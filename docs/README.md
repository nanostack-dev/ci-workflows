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
- [2026-11-13 gate SSE reset not transport](postmortems/2026-11-13-gate-sse-reset-not-transport.md): the gate's transport regex carries a sample self-test, kept in step with the routine's run_suites.sh ([report](postmortems/2026-11-13-gate-sse-reset-not-transport.html)).
- [2026-11-16 gate rerun idempotency conflict](postmortems/2026-11-16-gate-rerun-idempotency-conflict.md): each transport rerun launches with its own idempotency key (`transport-rerun-<run>-<attempt>-<flow>`), and echopoint-cli derives keys per step and per flow since v4.1.1 ([report](postmortems/2026-11-16-gate-rerun-idempotency-conflict.html)).
- [2026-11-19 gate claim reset not transport](postmortems/2026-11-19-gate-claim-reset-not-transport.md): the gate classifies a reset or a TCP i/o timeout as transport wherever it appears (node, SSE, the CLI's own claim or launch) and reports leaks before its verdict ([report](postmortems/2026-11-19-gate-claim-reset-not-transport.html)).
- [2026-11-21 gate ran function flows](postmortems/2026-11-21-gate-ran-function-flows.md): the gate skips function flows the tag matches (`ignore_modules`, default true), like monitors; a function run alone fails INPUT_REQUIRED ([report](postmortems/2026-11-21-gate-ran-function-flows.html)).
- [2026-11-25 per-push diff stranded backend](postmortems/2026-11-25-per-push-diff-stranded-backend.md): a push to the default branch diffs from the last green commit (`last-success-sha.yml` into detect-changes' `base_sha`), so a red run's changes ship with the next green push; callers run the lookup on every event ([report](postmortems/2026-11-25-per-push-diff-stranded-backend.html)).
