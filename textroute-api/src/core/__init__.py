"""Persistence managers and processing primitives.

- ``*Manager`` — DB reads/writes; ``flush`` only, never ``commit``
- ``phone_normalize`` — E.164 identity keys
- ``MessageProcessor`` — extension point for AI intent / matching
"""
