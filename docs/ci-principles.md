# CI principles

The rules every nanostack-dev workflow follows, why each exists, and the
incident or measurement behind it. `cmd/ci-lint` enforces the ones a machine
can check; `workflow-lint.yml` runs it on every pull request that touches
`.github/`. [ci-flows.md](ci-flows.md) describes what each workflow file does.

Read this before you add or change a workflow.

## 1. One command is the gate, and it runs anywhere

Each repository has one local command that is its CI: `dagger check` for the
Dagger repositories (echopoint, anchor, marketing, nanostack-design-system,
HomeScanner), `go test ./...` plus `golangci-lint run` for the Go libraries.
The workflow is a thin wrapper around it.

- It runs the same on the Mac (arm64) and on `1340p` (x86_64). The devbox
  runner proves the arm64 path in CI: the 2026-11-11 benchmark ran echopoint's
  full `dagger check` there.
- Merge on local green is the standing rule (CLAUDE.md). It only holds if the
  local command and CI are the same command.

## 2. Tests are hermetic: no moving external input

A check's result depends only on the commit.

| Rule | Incident |
|---|---|
| Pin service images by digest, and bump the pin in a pull request | echopoint ran `anchor:latest`. An Anchor merge broke 11 echopoint runs on 2026-11-10 that changed no echopoint code. Dagger also reused results cached against an older Anchor. Fixed: `cmd/it/anchorfixture/anchor-image.txt` plus `anchor-pin.yml`. |
| Never download from github.com anonymously; send a token and retry | GitHub throttles anonymous release downloads during incidents: 7 failed deploy-gate attempts (echopoint-cli, 2026-11-09), a 504 on `apispec.wasm`, a 504 on squawk. ci-lint rule `anonymous-github-download`. |
| No test against the shared dev environment in a pull request gate | Gate flows on dev fail on dev's own bugs, limits and locks (infra postmortems 2026-11-02, 11-03; skills postmortems). They stay as the post-deploy gate, not the PR gate. |

## 3. Self-hosted runners: no shared mutable cache owned by an action

The `1340p` slots share `GOMODCACHE`, the Go build cache and the pnpm store on
the host. These are already warm.

- `actions/setup-go` and `actions/setup-node` caches restore a tarball into
  that shared directory. Two jobs at once collide: echopoint integration-drift
  failed 2 of its last 5 runs with `Cannot open: File exists` (2026-11-10/11).
  Rule `setup-cache-self-hosted`: `cache: false`, or
  `cache: ${{ runner.environment == 'github-hosted' }}`.
- The Dagger CLI is cached in the runner tool cache (`setup-dagger`), so it is
  downloaded once per host and version.

## 4. One heavy job per host

A heavy job is one that runs `dagger check` with browser tests or
testcontainers. Its containers run outside the runner slot's `MemoryMax`
(Docker puts them in their own cgroups), so slot limits do not bound it.

