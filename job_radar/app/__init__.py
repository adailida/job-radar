"""The app around a run: what happens before and after the pipeline.

`JobRadarApp` runs one command; `AppFactory` builds it and is the only place that
knows concrete classes. Before a run starts, the app agrees its windows
(`WindowPlanner`, `WindowChooser`), offers to resume a failed run (`ResumeOffer`)
and agrees what paid sources may spend (`CostCheck`). `RunsCommand` lists and
deletes runs, and the run results say how a run ended.
"""
