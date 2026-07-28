---
name: jobloom
description: Use when discovering jobs with the JobLoom CLI.
version: 0.1.0
author: Sakina
license: AGPL-3.0-only
metadata:
  hermes:
    tags:
      - jobs
      - cli
      - local-first
      - read-only
---

# JobLoom Agent Guidance

Use JSON output by default so results are machine-readable:

```bash
jobloom search "python developer" --location Remote --country USA --limit 20 --format json
jobloom jobs list --format json
jobloom doctor --format json
jobloom providers --format json
```

Never expose, request, read, paste, or store cookies, passwords, browser storage, credentials, or private job-search files. Never access unrelated private configuration or credentials for JobLoom work.

Distinguish anonymous public search from native personalized feeds. `jobloom search --site indeed` is public search, not Indeed For You. `jobloom feed linkedin` is a platform-native personalized feed only when the user has independently installed and configured the optional `linked` command.

Do not auto-apply, submit forms, answer application questions, send messages, or modify job-board accounts. Leave final application submission to the user.
