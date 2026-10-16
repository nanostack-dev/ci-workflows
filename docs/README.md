# Reusable workflow documentation

Start with [agent guidance](../AGENTS.md) and [vocabulary](../CONTEXT.md).

- [Architecture and contracts](technical/architecture.md).
- [Migration lint](technical/migration-lint.md): the safety linter for Postgres migrations, its rules, exclusions and opt-outs.
- [Setup](development/setup.md), [validation](development/testing.md), [troubleshooting](development/troubleshooting.md).
- [Publishing/consumer rollout](runbooks/deployment.md), [rollback](runbooks/rollback.md).
- [Architecture decisions](adr/README.md): [0001 migration lint](adr/0001-lint-migrations-with-squawk-and-custom-checks.md).
- [Self-hosted runner flakes](self-hosted-runner-flakes.md): existing evidence and prevention.

The workflow files own exact inputs/defaults; guides explain boundaries and how to verify consumers.
