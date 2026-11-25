# Reusable workflow architecture

| Workflow | Owned behavior |
| --- | --- |
| [go-build-test.yml](../../.github/workflows/go-build-test.yml) | Caller-configured Go lint/test suites and container publication. |
| [frontend-verify.yml](../../.github/workflows/frontend-verify.yml) | Frontend verification and affected Storybook/browser test planning. |
| [detect-changes.yml](../../.github/workflows/detect-changes.yml) | Backend/frontend boolean outputs from caller-defined glob patterns; full verification when comparison is unavailable. A push diffs against `base_sha` (the last green commit) when the caller passes one and it is an ancestor, else against the previous push. |
| [last-success-sha.yml](../../.github/workflows/last-success-sha.yml) | `sha` and `run_id` of the newest successful push run of the calling workflow on the default branch, for detect-changes' `base_sha`. Needs `actions: read` from the caller; never fails (empty output means "use the previous push"). |
| [echopoint-test.yml](../../.github/workflows/echopoint-test.yml) | API flow-suite verification through the declared Echopoint CLI Action. |
| [migration-lint.yml](../../.github/workflows/migration-lint.yml) | Safety lint of the Postgres migrations a pull request adds or modifies: pinned squawk plus custom checks. [Guide](migration-lint.md). |
| [dispatch-deploy-event.yml](../../.github/workflows/dispatch-deploy-event.yml) | Validated JSON event handoff to an explicitly configured private owner. |

A caller's `jobs.<name>.uses` binds a GitHub repository/ref; `with`, explicit secrets and caller permissions define the contract. Runtime deployment ownership stays outside this repository. The dispatch workflow requires both `deploy_repository` and `DEPLOY_TOKEN`: missing either prevents the handoff and fails the job so an unsent deployment or preview cleanup cannot appear successful.

## Change detection base on the default branch

A push run must cover every change since the last commit CI verified, not only its own push. A red run deploys nothing, so diffing the next push against `github.event.before` drops the red push's files: on 2026-11-25 echopoint #1006's backend never built because the three pushes after its red run were frontend-only, and the frontend-only deploy path shipped the new frontend to prod against the old API ([postmortem](../postmortems/2026-11-25-per-push-diff-stranded-backend.md)).

Callers opt in with two jobs:

```yaml
last_success:
  if: github.event_name == 'push'
  uses: nanostack-dev/ci-workflows/.github/workflows/last-success-sha.yml@main
  permissions:
    actions: read
detect_changes:
  needs: last_success
  if: ${{ !cancelled() }}   # last_success is skipped on pull requests
  uses: nanostack-dev/ci-workflows/.github/workflows/detect-changes.yml@main
  permissions:
    contents: read
  with:
    base_sha: ${{ needs.last_success.outputs.sha }}
```

The lookup is a separate workflow because a called workflow cannot ask for more than its caller grants: if `detect-changes.yml` itself asked for `actions: read`, every caller that grants only `contents: read` would fail at startup. A caller that does not opt in keeps the per-push diff. The detect log names the base it used (`Base: the last successful run's commit …` or `Base: the previous push …`). Once a run with the widened diff succeeds, its commit is the next base, so a green run always covers the red runs before it. The base stops at a run that succeeded under the old per-push diff, so the first push after opting in can still miss earlier stranded changes; check `/health` against `main` after opting in.

Source files are authoritative for required values and defaults. Avoid copying a workflow's full schema into a second maintained table. Read [runner flakes](../self-hosted-runner-flakes.md) before changing job concurrency/network or lint execution assumptions.

The flow-suite workflow selects an explicit workspace alongside the CI organization
and API key. The matching per-product `ECHOPOINT_CI_WORKSPACE_ID_<ENV>_<PRODUCT>`
(`ANCHOR`, `ECHOPOINT`, `ATELIER`) and fallback `ECHOPOINT_CI_WORKSPACE_ID_<ENV>`
fields belong to `infra-control-plane` in 1Password. Release the CLI Action with its
`workspace-id` input before workspace enforcement. The selected workspace must remain
linked to that control plane's CI organization. When `workspace_id` is omitted, the
workflow maps `tag` (`anchor`, `echopoint`, `atelier`) to the matching product
workspace field from 1Password, falling back to `ECHOPOINT_CI_WORKSPACE_ID_<ENV>`.

Callers that pin golangci-lint locally pass their committed version file through `go-build-test.yml`'s `lint_version_file` input. The lint action reads it relative to `lint_working_directory`, so local tooling and CI share one pin. An empty input preserves the workflow's pinned default for other callers; an invalid or missing requested file fails the lint action.

The lint job installs golangci-lint itself before the action runs (step `Install golangci-lint`): the version from the same source the action uses, downloaded with the workflow token, retried, checked against the release's SHA-256 list and kept in the runner tool cache. The action then runs that binary with `install-mode: none`. A version the step cannot handle exactly (a go.mod that names golangci-lint, an inexact version such as `v2.3`, an unknown platform, a missing file) leaves the install to the action, as before. The pinned default `v2.14.0` appears in both steps; bump both together.

Every tool or module download in these workflows retries transient failures, and nothing else is retried (see [CI principles](../ci-principles.md) section 2):

| Download | Where | Retry |
|---|---|---|
| Go modules (`go mod download`) | `go-build-test.yml` lint and tests jobs, `workflow-lint.yml`, `ci.yml` | 5 attempts, 5/10/20/40 s apart |
| `gotestsum`, `actionlint` (`go install`) | `go-build-test.yml` tests job, `workflow-lint.yml`, `ci.yml` | 5 attempts, 5/10/20/40 s apart; the lint itself runs once |
| golangci-lint release | `go-build-test.yml` lint job | `curl --retry 5 --retry-all-errors --retry-delay 5 --connect-timeout 20`, token first, then anonymous |
| squawk release | `scripts/migration-lint/install-squawk.sh` | 5 attempts with backoff, token first |
| Dagger CLI | `actions/setup-dagger` | `curl --retry 5 --retry-all-errors --retry-delay 5 --connect-timeout 20` |

`GOPROXY` keeps a value the runner sets and is otherwise Go's default, `https://proxy.golang.org,direct`. `GOFLAGS=-mod=mod` is deliberately not set: it lets a build rewrite `go.mod` and `go.sum` instead of failing on drift. The echopoint CLI (`nanostack-dev/echopoint-cli@v1`, used by `echopoint-test.yml`) retries its own downloads. `actions/setup-go`, `actions/setup-node`, pnpm and Playwright installs keep the retries those tools ship with.
