# dyna_recommend

Read and follow [AGENTS.md](AGENTS.md), the shared operating guide, before working on this project. Read [README.md](README.md) for setup and [docs/DTCTL.md](docs/DTCTL.md) for Dynatrace commands. These repository files replace any dependency on a locally installed dtctl skill.

The runtime is Python 3.9+ and dtctl. AI APIs are not required. Run tests with `python3 -m unittest discover -s tests -v`. Preserve human review before exporting an email; the application never sends messages automatically.

Before any live operation, ask the user for their Dynatrace instance HTTPS URL unless they already provided it in this task. Never infer it from a saved context. Pass their answer using `run --environment URL`; the CLI verifies the context matches.
