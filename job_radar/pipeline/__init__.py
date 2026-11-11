"""The pipeline that runs a run's steps in order, saving each step's output.

`Pipeline` runs a list of `Step`s and resumes from the saved ones. The steps
themselves live in `steps/`, one module each, named after the step.
"""
