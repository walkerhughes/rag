"""Measurement of retrieval against the evaluation examples.

Evaluation reads the retrieval contract and the example files, and writes nothing. It
sits above retrieval for the same reason a test sits above the code it covers: measuring
a strategy means calling it, and a strategy must never know it is being measured.
"""
