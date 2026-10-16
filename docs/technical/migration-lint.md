# Migration lint

[migration-lint.yml](../../.github/workflows/migration-lint.yml) fails a pull request that adds or changes a Postgres migration unsafe to run against a database serving traffic. It exists because review kept finding the same four defects in index and backfill migrations (anchor#234, echopoint#644). The decision to build on squawk plus a small custom check is in [ADR 0001](../adr/0001-lint-migrations-with-squawk-and-custom-checks.md).

## What it lints

Only the `*.sql` files the change **adds or modifies** under `migrations_dir`: `git diff --diff-filter=ACMR <base>...<head>`. Migrations are append-only, so the history would only add noise. The base is `base_ref`, else the pull request's base commit (the previous push for a push event). A base that cannot be resolved **fails** the job with exit status 2: linting nothing would pass migrations nobody checked, the same fail-open rule as [detect-changes](../../.github/workflows/detect-changes.yml).

`*.up.sql` files go through squawk and the custom checks; `*.down.sql` files go through the custom checks only. Down migrations are destructive by nature (`DROP TABLE`, `DROP COLUMN`) and run only on a rollback, so squawk's findings on them are noise.

## Calling it

```yaml
migration-lint:
  needs: detect_changes
  if: github.event_name == 'pull_request' && needs.detect_changes.outputs.backend_changed == 'true'
  uses: nanostack-dev/ci-workflows/.github/workflows/migration-lint.yml@main
  permissions:
    contents: read
  with:
    migrations_dir: migrations
    pg_version: '18'
    # Extra squawk rules to disable, with the reason beside them.
    # excluded_rules: identifier-too-long
```

Add the job to the caller's `ci-ok` `needs` and result loop so that one required check covers it; `skipped` counts as passing there, as for every other gated job. Inputs, defaults and the runner label are in the workflow file. Pin to `@main`, as the other consumers do, or to a commit SHA to hold a revision back.

## squawk

[squawk](https://github.com/sbdchd/squawk) is Apache-2.0, written in Rust, parses SQL with its own Postgres grammar (no database needed) and exits non-zero on a violation. It is installed by [install-squawk.sh](../../scripts/migration-lint/install-squawk.sh): release **2.68.0** (2026-10-08), pinned by version and by the SHA-256 of each platform binary, verified against the digest GitHub shows for the release asset and against a download. Linux gets the static musl build, so the runner image's glibc does not matter. The release is older than the 7-day cooldown of infra ADR 0004 D5. To bump it, change `SQUAWK_VERSION` and the four digests in that script, rerun the tests, and pick a release that is at least 7 days old.

The linter runs squawk with an empty `--config`, so a stray `.squawk.toml` in the caller cannot change the result: the workflow inputs are the only configuration.

### Rules that stay on

Everything squawk enables by default except the rules below. The ones that matter most here:

| Rule | Catches |
| --- | --- |
| `require-concurrent-index-creation` | Plain `CREATE INDEX` on an existing table: blocks writes for the whole build. One finding per statement, so a file of eleven plain indexes reports eleven. |
| `require-concurrent-index-deletion` | Plain `DROP INDEX`. |
| `constraint-missing-not-valid`, `adding-foreign-key-constraint` | A constraint added without `NOT VALID` scans the table under a write-blocking lock. |
| `adding-field-with-default`, `adding-required-field`, `adding-not-nullable-field`, `adding-serial-primary-key-field` | Column adds that rewrite the table or fail on existing rows. |
| `changing-column-type`, `disallowed-unique-constraint` | `ACCESS EXCLUSIVE` lock held for a rewrite or an index build. |
| `ban-drop-column`, `ban-drop-table`, `renaming-column`, `renaming-table`, `renaming-object` | A rolling deploy runs the old application against the new schema. See *Expand, then contract* in each application's engineering practices. |
| `transaction-nesting`, `ban-uncommitted-transaction`, `ban-concurrent-index-creation-in-transaction` | `BEGIN`/`COMMIT` inside a file golang-migrate already wraps. |
| `identifier-too-long` | A name Postgres silently truncates to 63 bytes. |

Run `squawk --help` or see the [rule index](https://squawkhq.com/docs/rules) for the rest.

### Rules switched off for every caller

`python3 scripts/migration-lint/migration_lint.py --migrations-dir . --list-base-exclusions` prints this list from the code.

| Rule | Why it is off |
| --- | --- |
| `require-lock-timeout`, `require-statement-timeout` | Their fix is a `SET lock_timeout` statement in the file. That second statement turns the file into a transaction and breaks `CREATE INDEX CONCURRENTLY`, which the custom check below requires to be alone. They fired 40 times on Anchor's existing up migrations and 80 times on Echopoint's. |
| `prefer-robust-stmts` | Asks for `BEGIN`/`COMMIT` around the file. golang-migrate already runs a file in one transaction, and a transaction block is what `CONCURRENTLY` cannot run in. Its `IF NOT EXISTS` advice is not a lock hazard, and on an INVALID leftover index it hides the failure. |
| `prefer-text-field`, `prefer-bigint-over-int`, `prefer-bigint-over-smallint`, `prefer-identity`, `prefer-timestamptz` | Style, not safety. Both applications use `varchar(n)` on purpose (the bounded sort columns of the cursor searches are `varchar(255)`). `prefer-text-field` alone fired 160 times on Anchor's existing up migrations and 93 on Echopoint's. |
| `ban-drop-constraint`, `ban-drop-not-null` | Relaxing a constraint is an expand-phase step that takes a brief lock. Data loss is still guarded by `ban-drop-column` and `ban-drop-table`. |

### Per caller and per statement

- `excluded_rules` input: extra rules to disable for one repository, comma or newline separated. Put the reason in a comment beside it. `included_rules` turns on an opt-in rule.
- `-- squawk-ignore <rule>[, <rule>]` on the line before a statement, or `-- squawk-ignore-file <rule>`: squawk's own opt-out. Prefer the statement form, and say why in the line above it.
- `pg_version`: the Postgres major version rules assume (both applications run 18).

### Findings squawk gets wrong, filtered by the linter

| squawk reports | The linter drops it when |
| --- | --- |
| `require-concurrent-index-creation` | the index is on a table the same file created with `CREATE TABLE` (empty, nothing to block), or on a known hypertable (squawk cannot see `transaction_per_chunk`; the `hypertable-index` check decides instead). |
| `adding-field-with-default` on a generated column | the column is `GENERATED ALWAYS AS (...) VIRTUAL`. squawk treats every generated column as `STORED`, which rewrites the table; a PostgreSQL 18 virtual column is metadata-only. A `STORED` one is still reported. |

## Custom checks

These cover what squawk cannot know, because it does not know how golang-migrate runs a file or what a hypertable is. Statements are split with a tokenizer that understands comments (including nested `/* */`), `'...'`, `E'...'`, `"..."` and `$tag$...$tag$`, so a semicolon or the word `UPDATE` inside a string, comment or function body does not count.

| Check | Fails when |
| --- | --- |
| `concurrently-alone` | A file with more than one statement contains a statement Postgres refuses inside a transaction block: `CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY`, `REINDEX ... CONCURRENTLY`, `ALTER TABLE ... DETACH PARTITION ... CONCURRENTLY`, or `CREATE INDEX ... WITH (timescaledb.transaction_per_chunk)` (TimescaleDB calls `PreventInTransactionBlock` for it). golang-migrate sends a multi-statement file as one query, which Postgres runs in an implicit transaction; one statement runs outside any. A `SET lock_timeout` or a `BEGIN` beside it counts as a second statement. **No opt-out**: the migration fails when applied otherwise. `REFRESH MATERIALIZED VIEW CONCURRENTLY` is allowed in a transaction and is not checked. |
| `update-backfill` | An `UPDATE` (alone, in a data-modifying CTE, or inside a `DO` block) targets a table the file did not create. It runs in one transaction and holds a row lock on every row until the migration ends, so a large table stalls writers. Updating a table created earlier in the same file is fine. |
| `unbounded-delete` | A `DELETE` has no `WHERE`, or a `WHERE` that is plainly true (`true`, `1 = 1`). A `DELETE` with a real `WHERE` passes; whether it matches too many rows is a review question. |
| `hypertable-index` | `CREATE INDEX` on a hypertable without `WITH (timescaledb.transaction_per_chunk)`, or with `CONCURRENTLY`, which hypertables do not support. Not raised for a hypertable the same file created. |
| `lint-opt-out` | A `-- lint: allow-...` comment names an unknown opt-out or gives no reason. A typo must not silently disable a check. |

Hypertables are found from the whole migrations directory, not just the changed files: `create_hypertable('name', ...)` (schema qualified or quoted names included, also inside `DO` blocks) and `CREATE TABLE ... WITH (tsdb.hypertable)` / `(timescaledb.hypertable)`. The `hypertables` input adds names no migration creates.

### Opt-out comments

```sql
-- lint: allow-backfill organization_settings has fewer than 1,000 rows in every environment
UPDATE organization_settings SET region = 'eu' WHERE region IS NULL;
```

| Comment | Silences |
| --- | --- |
| `-- lint: allow-backfill <reason>` | `update-backfill` and `unbounded-delete` |
| `-- lint: allow-hypertable-index <reason>` | `hypertable-index`, for example a unique index (TimescaleDB refuses `transaction_per_chunk` on one) or a hypertable with no chunks yet |

The comment applies to the **one statement** it sits above, or trails on the line of its `;`. The reason is required and is read by the reviewer; it is not validated. A comment that silences nothing is reported as a warning (`lint-opt-out-unused`) and does not fail the run.

## Running it locally

```bash
scripts/migration-lint/install-squawk.sh ~/.local/bin          # pinned, checksum verified
python3 scripts/migration-lint/migration_lint.py \
  --migrations-dir migrations --squawk ~/.local/bin/squawk --pg-version 18 \
  --base origin/main                                           # what this branch adds
# or exact files, whatever their history:
python3 scripts/migration-lint/migration_lint.py --migrations-dir migrations --files migrations/000086_x.up.sql
```

Exit status: 0 clean, 1 findings, 2 the linter could not run (no base, no squawk, unreadable file). In Actions each finding is also an annotation on the file and line, and the step summary lists them.

## Tests

[migration-lint-test.yml](../../.github/workflows/migration-lint-test.yml) runs on every change under `scripts/migration-lint/`: ShellCheck on the installer, the unit tests with the pinned squawk, and the reusable workflow itself against a clean fixture directory. Locally:

```bash
SQUAWK=~/.local/bin/squawk python3 -I -m unittest discover -s scripts/migration-lint/tests -v
```

Each file in `tests/fixtures/cases` declares its expected findings in its first lines (`-- expect-custom: ...`, `-- expect-squawk: ...`), so a new case is one file. `tests/fixtures/history` stands for the repository's earlier migrations (it declares the hypertables). Without a squawk binary the squawk cases are skipped, not passed.

## Verified against

Run with squawk 2.68.0 and `--pg-version 18` over the real cursor-search history, in the migrations directory of each repository:

| Migration | Result |
| --- | --- |
| anchor 000043 as first pushed in anchor#234 (`95bf938`): eleven plain `CREATE INDEX` in one file | 11 `require-concurrent-index-creation` findings |
| anchor 000043-000053 as merged | clean |
| echopoint 000083 and 000085 backfills as pushed in echopoint#644 (`4344dc47`): one `UPDATE` over `resource_search_documents` and `openapi_operations` | 2 `update-backfill` findings |
| echopoint 000084 and 000086 backfills of the earlier numbering (`293a0432`) | 2 `update-backfill` findings |
| echopoint 000065-000085 as merged | clean, with `identifier-too-long` excluded (see below) |

Echopoint excludes `identifier-too-long` because its merged `000083` index is named with 69 bytes. Postgres truncates the name identically in `CREATE INDEX` and `DROP INDEX`, so the down file still works.
