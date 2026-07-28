# Providers

## jobspy-public

`jobspy-public` is the anonymous public-search adapter. It calls `python-jobspy` through a thin boundary, normalizes records to JobLoom's internal `Job` model, and preserves JSON-safe raw data.

JobLoom depends on `python-jobspy>=1.1.82,<2` as a package dependency. It is not vendored, forked, or included as a submodule. This keeps upstream code reviewable, avoids copying scraper implementation into JobLoom, and lets the lockfile and Dependabot manage reproducible updates.

## linkedin-linked

`linkedin-linked` is an optional external-command provider for platform-native personalized LinkedIn recommendations. It expects a user-installed `linked` executable compatible with:

```bash
linked jobs recommended --count N -o json
```

Configure only a single executable path/name:

```toml
[providers.linkedin_linked]
executable = "linked"
timeout_seconds = 20
```

JobLoom always constructs exactly `[executable, "jobs", "recommended", "--count", N, "-o", "json"]`, passes it as an argv list, never with `shell=True`, removes `LINKED_DEBUG`, sets `NO_COLOR=1`, and applies a validated timeout from 1 to 300 seconds. It parses either `{ "items": [...] }` or a top-level array. Provider failures return structured errors without tracebacks, provider stdout, or secrets. Raw provider mappings are sanitized before output or storage.

## indeed-native

`indeed-native` is unavailable by design. No credible open-source Indeed-native personalized For You CLI has been verified, and JobLoom does not claim a native Indeed For You provider. JobLoom reports that clearly and suggests anonymous public search with `search --site indeed`, while stating that search is not Indeed For You.
