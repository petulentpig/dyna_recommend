# dyna_recommend

Create a customer-specific Dynatrace release digest from observed technology usage.

The process queries a read-only dtctl context, ranks detected technologies, reads official OneAgent/SaaS/ActiveGate release notes, and writes an editable email and an internal review report. A named human reviewer exports an `.eml` file for manual sending. There is no automatic email delivery.

For a project review, start with the [reviewer guide](docs/REVIEW_GUIDE.md), then use the setup below.

## Use with ChatGPT, Claude, or Copilot

The pipeline is AI-provider independent: it uses Python and dtctl, with no model SDK, AI API key, or assistant plugin required. Use any assistant with repository/terminal access to run it, or run it yourself and review the files in a chat assistant.

[AGENTS.md](AGENTS.md) contains the shared workflow. Claude Code and GitHub Copilot have small repository instruction files pointing to that guide. [AI usage and copyable prompts](docs/AI_USAGE.md) covers setup for colleagues, tool-capable assistants, and chat-only review. [The portable dtctl runbook](docs/DTCTL.md) supplies the instructions previously provided by a local skill.

## Quick start

First ask the operator which Dynatrace instance to use and obtain its full HTTPS URL. Each user supplies their own instance; the application never defaults to a tenant from this repository or a saved context.

Requires Python 3.9+, Git, access to this private repository, and dtctl 0.38.0. The installer pins that dtctl version; compatibility with other versions is not guaranteed. No Python packages are required. The commands below target macOS or Linux (including WSL); see the [dtctl runbook](docs/DTCTL.md) for platform details. Live runs need network access to the selected Dynatrace environment and official Dynatrace documentation; installation also accesses GitHub.

```sh
git clone https://github.com/petulentpig/dyna_recommend.git
cd dyna_recommend
python3 install_dtctl.py
.tools/dtctl auth login --context dyna-recommend --environment https://YOUR-ENVIRONMENT.apps.dynatrace.com --safety-level readonly
# First checkout only: do not overwrite an existing local.json.
cp config.example.json local.json
# Replace the example customer and select your authenticated context in local.json.
python3 recommend.py run --config local.json
```

Replace `https://YOUR-ENVIRONMENT.apps.dynatrace.com` with the user-provided platform URL before running login. If you already have the clone, start in its root and skip `git clone`. Each colleague uses their own authenticated context.

The `run` command asks for the instance URL in an interactive terminal. For an assistant or other noninteractive caller, first obtain the URL from the user and pass `--environment https://THEIR-INSTANCE.apps.dynatrace.com`. Missing input stops noninteractive runs. Before querying, the CLI checks the supplied URL against the configured readonly dtctl context; a mismatch stops without fetching account data. The selected instance is recorded in the internal review report. A URL already supplied for the current task does not need to be requested again.

Authentication belongs to dtctl and the OS credential store. Never put tokens in the config or repository. The installed binary is local to `.tools/`; it is not added to global PATH.

## Configuration and CLI

Copy [config.example.json](config.example.json) to `local.json` on first setup. The JSON file uses these keys:

| Key | Required | Meaning |
|---|---|---|
| `customer` | Yes | Customer name for the greeting and subject; replace the example `Customer`. |
| `context` | Yes | Name of an existing dtctl context for the user-selected instance. It must be `readonly`. |
| `channels` | Yes | Nonempty list chosen from `oneagent`, `saas`, and `activegate`. List order is the email section order; duplicates are ignored. |
| `entity_limit` | No | Positive integer query limit; defaults to `100000`. Reaching the limit stops the run to avoid reporting a partial inventory. |
| `dtctl` | No | Executable path or command name. Defaults to the repository’s `.tools/dtctl`, falling back to `dtctl` on PATH. Prefer an absolute path for a custom installation. |

The instance URL is supplied separately, through the interactive prompt or `--environment`; a context name is not a substitute for the user's instance selection. The obsolete `release_days` key is ignored. Configuration is a simple JSON file, not an interactive setup wizard: it is not automatically created or updated by `run`.