Measured on 2026-11-11, echopoint full `dagger check` with every cache busted
(details in [Measurements](#measurements)):

| Case | Wall time | Host |
|---|---|---|
| devbox (M2, one Lima VM) alone | see Measurements | 16 GB VM |
| 1340p alone | see Measurements | load ≈ 20, engine ≈ 16 GiB |
| 1340p, two jobs at once | see Measurements | load 92–95 on 16 threads, 2 GB free, engine 18.8 GiB, dev Swarm on the same host |

Two jobs at once on `1340p` are slower than two jobs in sequence and fail
checks that pass alone. Rule: `1340p` carries the `nanostack-dagger-pool`
label on one slot only; the devbox is the second slot. See
[Runner layout](#runner-layout).

## 5. Required checks: one `ci-ok`, no `paths` on `pull_request`

A workflow skipped by a `paths` filter creates no check run, so a required
check stays pending forever. A job skipped by `if:` reports success. Rule
`required-check-paths`: a workflow with a `ci-ok` job has no `paths` on
`pull_request`; a changes job gates the expensive jobs, and `ci-ok`
(`if: always()`) fails when any needed job failed or was cancelled.
Source: GitHub, "Troubleshooting required status checks".

## 6. Least privilege and pinned code

- Top-level `permissions: {}` (or read-only); each job grants what it needs
  (rule `permissions-top`). Limits the blast radius of a compromised action
  (tj-actions/changed-files, 2025).
- Third-party actions are pinned to a full commit SHA with the version in a
  comment (rule `pin-actions`). This org's reusable workflows track `@main`
  on purpose: one change reaches every repository.
- Every job has `timeout-minutes` (rule `job-timeout`). The default is 360
  minutes; a hung job holds a slot that long.
- Private repositories never use GitHub-hosted runners (rule `runner-label`):
  the 2026-10-13 spending-limit freeze stopped every private job.

## 7. Flakes are fixed or removed, never retried into green

- No blanket retries. A test that passes on retry is a flake: it gets an
  owner, or it leaves the gate.
- Measure flakiness as "attempt 1 failed, a rerun on the same commit passed".
  Before this refactor: echopoint 9.1 % of runs (23 of 254, 6 days),
  atelier 9.8 %, nanostack-framework 3.2 %, anchor 2.6 %
  (`gh run list`, 2026-11-11).
- Since 2026-10-21 agents ran `gh run rerun` about 218 times (transcripts).

## 8. Flaky by design (decisions for Alexis)

These checks fail for reasons outside the code under test. Each needs a
decision: keep it in the PR gate, move it out (nightly or local), or replace it.

| Check | Evidence | Recommendation |
|---|---|---|
| echopoint `storybook-test` (Vitest browser mode, 1,481 stories) | Failed in 15 of the last 53 failed echopoint runs. Storybook's own docs say "Failed to fetch dynamically imported module" and iframe errors occur "in CI environments when running a large number of tests simultaneously". Failed 3 of 3 atelier runs that shared the engine. | Out of the PR gate. Keep `storybook-build` required (it catches compile errors). Run the stories a change reaches locally and the full suite nightly (`frontend-full.yml`). You said on 2026-11-09: "I think I will drop storybook on the CI and keep it only local". |
| echopoint `browser-app` (full stack in Docker-in-Docker: backend build, Anchor, Postgres, Redis, Mailpit, WireMock, cloud worker, real Clerk) | Failed in 27 of 53 failed runs: 11 from `anchor:latest` (fixed by the pin), at least 3 webServer boot timeouts (15 min, cloud worker health), 1 GitHub 504, and real test failures. | Keep, now hermetic. Revisit after two weeks of data with the pin. If boot timeouts remain, move it to post-merge on `main`. |
| echopoint `motion` (viewport animation checks on 3 viewports) | Failed in 6 of 53. Timing-based by nature. | Same as Storybook. |
| Post-deploy gate flows against shared dev | See principle 2. | Keep as a deploy gate; never as a PR gate. |
| `tailscale/github-action` in CI | Can log the host itself out of the tailnet (infra github-runners.md). | Keep only in infra deploy jobs. |

## Runner layout

Decided with Alexis on 2026-11-11. 1340p serves dev websites to the internet,
so it holds no secrets. The Mac (M2 devbox) is not reachable from the
internet, so it is the only place a deploy token lives.

| Host | Role | Labels | Holds secrets |
|---|---|---|---|
| 1340p | Builds and tests | `nanostack-light` (seconds-long jobs), `nanostack-dev` (builds), `nanostack-dagger-pool` on r1 only (one heavy job) | No. No 1Password token, no deploy key |
| M2 devbox, job VM | Builds and tests: one throwaway Lima VM per job, pf fence (no tailnet, no LAN) | `nanostack-dagger-pool` | No |
| M2 devbox, deploy runner | Every deploy, dev and prod, previews, infra operations, prod backups. Never runs pull request code | `nanostack-deploy` | Yes: the 1Password token, in a root-owned file on the Mac, not in GitHub secrets |
| 8845hs | Prod host only. No GitHub runner: it is internet-facing | none | Its own service secrets |
| GitHub-hosted | Public repositories | `ubuntu-latest` | No |

Rules:
- A job that reads a secret runs on `nanostack-deploy`.
  Nothing else. ci-lint enforces it (planned rule `secret-runner`).
- `nanostack-dagger-pool` takes at most one heavy job per host: 1340p-r1 and
  the Mac's job VM. The lighter Dagger checks (marketing, HomeScanner, design
  system) stay on `nanostack-dev`.
- Removed: GARM and Incus (`nanostack-ci`), the `nanostack-dagger` label, and
  every 1Password read on 1340p.
- No GitHub runner on an internet-facing host (1340p, 8845hs). Prod is deployed from the Mac over the tailnet, through the restricted `deploy@8845hs` entry point of infra ADR 0008 (forced command, `from=` the Mac's tailnet address).
- The Mac holds the keys to prod. Condition before prod secrets move there: FileVault on (manual unlock after reboot) or an accepted weaker alternative. Decided by Alexis.
- Removed: the `nanostack-prod` runner on 8845hs.
- When the Mac is off, deploys queue until it is back; builds continue on 1340p.

## Measurements

Benchmark: echopoint `ci/bench-flake`, `go.yml` replaced by a cache-busted full
`dagger check` (a comment appended to one frontend and one Go file per run),
dispatched 5 rounds × {1340p alone + devbox, 1340p pair}. Raw logs: the run
IDs below. Results are filled in by the benchmark report.
