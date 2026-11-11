# ci-workflows

Public-safe reusable GitHub Actions workflows for Nanostack application CI.

Start with [AGENTS.md](AGENTS.md), [CONTEXT.md](CONTEXT.md) and [the documentation index](docs/README.md) for standalone maintenance, validation and consumer rollout.

This repo is intended to contain only verification and build workflows such as:

- frontend verify
- Go build and test
- container image publishing
- migration lint: pinned squawk plus custom checks on the Postgres migrations a pull request adds ([guide](docs/technical/migration-lint.md))
- repository dispatch handoff to the private deploy repo
- `workflow-lint.yml`: actionlint plus `cmd/ci-lint`, the organization's CI rules ([principles](docs/ci-principles.md), [per-file flows](docs/ci-flows.md))
- `preview.yml`: raise and tear down a pull request's preview from its description checkbox
- `setup-dagger`, a composite action that installs the pinned Dagger CLI for `dagger check` ([guide](docs/technical/dagger.md))

It should not contain deploy, preview, infra checkout, or environment-specific secret orchestration.

## Self-hosted runners

[`docs/self-hosted-runner-flakes.md`](docs/self-hosted-runner-flakes.md) explains four failures that only happen when several jobs share one self-hosted host, and how these workflows prevent them: Storybook tests that hang or fail to import a module (Chrome's `net::ERR_NETWORK_CHANGED` on Docker interface changes), golangci-lint's `parallel golangci-lint is running` lock, integration tests that fill the host's memory, and golangci-lint exiting with code 137.