Run commands from the repository root. `--config` defaults to `local.json` and relative config paths resolve from the current working directory. Output defaults to a new directory under the repository's `runs/`. An optional `--output PATH` must name a directory that does not yet exist; relative output paths resolve from the current working directory. Failed runs may leave a directory with diagnostic files, so use a new output path for a retry.

```sh
python3 recommend.py run --help
python3 recommend.py approve --help
```

## Review and send

A successful default run prints the path of its new timestamped directory under `runs/`:

- `email.txt`: editable customer draft naming the latest release per channel, with separate, explicitly labeled sections for the configured channels (OneAgent, SaaS, and ActiveGate by default) and source links. Each channel ranks only technologies with matched changes, showing rank, distinct entity count, prevalence, and that channel’s matched item count. Both technology ranks and numbered change ranks restart at 1 in each section. Channels with no matches retain their release heading and an explicit no-match message; the full detected inventory remains in the review report.
- `email-subject.txt`: suggested subject naming the customer and selected release versions. `approve` regenerates it from `review.json`; editing this text file alone does not change the exported subject. Rollout dates appear in the body, not the subject.
- `review.md`: technology ranking and applicability questions.
- `review.json`: all included, held, and excluded items, matches, held/excluded reasons, entity IDs and versions, selected instance, release metadata, and source hashes. Channel-local rank numbers are calculated when formatting the email, rather than stored here.
- `inventory-raw.json`, `discovery.json`: tenant evidence for internal review.
- `sources/`: selected release-page HTML snapshots for checking extracted content. Discovery indexes are not saved, so these files alone do not reproduce latest-release discovery.

Review the source notes and edit `email.txt`. Check the customer name and the specific version, operating system, feature flags, or licensing prerequisites. Held items are omitted from the email; add one manually only after confirming applicability. If you add or remove an item, update the affected channel’s counts and ranks in the draft as well, and record the rationale separately for the reviewer. Editing `email.txt` does not recalculate `review.json` or the ranking tables.

After a human approves the current draft, replace `RUN_ID` with the run directory printed by the command and export it:

```sh
python3 recommend.py approve runs/RUN_ID --reviewer 'Your name' --to customer@example.com
```

This creates a plain-text `approved.eml` with `X-Unsent: 1`, the supplied recipient, and the generated subject. It records reviewer, recipient, time, and draft/export hashes in `approval.json`. It does not add a From address. Open the message in your email client, select the sender, verify formatting and recipient, and send it manually. Draft handling varies by mail client; the file export itself never sends a message.

`approve` records the operator-provided reviewer name; it does not authenticate a reviewer, compare changes, or enforce access control. Repeating it overwrites `approved.eml` and `approval.json`; there is no append-only approval history. Editing the draft afterward does not automatically invalidate the old export: review again and re-export before using it. `review.json` remains marked `needs_review`; `approval.json` records `approved_for_manual_send`. Neither file proves delivery. These are workflow aids, not an enforced multi-user approval service.

## Usage weighting

The live query reads Smartscape PROCESS technology arrays from each OneAgent module plus HOST technologies and OS metadata. Canonical aliases merge equivalent technology names. An entity is counted once per technology, even if several modules or versions report it.

`prevalence = distinct entities with technology / all queried process and host entities`

The denominator includes entities without technology metadata, which are also reported. Technologies overlap, so percentages do not add to 100. Hosts and processes count equally in this first version. This measures observed deployment prevalence, not request volume, CPU consumption, spend, or business criticality. Within each channel, technology ranks use descending entity count, breaking ties alphabetically by canonical technology identifier. A release item uses the highest entity count among its matched technologies as its sorting score; ties use a stable item ID. The same technology can have different local ranks in different channels. Prevalence always uses the full queried inventory as its denominator, not the channel subset. Low-prevalence matches are retained.

## Release filtering

