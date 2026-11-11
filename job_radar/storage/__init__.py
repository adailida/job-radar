"""Where a run's state lives on disk: one interface and one file-backed class each.

Checkpoints and the manifest, the run history, seen jobs, the spend, drop,
pending, warning, error and source count logs, the run lock, and the cache of
how requirements compare with the CV.
"""
