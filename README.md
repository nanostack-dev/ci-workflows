# ci-workflows

Public-safe reusable GitHub Actions workflows for Nanostack application CI.

This repo is intended to contain only verification and build workflows such as:

- frontend verify
- Go build and test
- container image publishing
- repository dispatch handoff to the private deploy repo

It should not contain deploy, preview, infra checkout, or environment-specific secret orchestration.

## Self-hosted runners

[`docs/self-hosted-runner-flakes.md`](docs/self-hosted-runner-flakes.md) explains two failures that only happen when several jobs share one self-hosted host, and how these workflows prevent them: Storybook tests that hang or fail to import a module (Chrome's `net::ERR_NETWORK_CHANGED` on Docker interface changes), and golangci-lint's `parallel golangci-lint is running` lock.
