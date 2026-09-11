# dyna_recommend

Create a customer-specific Dynatrace release digest from observed technology usage.

The process queries a read-only dtctl context, ranks detected technologies, reads official OneAgent/SaaS/ActiveGate release notes, and writes an editable email and an internal review report. A named human reviewer exports an `.eml` file for manual sending. There is no automatic email delivery.

## Use with ChatGPT, Claude, or Copilot

The pipeline is AI-provider independent: it uses Python and dtctl, with no model SDK, AI API key, or assistant plugin required. Use any assistant with repository/terminal access to run it, or run it yourself and review the files in a chat assistant.

[AGENTS.md](AGENTS.md) contains the shared workflow. Claude Code and GitHub Copilot have small repository instruction files pointing to that guide. [AI usage and copyable prompts](docs/AI_USAGE.md) covers setup for colleagues, tool-capable assistants, and chat-only review. [The portable dtctl runbook](docs/DTCTL.md) supplies the instructions previously provided by a local skill.

## Quick start

First ask the operator which Dynatrace instance to use and obtain its full HTTPS URL. Each user supplies their own instance; the application never defaults to a tenant from this repository or a saved context.

Requires Python 3.9+ and dtctl 0.38.0 or a compatible version. No Python packages are required.

```sh
python3 install_dtctl.py
.tools/dtctl auth login --context dyna-recommend --environment https://YOUR-ENVIRONMENT.apps.dynatrace.com --safety-level readonly
cp config.example.json local.json
# Edit customer/context in local.json.
python3 recommend.py run --config local.json
```

The `run` command asks for the instance URL in an interactive terminal. For an assistant or other noninteractive caller, first obtain the URL from the user and pass `--environment https://THEIR-INSTANCE.apps.dynatrace.com`. Missing input stops noninteractive runs. Before querying, the CLI checks the supplied URL against the configured readonly dtctl context; a mismatch stops without fetching account data. The selected instance is recorded in the internal review report. A URL already supplied for the current task does not need to be requested again.

Authentication belongs to dtctl and the OS credential store. Never put tokens in the config or repository. The installed binary is local to `.tools/`; it is not added to global PATH.

## Review and send

Every run creates a new timestamped directory under `runs/`:

- `email.txt`: editable customer draft naming the latest release per channel, with a technology ranking table and source links. Every detected technology shows its rank, distinct entity count, prevalence, and matched item count.
- `email-subject.txt`: suggested subject naming the customer and selected releases; approval uses the same subject format.
- `review.md`: technology ranking and applicability questions.
- `review.json`: all included, held, and excluded items, reasons, evidence, and source hashes.
- `inventory-raw.json`, `discovery.json`: tenant evidence for internal review.
- `sources/`: source pages captured for reproducibility.

Review the source notes and edit `email.txt`. Check the customer name and the specific version, operating system, feature flags, or licensing prerequisites. Held items are omitted from the email; add one manually only after confirming applicability.

After review:

```sh
python3 recommend.py approve runs/RUN_ID --reviewer 'Your name' --to customer@example.com
```

This creates `approved.eml` with `X-Unsent: 1` and records reviewer, recipient, time, and content hashes in `approval.json`. Open the message in your email client, choose the sender, and send it manually. Export is not proof of delivery. If you edit the draft afterward, run approval again to export the updated content. The approval log records the operator-provided name; it is not an identity authentication system.

## Usage weighting

The live query reads Smartscape PROCESS technology arrays from each OneAgent module plus HOST technologies and OS metadata. Canonical aliases merge equivalent technology names. An entity is counted once per technology, even if several modules or versions report it.

`prevalence = distinct entities with technology / all queried process and host entities`

The denominator includes entities without technology metadata, which are also reported. Technologies overlap, so percentages do not add to 100. Hosts and processes count equally in this first version. This measures observed deployment prevalence, not request volume, CPU consumption, spend, or business criticality. A release item uses the highest entity count among its matched technologies as its sorting score; ties prefer newer releases. Low-prevalence matches are retained.

## Release filtering

Every run fetches the official indexes again and selects exactly one release per configured channel: the highest sprint version whose documented rollout date is on or before the run date (UTC). OneAgent, SaaS, and ActiveGate can have different latest versions. Planned future rollouts are skipped, including planned pages with no change details yet. The selected releases and rollout dates appear at the top of the email and in its suggested subject, even if they have no matched items.

There is no lookback window: the latest released version is used regardless of age. The obsolete `release_days` setting is ignored in existing configurations and removed from the example. Missing links, versions, dates, or change details in the latest eligible page fail the run rather than silently substituting older releases. Discovery checks at most 20 candidates per channel and fails if no released version is found. The report covers the published release, not proof that it has been deployed to the customer tenant.

Each feature and individual fix is matched using explicit technology aliases with word boundaries. For example, JavaScript does not match Java, and the verb “go” does not match the Go runtime. Items mentioning additional undetected technologies are held. Multiple runtime/library technologies must also appear on at least one shared entity; otherwise their joint applicability is held for review. OS and Kubernetes matches do not require sharing a process ID.

Exact duplicate title/body pairs are collapsed within a run. There is no cross-run delivery ledger: rerunning before a new release appears can repeat notes, so the reviewer must compare previous customer emails. The latest release pages are fetched again on every run, including revisions to their content; older releases are not added because they were recently edited.

## Coverage and limits

This is a working first version, with live validation against Smartscape. It does not prove that every account technology or every relevant release item has been found:

- The query covers OneAgent process and host technology metadata. Remote managed services, frontend frameworks, extensions, licensing, RUM feature usage, and OTEL-only entities need additional collectors. The inventory command's capability report is preserved as context, not treated as a substitute for technology evidence.
- Unknown inventory technology types appear in the review report. Extend `ALIASES`/`NORMALIZE` for them; no fuzzy inference is used. An unknown technology mentioned only in prose can escape matching, so human source review remains necessary.
- Detection establishes presence, not that a customer is affected. Installed versions are collected but version ranges and feature prerequisites are not evaluated automatically.
- The HTML adapter targets the current release-page structure. Changes described only in tables or headings without body text may be omitted. A nonempty parsed page is not proof of complete extraction.
- Generic Dynatrace announcements without an explicit technology match are excluded. The output is a link-led digest, not an AI-generated upgrade recommendation.
- dtctl errors, empty inventories, non-inline results, warnings, or hitting the configured entity limit stop generation. Authentication refresh is handled by dtctl. A failed run may leave diagnostic files but will not produce an approved email.

Customer data, config, downloaded tools, and generated output are ignored by Git. Only source, query templates, and synthetic tests should be committed.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests exercise deduplication, inventory aliases, false-positive matches, missing technology evidence, separate-entity dependencies, latest releases per channel, future releases, email ranking and release labels, parser failure, incomplete queries, and reviewed-message export.

## Sources

- [dtctl](https://github.com/dynatrace-oss/dtctl)
- [Smartscape core entity technology fields](https://docs.dynatrace.com/docs/semantic-dictionary/model/smartscape/core)
- [OneAgent release notes](https://docs.dynatrace.com/docs/whats-new/oneagent)
- [SaaS release notes](https://docs.dynatrace.com/docs/whats-new/saas)
- [ActiveGate release notes](https://docs.dynatrace.com/docs/whats-new/activegate)
