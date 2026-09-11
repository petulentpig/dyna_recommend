# dyna_recommend

Read and follow [AGENTS.md](../AGENTS.md) at the repository root for the shared workflow, evidence rules, and development instructions. Read [README.md](../README.md) for setup and [docs/DTCTL.md](../docs/DTCTL.md) before querying Dynatrace. No locally installed assistant skill is required.

The runtime is Python 3.9+ with only the standard library and the dtctl CLI. Run tests from the repository root with `python3 -m unittest discover -s tests -v`. Keep customer configuration and reports out of Git. Preserve human review before exporting an email; the application never sends messages automatically.

Before any live operation, ask the user for their Dynatrace instance HTTPS URL unless they already provided it in this task. Never infer it from a saved context. Pass their answer using `run --environment URL`; the CLI verifies the context matches.
