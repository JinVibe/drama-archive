"""Entity resolution: silver record -> canonical IDs (or CREATE_NEW / REVIEW).

`matching` is pure and takes a `Repo` for lookups; `repo` is the PostgreSQL
implementation. An LLM is never the authority for canonical identity.
"""
