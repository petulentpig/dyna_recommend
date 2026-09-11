# Portable dtctl runbook

This runbook is part of the repository so every assistant and operator can use the same process. An installed ChatGPT, Claude, or Copilot skill is optional.

## Set up your own environment

From the repository root, follow the README installer steps, then authenticate with your own tenant and context:

```sh
.tools/dtctl auth login --context my-customer --environment https://YOUR-ENVIRONMENT.apps.dynatrace.com --safety-level readonly
```

Use the actual platform URL supplied by the customer, including an internal lab domain when applicable. Put the chosen context name in your ignored `local.json`. Colleagues authenticate independently; cloning the repository does not copy credentials or tenant configuration.

Commands here use the macOS/Linux project-local binary. If you install dtctl elsewhere, use its path or `dtctl` on PATH and optionally set `"dtctl": "/path/to/dtctl"` in local.json. The bundled installer supports macOS and Linux; on Windows use WSL for these commands or install the official Windows executable and set the config path. AI-provider support does not imply that this installer supports every OS.

## Establish context before querying

```sh
.tools/dtctl commands
.tools/dtctl config current-context
.tools/dtctl config describe-context my-customer --plain
.tools/dtctl --context my-customer auth status --plain
.tools/dtctl --context my-customer inventory -o json --no-agent
```

Check the environment and readonly safety level. `inventory` describes available data and capability evidence. A missing capability is not always proof that a technology is absent: process or host technology metadata can provide positive evidence independently.

Use explicit `--context` on operations to avoid querying whichever tenant happens to be globally selected. Do not use `auth whoami` as a connectivity probe; its scope requirements can differ from ordinary read operations. Avoid `--debug` and `-vv`, which may expose authentication headers.

## Run the checked-in query

The Python pipeline already runs discovery and the query. For troubleshooting only:

```sh
.tools/dtctl --context my-customer query -f queries/technologies.dql --agent -o json --spill=never --max-result-records 100000
```

Use the existing query rather than reconstructing it from memory. Before changing DQL, inspect `dtctl commands` and current official documentation, especially the [Smartscape core fields](https://docs.dynatrace.com/docs/semantic-dictionary/model/smartscape/core). Use double quotes for DQL strings and query files to avoid shell-quoting problems. Smartscape data uses `smartscapeNodes`/`smartscapeEdges`; metrics use `timeseries`, not `fetch metrics`.

In agent output, check `ok` and `result.kind` rather than assuming a rows array. The pipeline requests bounded inline records and rejects non-record results, warnings, empty results, and a reached limit. If an exploratory query spills to a file, use `dtctl inspect` to examine that file instead of repeating the query. An incomplete inventory must not be presented as a complete list of account technologies.

See the [official dtctl project](https://github.com/dynatrace-oss/dtctl) for installation, authentication, and command changes.
