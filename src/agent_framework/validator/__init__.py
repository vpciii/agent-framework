"""Validator agent: the cite-the-test gate (ADR 0005).

A PR is *done* only when every claimed success criterion is backed by cited,
passing evidence. Deterministic checks run as code before any model call;
the model judges only what code cannot. Verdicts cite; they never assert.
"""
