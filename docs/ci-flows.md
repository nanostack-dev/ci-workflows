# CI flows: what each workflow file must do

The intended flow of every CI file in the nanostack-dev organization. Use it
to review a change to a workflow: if the file no longer does what its entry
says, either the file or this page is wrong. The rules behind the flows are in
[ci-principles.md](ci-principles.md).

Notation: `→` is "then", `∥` is "in parallel". Runner labels are in
[Runner layout](ci-principles.md#runner-layout).

## The shape every product repository follows

```text
pull_request (every PR, no paths filter)
  changes ─┬─ gate: one local command (dagger check | go test + lint) ─┐
           ├─ migrations: append-only + migration-lint (PR only)       ├─ ci-ok (required)
           └─ image publish (when a deployable path changed)           ┘
push to main
  same jobs → dispatch deploy-service to infra (only if gate and image succeeded)
pull_request edited/closed
  preview.yml → ci-workflows preview.yml (raise / tear down the preview)
pull_request touching .github/**
  workflow-lint.yml → actionlint + ci-lint
```

## ci-workflows (shared, public)

| File | Trigger | Flow | Must keep |
|---|---|---|---|
| `ci.yml` | PR, push main | `workflow-lint` (go test ci-lint, ci-lint on itself, actionlint) ∥ `unit` (migration-lint fixtures, shellcheck) ∥ `reusable-workflow` (migration-lint on clean fixtures) | No paths filter: every job is under a minute |
| `workflow-lint.yml` | workflow_call | checkout caller ∥ checkout ci-workflows at `job.workflow_sha` → actionlint (labels config) → ci-lint | Tools from the Go module proxy, never a github.com binary |
| `preview.yml` | workflow_call from `<repo>/preview.yml` | decide from the event file → `up`: re-run the PR's last build run · `down`: dispatch `preview-destroy` | Never cancelled; closed PR with checkbox off dispatches nothing (1Password read budget); fork PRs skipped |
| `detect-changes.yml` | workflow_call | glob the PR diff against backend/frontend patterns → outputs | Runs on every PR (it is what lets `ci-ok` stay required) |
| `dispatch-deploy-event.yml` | workflow_call | validate JSON → `repository_dispatch` to infra | Empty `DEPLOY_TOKEN` fails the job (it used to skip silently) |
| `migration-lint.yml` | workflow_call | squawk + custom rules on the migrations a PR adds or edits | PR only; pinned squawk downloaded with a token |
| `echopoint-test.yml` | workflow_call from infra deploys | run a tag of Echopoint flows against an environment with the released CLI | The post-deploy gate. Retries transport resets (postmortem 2026-11-05) |
| `go-build-test.yml`, `frontend-verify.yml` | workflow_call from atelier only | lint ∥ tests ∥ image; frontend verify with the Vitest watchdog and private network namespace | Delete both when atelier moves to Dagger; first port the watchdog and netns fixes into the Dagger modules |
| `actions/setup-dagger` | composite | install the pinned CLI (checksum) into the runner tool cache → set `DAGGER_ENGINE` | One `DAGGER_ENGINE` string per host: two strings kill each other's engine |

## echopoint (private)

| File | Trigger | Flow | Must keep |
|---|---|---|---|
| `go.yml` | PR (no paths), push main (paths), dispatch | `detect_changes` → `dagger-check` (every check except storybook-test and motion) ∥ `dagger-publish` ∥ `migrations-verify` ∥ `migration-lint` → `ci-ok`; push main: → `dispatch-deploy-dev` or `dispatch-frontend-deploy-dev`; PR: `preview-flag` → `dispatch-preview-upsert`; PR: `frontend-tests` (not required) after `dagger-check` | `queue: max` on main pushes (deploys in merge order); `ci-ok` required; deploys gate on `dagger-check` |
| `preview.yml` | PR edited/closed | → ci-workflows `preview.yml` (service echopoint) | Stacked PRs may own previews |
| `anchor-pin.yml` | daily, dispatch | resolve `anchor:latest` digest → if new: commit to `chore/anchor-pin` → PR → `go.yml` dispatch on the branch | Needs "Allow GitHub Actions to create pull requests" for the PR step |
| `frontend-full.yml` | nightly, dispatch | full `storybook-test` + `motion` (every story) | Not a gate; its failures are the Storybook backlog |
| `cloud-worker.yml` | push main (cloudworker paths), dispatch | `cloudworker-*` checks (cache hits of go.yml) → wrangler deploy dev → prod | No PR trigger (go.yml runs those checks). Reaches prod without the flow gate |
| `email-worker.yml` | push main (paths) | checks → wrangler deploy | Reaches prod without the flow gate |
| `integration-drift.yml` | daily | per integration: regenerate from its spec → PR when it drifted | `setup-go` cache off (shared GOMODCACHE) |
| `workflow-lint.yml` | PR touching .github | → ci-workflows `workflow-lint.yml` | |

## anchor (public)

| File | Trigger | Flow | Must keep |
|---|---|---|---|
| `go.yml` | PR, push main | `detect_changes` → dagger frontend ∥ dagger backend ∥ publish ∥ migration-lint → `ci-ok`; push main → dispatch deploy | Hosted runners (public repo): Dagger is cold every run, ≈ 11 min |
| `e2e-app.yml` | PR | isolated browser app suite | Reads git history, so it stays a workflow job |
| `release-client.yml` | push main (clients/go) | compute next `clients/go/vX.Y.Z` from commits → tag | |
| `preview.yml` | PR edited/closed (base main) | → ci-workflows `preview.yml` (service anchor, `ubuntu-latest`) | |
| `workflow-lint.yml` | PR touching .github | → ci-workflows `workflow-lint.yml` | |

## infra (private): deploy control plane

Unchanged in this refactor except where noted: seven ADR 0008 pull requests
(#303–#308) rework the same files. See the decision in the refactor report.

| File | Trigger | Flow | Must keep |
|---|---|---|---|
| `router.yml` | repository_dispatch | guard payload → per service: `<service>-deploy` dev → (promote_to_prod && dev green) → prod; previews → `<product>-preview`; any failure → Discord | `queue: max` per service (merge order) |
| `anchor-deploy.yml`, `echopoint-deploy.yml` | workflow_call | typecheck ∥ `deploy-swarm-service` ∥ wrangler upload → promote worker → `echopoint-test` gate (dev) | Merge candidates: they differ only in names and keys |
| `echopoint-runner-deploy.yml`, `atelier-deploy.yml`, `echopoint-mock-api-deploy.yml` | workflow_call | `deploy-swarm-service` (runner: dev → prod; others dev only) | runner reaches prod with no flow gate |
| `anchor-preview.yml`, `echopoint-preview.yml`, `preview-pr.yml` | workflow_call | preview stack up/down + Cloudflare preview worker (+ PR comment for echopoint) | |
| `preview-gc.yml` | nightly | remove previews of closed PRs | Safety net for `preview.yml` |
| `deploy-swarm-service.yml` | workflow_call | 1Password → render env → verify image → tailnet → `docker stack deploy` → verify checksum and replicas → secret GC; on failure roll back | |
| `deploy-shared.yml`, `deploy-shared-on-otel-change.yml` | dispatch / push main (otel paths) | shared stack dev → prod | Merge candidate (the second is a 40-line wrapper) |
| `deploy-wrangler-frontend.yml`, `promote-worker-version.yml`, `frontend-typecheck.yml` | workflow_call | build/upload worker version → promote | |
| `deploy-observability.yml` | push main (paths), dispatch | deploy the ops cluster | |
| `security-images.yml` | push main (paths), PR (paths), dispatch | per image: trivy (downloaded with a token) → build → scan → publish (main) | Push limited to main (a branch push used to publish) |
| `db-backup.yml` | daily, PR (paths) | PR: script tests (`nanostack-light`) · daily: backup on 8845hs | |
| `stacks-verify.yml` | PR (paths) | template variables ∥ Postgres lock metrics | Moved off GARM to `nanostack-dev` |
| `disk-gc.yml`, `ops.yml`, `pulumi.yml`, `terraform.yml`, `atelier-terraform.yml`, `echopoint-terraform.yml`, `ansible.yml`, `secrets.yml`, `cloudflare-billing-guards.yml` | schedule / dispatch / push (paths) | the named operation, dev or prod by input | `echopoint-terraform` apply-prod has no job-level environment |
| `garm-runner-image.yml` | PR (paths) | verify the GARM runner image | Delete with GARM if the pool is turned off |
| `workflow-lint.yml` | PR touching .github | → ci-workflows `workflow-lint.yml` (extra label `nanostack-ci`) | |

Deleted: `anchor-test.yml` (last run 2026-08-05, 10 of 12 failed; replaced by
the `echopoint-test` gate) and `claude.yml` (9 of 9 runs skipped).

## marketing (private)

| File | Trigger | Flow | Must keep |
|---|---|---|---|
| `ci.yml` | PR, push main, dispatch (site) | `dagger-check` (all sites) ∥ `changes` (sites changed since `before`) → `release` per changed site: build with the production URL → test the built site → wrangler deploy | Release gated on the same commit's checks; one production concurrency group per site |
| `workflow-lint.yml` | PR touching .github | | |

Replaced: `check.yml`, `release-echopoint.yml`, `release-cadastre.yml`,
`release-rempart.yml` (each release re-ran the checks). Deleted: `claude.yml`.

## Smaller repositories

| Repo | File | Flow |
|---|---|---|
| HomeScanner (private) | `ci.yml` | build (React + Rust, now `nanostack-dev`, not GARM) ∥ container check (Dagger) → docker push → dispatch deploy (dev only) |
| echopoint-mock-api (private) | `ci.yml` | PR: build and vet (`nanostack-light`, not GARM) · push main: deploy dev |
| atelier (private) | `go.yml` | detect → ci-workflows frontend-verify ∥ go-build-test ∥ migrations → `ci-ok` → dispatch deploy |
| echopoint-runner (public) | `go.yml`, `release.yml` | lint ∥ tests → image → dispatch deploy · push main: tag (minor bump) → goreleaser. Note: a runner merge releases and deploys with no flow gate (AGENTS.md rule on capabilities) |
| echopoint-cli (public) | `go.yml`, `release.yml`, `action-smoke.yml` | lint, race tests, cross builds · tag → goreleaser → move major tag · action smoke on 3 OSes. Deleted `action-sandbox.yml` (14 of 14 runs skipped) |
| echopoint-kit, pgkit, cron, terraform-provider-anchor, nanostack-framework, nanostack-design-system (public) | `ci.yml`/`test.yml`, `release*.yml`, `db.yml` | lint + tests on hosted runners · releases on tag or main |
| orchard (private) | none | Deleted `ci.yml`: macOS-hosted runner in a private repo (blocked by billing), 2 of 2 runs failed in 5 s. Needs a self-hosted macOS runner to come back |

Every repository with workflows also has `workflow-lint.yml`.
