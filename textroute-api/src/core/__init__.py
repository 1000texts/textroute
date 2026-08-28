"""Core capabilities grouped by responsibility.

- ``managers`` — focused DB reads/writes; ``flush`` only, never ``commit``
- ``providers`` — external integration contracts and adapters
- ``processors`` — pure analysis and recommendation logic
- ``phone_normalize`` — E.164 identity-key utility

There is no ``resolvers`` package yet. Add one when a reusable relationship or
context-resolution component emerges; keep service-local flow steps local until
then.
"""
