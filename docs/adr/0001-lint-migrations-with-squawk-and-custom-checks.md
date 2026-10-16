# 0001. Lint migrations with squawk and a small custom check

Status: accepted (2026-10-15)

## Context

Shipping the cursor-search standard (anchor#234, echopoint#644) produced four migration defects that only review caught:

- several plain `CREATE INDEX` statements in one file, one transaction, each taking a write-blocking lock on a large table;
- a backfill that ran as one `UPDATE` over a large table;
- `CREATE INDEX CONCURRENTLY` sharing a file with another statement, which fails because golang-migrate sends a multi-statement file as one query and Postgres runs it in an implicit transaction;
- an index on a TimescaleDB hypertable, which has no `CONCURRENTLY` and needs `WITH (timescaledb.transaction_per_chunk)`.

Anchor and Echopoint share this CI repository. A check belongs here once, not in each application.

## Decision

[migration-lint.yml](../../.github/workflows/migration-lint.yml) runs on the migrations a pull request adds or modifies, in two layers: [squawk](https://github.com/sbdchd/squawk) for lock and rewrite hazards, and [migration_lint.py](../../scripts/migration-lint/migration_lint.py) for the checks squawk cannot make. [Migration lint](../technical/migration-lint.md) owns the rules, the exclusions and their reasons, and the opt-out comments.

- squawk is installed from a release binary pinned by version and SHA-256 ([install-squawk.sh](../../scripts/migration-lint/install-squawk.sh)), as D5 of infra ADR 0004 requires of third-party code, at a release older than 7 days.
- The custom checks are Python 3 standard library only: `concurrently-alone`, `update-backfill`, `unbounded-delete`, `hypertable-index`. They read a small SQL tokenizer, not a regex over lines.
- Findings squawk gets wrong for these applications are filtered in the same script: an index on a table the file just created, an index on a hypertable, a PostgreSQL 18 `VIRTUAL` generated column.
- Style rules and the two `require-*-timeout` rules are off for everyone. The timeout rules would add a second statement to a `CONCURRENTLY` file.
- Only changed files are linted. An unresolvable base fails the job.

## Alternatives

- **squawk alone.** It does not know the golang-migrate file model, so it passes `SET lock_timeout; CREATE INDEX CONCURRENTLY` (a runtime failure), has no backfill check, and reports a hypertable's `transaction_per_chunk` index as a plain `CREATE INDEX`.
- **The squawk GitHub Action or `upload-to-github`.** Comments on the PR and needs a token with write access; this job only reads. A pinned binary is easier to hold to the pinning rules and runs identically on a laptop.
- **Equivalent checks written from scratch.** squawk already encodes the Postgres lock matrix (`constraint-missing-not-valid`, `changing-column-type`, `adding-field-with-default`, and others) and is maintained against new Postgres versions.
- **Running the migrations against a database in CI.** The integration suites already do, on an empty database. Lock behavior needs a loaded one, which this does not provide.
- **Linting every migration.** Migrations are append-only, so history can only fail on things already shipped. Run over the whole history with the shared rule set, the linter reports 58 findings in Anchor and 106 in Echopoint, all in migrations that shipped long ago. A check that starts red trains people to ignore it.

## Consequences

- A migration that passes can still be slow: the linter cannot know a table's size. `update-backfill` flags every `UPDATE` of an existing table and `allow-backfill` records the reviewer's judgement in the diff.
- squawk is a third-party binary executed on the runners. The bump procedure is in the installer's header and the technical guide.
- A caller that needs another rule off adds it to `excluded_rules` and states why. Echopoint excludes `identifier-too-long` for its 69-byte `000083` index name.
- Wiring a caller's `ci-ok` to this job makes it a required check there. GitHub branch protection is outside this repository.