Every run fetches the official indexes again and selects exactly one release per configured channel: the highest sprint version whose documented rollout date is on or before the run date (UTC). OneAgent, SaaS, and ActiveGate can have different latest versions. Planned future rollouts are skipped, including planned pages with no change details yet. Each email section names its channel, selected release version, and rollout date, even when it has no matched items. The suggested subject names all selected release versions.

There is no lookback window: the latest released version is used regardless of age. The obsolete `release_days` setting is ignored in existing configurations and removed from the example. Missing links, versions, dates, or change details in the latest eligible page fail the run rather than silently substituting older releases. Discovery checks at most 20 candidates per channel and fails if no released version is found. The report covers the published release, not proof that it has been deployed to the customer tenant.

Each feature and individual fix is matched using explicit technology aliases with word boundaries. For example, JavaScript does not match Java, and the verb “go” does not match the Go runtime. An item with at least one detected technology match is held if it also mentions an undetected technology. An item with no detected technology matches is excluded. Multiple runtime/library technologies must also appear on at least one shared entity; otherwise their joint applicability is held for review. Linux, Windows, AIX, Kubernetes, and OpenShift are exempt from the shared-entity check. This exception does not verify a host/process relationship or prove that an OS-specific change applies.

Exact duplicate title/body pairs are collapsed within the same release page. The same change appearing in separate channels remains in each applicable channel section. There is no cross-run delivery ledger: rerunning before a new release appears can repeat notes, so the reviewer must compare previous customer emails. The latest release pages are fetched again on every run, including revisions to their content; older releases are not added because they were recently edited.

## Coverage and limits

This is a working first version, with live validation against Smartscape. It does not prove that every account technology or every relevant release item has been found:

- The query covers OneAgent process and host technology metadata. Remote managed services, frontend frameworks, extensions, licensing, RUM feature usage, and OTEL-only entities need additional collectors. The inventory command's capability report is preserved as context, not treated as a substitute for technology evidence.
- Unknown inventory technology types appear in the review report. Extend `ALIASES`/`NORMALIZE` for them; no fuzzy inference is used. An unknown technology mentioned only in prose can escape matching, so human source review remains necessary.
- Detection establishes presence, not that a customer is affected. Installed versions are collected but version ranges and feature prerequisites are not evaluated automatically.
- The HTML adapter targets the current release-page structure. Changes described only in tables or headings without body text may be omitted. A nonempty parsed page is not proof of complete extraction.
- Generic Dynatrace announcements without an explicit technology match are excluded. The output is a link-led digest, not an AI-generated upgrade recommendation.
- dtctl errors, empty inventories, non-inline results, query-envelope `has_more` or `warnings`, or hitting the configured entity limit stop generation. This checks the signals returned by dtctl; it is not an independent completeness audit of all tenant data. Authentication refresh is handled by dtctl. A failed run may leave diagnostic files but will not produce an approved email.

The default `local.json`, `.tools/`, `runs/`, `.env`, and `.dtctl.yaml` paths are ignored by Git. A custom configuration filename or output directory outside these paths is **not** automatically ignored. Add an appropriate ignore rule before using such paths inside the repository. Only source, shared documentation, query templates, and synthetic fixtures should be committed.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests run offline with synthetic fixtures and mocked network/CLI calls. They exercise instance prompting and context mismatch rejection, independent channel rankings, deduplication, inventory aliases, false-positive matches, missing technology evidence, separate-entity dependencies, latest releases per channel, future releases, email ranking and release labels, parser failure, incomplete queries, and reviewed-message export.

## Sources

- [dtctl](https://github.com/dynatrace-oss/dtctl)
- [Smartscape core entity technology fields](https://docs.dynatrace.com/docs/semantic-dictionary/model/smartscape/core)
- [OneAgent release notes](https://docs.dynatrace.com/docs/whats-new/oneagent)
- [SaaS release notes](https://docs.dynatrace.com/docs/whats-new/saas)
- [ActiveGate release notes](https://docs.dynatrace.com/docs/whats-new/activegate)
