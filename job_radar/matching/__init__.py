"""Deciding what a posting is and whether it is wanted, without the LLM.

`JobMatcher` checks jobs against the searches, `JobKey` decides which postings
are the same job, and `AtsLinks`, `PlaceCodes` and `Normalizer` put links, places
and names in one form for them.
"""
