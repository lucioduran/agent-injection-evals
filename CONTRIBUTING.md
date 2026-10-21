# Contributing

Use Python 3.11 and focused commits. Install requirements-dev.txt and run the
commands in README Testing. Include regression tests for behavior changes and
negative cases. Keep code, fixtures and documentation in English with no em dash
characters. Design explanations belong in docs, not large code comments.

Freeze dataset and prompt changes before a new model evaluation. Preserve prior
raw runs, disclose failures, and use a new result directory. Do not tune on the
evaluation split. Reproduction must use local hardware and free resources.
Serialize heavy work with the shared lock when working in the project series.
Never introduce executable generated actions, real credentials or live tool calls.
