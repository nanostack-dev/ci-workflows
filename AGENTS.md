# CI workflow agent guide

This repository owns reusable, public-safe GitHub Actions verification/build workflows and dispatch handoffs. Clone it independently; its local documentation supplies the required guidance.

Read [CONTEXT.md](CONTEXT.md) and [docs/README.md](docs/README.md). Before changing workflow contracts, read [architecture](docs/technical/architecture.md); for validation use [testing](docs/development/testing.md). Before publishing a workflow revision or repairing a consumer, read [deployment](docs/runbooks/deployment.md) and [rollback](docs/runbooks/rollback.md).

- Keep deploy execution, preview resources and environment-specific secret orchestration in the caller/control-plane repository. This repository accepts explicit inputs and secrets.
- Preserve reusable input/output contracts and public-safe defaults. A caller can be independently cloned; workflow reuse is a declared GitHub dependency, not a sibling filesystem requirement.
- Treat change-detection outputs as verification gates. An unresolved comparison must require verification, not silently skip it.
- Self-hosted runner diagnosis starts at [runner flakes](docs/self-hosted-runner-flakes.md).
- Read the caller's exact workflow/ref when assessing behavior; changes used at `@main` can affect consumers immediately.

Fetch and edit in an isolated worktree, retain primary checkout changes, and use Conventional Commits with focused PRs. Update the owning contract/development guide in the same PR after a behavior change or verified finding. Record consequential choices in [ADRs](docs/adr/README.md).
