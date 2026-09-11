# Project reviewer guide

Start with [README.md](../README.md) for installation and operator usage. [AGENTS.md](../AGENTS.md) defines the shared assistant workflow, [AI_USAGE.md](AI_USAGE.md) supplies provider-neutral prompts, and [DTCTL.md](DTCTL.md) covers authentication and diagnostics.

## Intended behavior

1. Ask for the user's Dynatrace instance URL, reusing an answer already supplied in the current task. Before account queries, verify that it matches the configured readonly dtctl context.
2. Discover available data and query Smartscape process/host technology metadata. Deduplicate each entity per technology and retain observed versions.
3. Fetch the official release indexes and choose the newest released sprint in each configured channel. Exclude future rollouts; do not fall back if the latest eligible page is unparseable.
4. Match individual changes to detected technologies. Hold uncertain multi-technology applicability and exclude changes with no detected match.
5. Generate an email with a separate section for each channel and its release version/date. Rank matching technologies and changes independently in each section. Preserve empty-channel sections.
6. Let a human review and edit the draft, then explicitly export an email for manual sending. No scheduling, automatic sending, or AI model calls are implemented.

## Code map

| Area | Implementation |
|---|---|
| Instance selection and context check | `choose_environment`, `verify_environment` in [recommend.py](../recommend.py) |
| Data collection and ranking | `dtctl`, `records_from`, `rank`, and [technologies.dql](../queries/technologies.dql) |
| Latest-release discovery and extraction | `fetch_releases`, `release_metadata`, `parse_release` |
| Relevance matching | `ALIASES`, `NORMALIZE`, `mentioned`, `select` |
| Channel sections, local ranks, and email | `channel_sections`, `draft_text`, `email_subject` |
| Human export record | `approve` |
| Installation and configuration | [install_dtctl.py](../install_dtctl.py), [config.example.json](../config.example.json) |
| Regression coverage | [test_recommend.py](../tests/test_recommend.py) |

## Validate without a tenant

From the repository root:

```sh
python3 -m unittest discover -s tests -v
python3 recommend.py run --help
python3 recommend.py approve --help
git diff --check
```

Tests use synthetic fixtures and mocks. They cover duplicate technology counts, instance selection, context mismatch rejection, release selection, future releases, channel isolation and rank resets, empty sections, partial results, and email export. These checks require neither a Dynatrace login nor an AI subscription. They do not test every upstream HTML layout, email client, OS, or assistant product.

## Validate with an authorized tenant

Follow the README with the reviewer's own instance and login. Inspect the generated files from the same run:

- `review.json` records the requested instance and selected release sources. Check those URLs against the official indexes and source snapshots.
- `review.md` lists the full inventory, its denominator, and held items. Check technology aliases and missing metadata before interpreting prevalence.
- `email.txt` should have one section per configured channel. Each technology ranking and change list starts at 1. Counts are specific to that channel's matched items; prevalence uses the full inventory. An item can reference multiple technologies, so item-count columns need not sum to the number of changes.
- `email-subject.txt` names the customer and selected release versions. Rollout dates are in the body.

Review does not require exporting or sending an email. Use the documented approval command only when the human has approved the draft and recipient.

## Important review boundaries

This is an initial implementation with live validation, not a claim of complete technology or release-note coverage. The central design choices to assess are:

- **Usage measure:** counts process and host entities equally. It measures deployment presence, not traffic, risk, cost, or business priority.
- **Coverage:** only the checked-in process/host fields are collected. Missing metadata, unknown aliases, remote services, and feature-level usage can leave gaps.
- **Matching:** deterministic text aliases and shared-entity evidence are conservative heuristics, not version-range or feature-configuration evaluation. Human review remains necessary.
- **Sources:** the HTML parser can omit table-only content. Discovery selects the highest sprint advertised in each configured index with an eligible rollout date; it does not establish customer deployment status.
- **Review records:** export records a supplied reviewer name and hashes but does not authenticate the reviewer or prevent stale exports. Re-export after edits; approval files are overwritten, not an immutable history.
- **Repeat runs:** there is no delivery ledger. The same latest release can appear again until a newer release is published.
- **Portability:** the Python runtime is independent of AI providers. Tool access, authentication, OS support, and assistant instruction loading still depend on the chosen environment.

Share the private repository with authorized reviewers through the usual GitHub access process. Customer reports and credentials are not part of the source repository; default local paths are ignored, while custom paths need their own ignore rules.
