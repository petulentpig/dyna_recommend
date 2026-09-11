# dyna_recommend

Read and follow [AGENTS.md](AGENTS.md), the shared operating guide, before working on this project. Read [README.md](README.md) for setup and [docs/DTCTL.md](docs/DTCTL.md) for Dynatrace commands. These repository files replace any dependency on a locally installed dtctl skill.

The runtime is Python 3.9+ and dtctl. AI APIs are not required. Run tests with `python3 -m unittest discover -s tests -v`. Preserve human review before exporting an email; the application never sends messages automatically.
