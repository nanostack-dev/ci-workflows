# Local workflow setup

Clone this repository independently and install Git, GitHub CLI and a YAML-aware editor. The repo has no package installation or application runtime. Install `actionlint` when validating workflow changes; ShellCheck can validate extracted shell scripts.

Select a caller repository/ref before a behavior experiment. A reusable workflow runs in the caller context; merging a PR here does not prove its consumers passed.

Use [testing](testing.md) for offline checks and [deployment](../runbooks/deployment.md) for rollout through a disposable caller branch.

Codex, OpenCode and Grok Build read the local `AGENTS.md`. Claude Code loads it through the repository-owned `.claude/settings.json` session-start hook. Review project/hook trust in the client and start a fresh session after changing this configuration; personal overrides remain in ignored `settings.local.json`.
