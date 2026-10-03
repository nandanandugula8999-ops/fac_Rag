"""API layer.

Stage 16 of the pipeline, and the public surface of the engine.

Planned endpoints:
  * search faculty by topic / free-text query
  * retrieve a faculty profile with evidence and citations
  * disambiguate a researcher name to a canonical identity
  * filter by topic, department, or year range
  * later: collaboration suggestions and trend reports

Every response returns evidence alongside the score, so the API cannot express
a ranking that the underlying data does not support.
"""
