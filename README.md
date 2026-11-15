# JobLoom

JobLoom searches job boards from the command line and keeps what it finds in a local SQLite database. Public search goes through [`python-jobspy`](https://github.com/speedyapply/JobSpy), which covers LinkedIn, Indeed and several other boards without an account. Personalized feeds, such as LinkedIn's recommended jobs, are optional and sit behind a separate adapter.

It only reads. JobLoom never applies, fills in forms, answers screening questions, sends messages or changes anything on a job-board account; reviewing and applying stay with you. Output is JSON by default, so scripts and agents can use it as easily as a person can.

## Install

From a local checkout:

```bash
uv sync --locked --all-extras
uv run jobloom --version
```

Current GitHub source install:

```bash
uv tool install git+https://github.com/soffits/jobloom.git
```

It isn't on PyPI.

## Usage

JSON is the default output format. stdout contains only the requested result; diagnostics and structured JSON errors go to stderr, even when `--format table` is requested.

```bash
jobloom init
jobloom search "python developer" --site linkedin --site indeed --location "New York, NY" --country USA --limit 20
jobloom search "data engineer" --location Remote --country USA --remote --save
jobloom feed linkedin --limit 10
jobloom feed indeed
jobloom jobs list --limit 20
jobloom doctor
jobloom providers
```

`feed linkedin` requires an optional external `linked` executable from `russ-blaisdell/linked`, configured by the user as a single executable path/name. JobLoom never installs it automatically, never accepts configured extra argv, and never executes it through a shell.

`feed indeed` intentionally fails with a structured provider-unavailable error. No verified open-source Indeed-native personalized For You CLI is known. `search --site indeed` is available for anonymous public search, but it is not Indeed For You.

## Boundaries

LinkedIn personalized feeds depend on an experimental private Voyager API helper. Upstream currently self-reports recommended jobs working, but JobLoom has not independently live-verified that claim. The upstream private API and query IDs can drift without notice and may carry account or Terms-of-Service risk. JobLoom keeps this behind an optional external-command adapter and does not read or store LinkedIn or Indeed passwords, cookies, browser storage, credentials, or account tokens.

JobLoom uses `python-jobspy` as a normal package dependency rather than vendoring, forking, or adding a git submodule. A package dependency plus a thin adapter keeps upstream code separate, makes upgrades auditable, and lets `uv.lock` and Dependabot provide reproducible development and reviewable dependency updates.

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 2 | Usage error |
| 3 | Configuration error |
| 4 | Provider unavailable, auth issue, or output drift |
| 5 | Local state or storage error |
| 6 | Upstream, network, or public search error |

## License

AGPL-3.0-or-later. See `LICENSE`.
