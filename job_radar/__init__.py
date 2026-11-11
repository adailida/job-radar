"""Job search and job-market trends, pulled from job APIs.

Reading order, from the command down:

- `cli`: the `job-radar` command, the entry point
- `app`: the app around a run: building it, the window, resume, the cost check, `runs`
- `pipeline`: the pipeline that runs the steps, and `pipeline/steps`, one module per step
- `sources`: one adapter per job board into the common posting format
- `llm`: the LLM and each pass that uses it: rank, classify, extract, judge gaps
- `matching`: searches against jobs, which postings are the same job, places and names
- `report`: the report's sections, its renderer and its writer
- `storage`: where a run's state lives on disk: checkpoints, history, logs, caches
- `config`: code that reads the user's files: settings, profile, searches, secrets
- `utils`: the clock, the terminal prompter, HTML to text, the base errors
- `models`: the domain models every part passes around
"""

from importlib.metadata import version

__version__ = version("job-radar")
