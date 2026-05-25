# ci-workflows

Public-safe reusable GitHub Actions workflows for Nanostack application CI.

This repo is intended to contain only verification and build workflows such as:

- frontend verify
- Go build and test
- container image publishing

It should not contain deploy, preview, infra checkout, or environment-specific secret orchestration.
