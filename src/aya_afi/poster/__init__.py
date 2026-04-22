"""Actual SNS posting layer.

Separate from ``sns_engine`` (content generation + validation):
- ``sns_engine`` = decides what to say
- ``poster`` = delivers it to the SNS

Stage 1 scope (current): Protocol + types + mock + note clipboard + stubs
for Threads / Bluesky. Real Threads / Bluesky API calls land in Stage 3.
"""
