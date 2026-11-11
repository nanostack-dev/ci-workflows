# Reusable workflow documentation

Start with [agent guidance](../AGENTS.md) and [vocabulary](../CONTEXT.md).

- [CI principles](ci-principles.md): the organization's CI rules, the incident behind each, runner layout, and what is flaky by design. `cmd/ci-lint` enforces them.
- [CI flows](ci-flows.md): what every workflow file in every repository must do.
- [Architecture and contracts](technical/architecture.md).
- [Migration lint](technical/migration-lint.md): the safety linter for Postgres migrations, its rules, exclusions and opt-outs.
- [Dagger CI](technical/dagger.md): the `setup-dagger` action, where the engine runs on each runner type, conventions for checks, and the upgrade procedure.
- [Setup](development/setup.md), [validation](development/testing.md), [troubleshooting](development/troubleshooting.md).
- [Publishing/consumer rollout](runbooks/deployment.md), [rollback](runbooks/rollback.md).
- [Architecture decisions](adr/README.md): [0001 migration lint](adr/0001-lint-migrations-with-squawk-and-custom-checks.md).
- [Self-hosted runner flakes](self-hosted-runner-flakes.md): existing evidence and prevention.

The workflow files own exact inputs/defaults; guides explain boundaries and how to verify consumers.

## Postmortems

- [2026-11-05 gate transport resets](postmortems/2026-11-05-gate-transport-resets.md): the gate reruns a transport-only failure once and reports leaked cleanups ([report](postmortems/2026-11-05-gate-transport-resets.html)).
