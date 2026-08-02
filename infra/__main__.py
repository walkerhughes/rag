"""AWS backend for the rag project.

ECR, a VPC, and one Fargate service behind an application load balancer.
"""

import pulumi
import pulumi_aws as aws
import pulumi_awsx as awsx

config = pulumi.Config()
otlp_endpoint = config.get("otlpEndpoint") or "https://api.honeycomb.io"
STACK = pulumi.get_stack()

PORT = 8000

# --- network ---------------------------------------------------------------------
# Public subnets only. Tasks egress through the internet gateway, so there is no NAT
# gateway to pay for.
vpc = awsx.ec2.Vpc(
    "rag",
    # Each AZ adds a billable public IPv4 address on the load balancer.
    number_of_availability_zones=2,
    nat_gateways=awsx.ec2.NatGatewayConfigurationArgs(strategy=awsx.ec2.NatGatewayStrategy.NONE),
    subnet_specs=[awsx.ec2.SubnetSpecArgs(type=awsx.ec2.SubnetType.PUBLIC, cidr_mask=24)],
    # Pinned because the awsx default changes in the next major version.
    subnet_strategy=awsx.ec2.SubnetAllocationStrategy.AUTO,
)

alb_security_group = aws.ec2.SecurityGroup(
    "alb",
    vpc_id=vpc.vpc_id,
    description="Public HTTP ingress to the load balancer",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp", from_port=80, to_port=80, cidr_blocks=["0.0.0.0/0"]
        )
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"]
        )
    ],
)

# The container accepts traffic from the load balancer only.
task_security_group = aws.ec2.SecurityGroup(
    "task",
    vpc_id=vpc.vpc_id,
    description="Load balancer to container",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            protocol="tcp",
            from_port=PORT,
            to_port=PORT,
            security_groups=[alb_security_group.id],
        )
    ],
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            protocol="-1", from_port=0, to_port=0, cidr_blocks=["0.0.0.0/0"]
        )
    ],
)

# --- secrets ---------------------------------------------------------------------
# Created empty. The value is written separately, so no secret material passes through
# this program, its state file, or the repository. See the deploy section of README.md.
#
# Holds the bare key rather than an OTEL_EXPORTER_OTLP_HEADERS string, whose value the
# OpenTelemetry SDK writes to the log when it cannot parse it.
honeycomb_key_parameter = aws.ssm.Parameter(
    "honeycomb-api-key",
    name=f"/rag/{STACK}/honeycomb-api-key",
    type="SecureString",
    value="unset",
    opts=pulumi.ResourceOptions(ignore_changes=["value"]),
)

# --- image -----------------------------------------------------------------------
# Tagged by content hash, so a tag always refers to the same image.
repository = awsx.ecr.Repository(
    "rag",
    force_delete=True,
    lifecycle_policy=awsx.ecr.LifecyclePolicyArgs(
        rules=[
            awsx.ecr.LifecyclePolicyRuleArgs(
                description="Keep the last 10 images",
                tag_status="any",
                maximum_number_of_images=10,
            )
        ]
    ),
)

image = awsx.ecr.Image(
    "rag",
    repository_url=repository.url,
    context="..",
    dockerfile="../Dockerfile",
    platform="linux/arm64",
)

# --- load balancer ---------------------------------------------------------------
load_balancer = awsx.lb.ApplicationLoadBalancer(
    "rag",
    subnet_ids=vpc.public_subnet_ids,
    security_groups=[alb_security_group.id],
    default_target_group=awsx.lb.TargetGroupArgs(
        vpc_id=vpc.vpc_id,
        port=PORT,
        protocol="HTTP",
        target_type="ip",
        deregistration_delay=15,
        health_check=aws.lb.TargetGroupHealthCheckArgs(
            path="/health",
            matcher="200",
            interval=15,
            healthy_threshold=2,
            unhealthy_threshold=2,
        ),
    ),
)

# --- roles -----------------------------------------------------------------------
assume_by_ecs = aws.iam.get_policy_document(
    statements=[
        aws.iam.GetPolicyDocumentStatementArgs(
            actions=["sts:AssumeRole"],
            principals=[
                aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                    type="Service", identifiers=["ecs-tasks.amazonaws.com"]
                )
            ],
        )
    ]
).json

# Pulls the image and reads the one SSM parameter below.
execution_role = aws.iam.Role("execution", assume_role_policy=assume_by_ecs)

aws.iam.RolePolicyAttachment(
    "execution-ecs",
    role=execution_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
)

aws.iam.RolePolicy(
    "execution-ssm",
    role=execution_role.id,
    policy=honeycomb_key_parameter.arn.apply(
        lambda arn: (
            aws.iam.get_policy_document(
                statements=[
                    aws.iam.GetPolicyDocumentStatementArgs(
                        actions=["ssm:GetParameters"], resources=[arn]
                    )
                ]
            ).json
        )
    ),
)

# The application's own role. No policies attached: the app calls no AWS APIs.
task_role = aws.iam.Role("task", assume_role_policy=assume_by_ecs)

# --- service ---------------------------------------------------------------------
cluster = aws.ecs.Cluster("rag")

service = awsx.ecs.FargateService(
    "rag",
    cluster=cluster.arn,
    desired_count=1,
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        subnets=vpc.public_subnet_ids,
        security_groups=[task_security_group.id],
        assign_public_ip=True,  # needed to reach ECR without a NAT gateway
    ),
    task_definition_args=awsx.ecs.FargateServiceTaskDefinitionArgs(
        cpu="256",
        memory="512",
        execution_role=awsx.awsx.DefaultRoleWithPolicyArgs(role_arn=execution_role.arn),
        task_role=awsx.awsx.DefaultRoleWithPolicyArgs(role_arn=task_role.arn),
        runtime_platform=aws.ecs.TaskDefinitionRuntimePlatformArgs(
            cpu_architecture="ARM64", operating_system_family="LINUX"
        ),
        container=awsx.ecs.TaskDefinitionContainerDefinitionArgs(
            name="api",
            image=image.image_uri,
            cpu=256,
            memory=512,
            essential=True,
            port_mappings=[
                awsx.ecs.TaskDefinitionPortMappingArgs(
                    container_port=PORT,
                    target_group=load_balancer.default_target_group,
                )
            ],
            environment=[
                awsx.ecs.TaskDefinitionKeyValuePairArgs(name="APP_ENV", value="dev"),
                awsx.ecs.TaskDefinitionKeyValuePairArgs(name="OTEL_SERVICE_NAME", value="rag-api"),
                awsx.ecs.TaskDefinitionKeyValuePairArgs(
                    name="OTEL_EXPORTER_OTLP_ENDPOINT", value=otlp_endpoint
                ),
            ],
            secrets=[
                awsx.ecs.TaskDefinitionSecretArgs(
                    name="HONEYCOMB_API_KEY", value_from=honeycomb_key_parameter.arn
                )
            ],
        ),
    ),
)

pulumi.export("url", load_balancer.load_balancer.dns_name.apply(lambda n: f"http://{n}"))
pulumi.export("image", image.image_uri)
pulumi.export("cluster", cluster.name)
pulumi.export("service", service.service.name)
