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
| devbox (M2, one Lima VM) alone | median 247 s (240–375), 0 of 5 failed | 16 GB VM |
| 1340p alone | median 297 s (287–325), 1 of 5 failed (one browser-app test) | peak load 37, 5 GB free, engine 17.7 GiB |
| 1340p, two jobs at once | median 671 s (459–840), 7 of 10 failed | peak load 335 on 16 threads, 0 GB free, engine 21.3 GiB, dev Swarm on the same host |

Two jobs at once on `1340p` take longer than the same two jobs in sequence
(671 s each against 2 × 297 s) and fail checks that pass alone: Storybook
failed 5 of 10 times in the pair and 0 of 10 times alone (1340p and devbox). Rule: `1340p` carries the `nanostack-dagger-pool`
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

## 8. Suspected flaky by design

These checks fail for reasons outside the code under test. Each needs a
decision: keep it in the PR gate, move it out (nightly or local), or replace it.

| Check | Evidence | Recommendation |
|---|---|---|
| echopoint `storybook-test` (Vitest browser mode, 1,481 stories) | Failed in 15 of the last 53 failed echopoint runs. The benchmark shows why: 0 of 10 failures when its job runs alone on a host, 5 of 10 when two heavy jobs share 1340p. Storybook's docs name the same cause: errors "in CI environments when running a large number of tests simultaneously". Failed 3 of 3 atelier runs that shared the engine. | Contention, not design. Decided 2026-11-11: stays in the required gate; one heavy job per host keeps it green. |
| echopoint `browser-app` (full stack in Docker-in-Docker: backend build, Anchor, Postgres, Redis, Mailpit, WireMock, cloud worker, real Clerk) | Failed in 27 of 53 failed runs: 11 from `anchor:latest` (fixed by the pin), at least 3 webServer boot timeouts (15 min, cloud worker health), 1 GitHub 504, and real test failures. | Keep, now hermetic. Revisit after two weeks of data with the pin. If boot timeouts remain, move it to post-merge on `main`. |
| echopoint `motion` (viewport animation checks on 3 viewports) | Failed in 6 of 53; 0 of 15 in the benchmark (alone or paired). | Stays in the required gate (same decision as Storybook). |
| anchor `e2e-app`: `email.e2e.ts` "email examples wait for saved data" | Fails with `route.fulfill: Fetch response has been disposed` at 2 workers (2026-11-10) and at 3 (2026-11-11): the test holds the examples GET with `page.route`, most likely the app drops that request, and the held response is gone before `fulfill`. | A test bug, not load. Fix the test: fulfill only a request that is still live, or hold the response in the app's API mock. |
| anchor `e2e-app`: `templates.e2e.ts` 8 s action timeout | Only at 3 or more Playwright workers on the 4 vCPU runner (1 run in 8 at 3, 1 in 5 at 4); never at 2. | Contention. Keep 2 workers. |
| Post-deploy gate flows against shared dev | See principle 2. | Keep as a deploy gate; never as a PR gate. |
| `tailscale/github-action` in CI | Can log the host itself out of the tailnet (infra github-runners.md). | Keep only in infra deploy jobs. |

## 9. Spend wall time only on the critical path

Measure a job before you change it, then shorten the longest path, not the
average. The 2026-11-11 pass (numbers in [Job durations](#job-durations)):

- **Cold runners: spread the work.** A GitHub-hosted runner starts cold, so
  each check pays engine start and a cold compile, about 130 s. On one 4 vCPU
  runner, checks that run together slow each other down: anchor's
  component-tests took 4m35s alone and 10m41s next to the other backend
  checks. Public repositories get hosted runners for free, so give each heavy
  check its own runner (a matrix job), and split a suite that is still the
  longest into parts (anchor `component-tests-a` to `-h`, each fails unless
  every test it selected ran).
- **Hosted runners: restore the caches a laptop keeps.** In Dagger every
  hosted anchor run compiled from scratch: lint 225–282 s, each Go test group
  205–268 s. Run natively instead (`scripts/lint.sh`, `scripts/go-test-part.sh`,
  the same scripts the Dagger checks call) and restore Go's build cache, test
  cache and golangci-lint's cache per matrix leg. Two traps: Go replays a test
  result only when the files and directories the test opened have the same
  size and mtime, and a checkout gives every file a new mtime. So
  `scripts/date-by-content.py` dates each file by its blob hash and each
  directory by its tree hash, in the past (Go ignores inputs that look too
  new). And `CGO_ENABLED` is part of the cache keys: set it the same way in
  every run. Result, when no Go file changed: the lint job 34–41 s, each
  test job 23–34 s (see the next two principles for a Go change).
- **Image builds: build the binary where the caches are, package it in the
  image.** Inside Buildx a Go build cache must be copied into the builder
  first (`buildkit-cache-dance`: 27 s for 207 MB on every run) and the
  modules download again whenever the layer cache misses (12 s). anchor's
  `publish` now runs `scripts/build-anchor.sh` natively with Go's caches
  restored, and passes the binary to the Dockerfile with `--build-context
  binary=<dir>`, which replaces its `binary` stage: the builder stage does not
  run. publish: 94–125 s → 56 s (no Go change), 87 s (Go change, of which 33 s
  compile). The Dockerfile still builds from source for laptops, Dagger and
  fork PRs, with the same script and a check that its Go version equals
  go.mod's toolchain.
- **Time a change that touches code, not only a rerun.** A rerun of the same
  commit replays every test and every layer, so it shows the floor, not the
  common case. anchor's component parts took 23–34 s on a rerun and 77–115 s
  after a change to a package 53 others import: 31–50 s compiling the test
  binary on 4 vCPU and 31–73 s running the tests. Eight parts instead of
  five brought them to 54–89 s. `TestClerkReconcileSkipsADisabledInstance`
  waited a fixed 12 s alone before the parallel tests; it now ends when the
  queue settles (about 2 s).
- **Warm runners: keep state between runs.** A persistent self-hosted slot
  keeps what a cold one rebuilds. HomeScanner keeps Cargo's target directory in
  the slot's `HOME` (not the workspace, which checkout cleans): clippy, tests
  and the release build went from 209 s to under 15 s. A slot's first run is
  still cold: 162–217 s of Rust (measured on 3 slots).
- **One cache per build that differs.** A matrix whose legs share one cache key
  keeps whichever leg saved first. nanostack-framework's 16 DB jobs shared
  setup-go's `go.sum` key, so a SQLite job's cache served the postgres race
  builds, which compiled from scratch. A key per package and race flag cut the
  longest job from 194–217 s to 123 s.
- **Fresh statistics before query-heavy tests.** A table filled just before the
  test has no planner statistics. MariaDB planned the keyset contract's
  correlated subqueries badly until `ANALYZE TABLE`: 46 s → 11 s.
- **Independent suites run in parallel.** Browser suites that each seed their
  own fixture and start their own server do not need to wait for each other
  (HomeScanner: one server per route viewport, 182 s → 46 s).
- **Count failures, not only minutes.** Playwright on anchor's 4 vCPU runner:
  3 workers cut the tests from a median 3.4 to 2.8 min and 4 workers to 2.7
  min, but both made `templates.e2e.ts` time out on an 8 s action (1 run in 8,
  1 in 5), which never happened at 2 workers. Five clean runs proved nothing:
  the flake showed up in runs 6 to 8. anchor stays at 2 workers.
- **Prefer the arm runners for compile-heavy hosted jobs.** For public
  repositories `ubuntu-24.04-arm` is free and compiled Go 10-30 % faster
  than `ubuntu-latest` (anchor, 2026-11-12), with less spread between runs.
  Keep the architecture in cache keys, and keep jobs that build an amd64
  image on x64.
- **Self-hosted heavy jobs are CPU-bound: spread them over hosts.** On one
  host, reordering echopoint's checks only moved the tail (`dagger check`
  starts checks in a fixed order) and 8 checks at once was no faster than 4.
  Two parts on the two heavy hosts cut the run from 272–277 s to 169–171 s.
  Balance the parts by measured time: a first split ran 188–199 s because one
  part took 30 % longer than the other.

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
- The Mac holds the keys to prod. FileVault stays off so the Mac comes back unattended after a reboot (Alexis, 2026-11-11). Accepted risk: physical access to the Mac gives the deploy token. Controls: the token is a 1Password service account scoped to the items deploys read, stored in a root-owned file readable only by the deploy runner's user; if the Mac is lost or opened, revoke the service account in 1Password first.
- Removed: the `nanostack-prod` runner on 8845hs.
- When the Mac is off, deploys queue until it is back; builds continue on 1340p.

## Measurements

Benchmark, 2026-11-11 15:19–17:00 UTC: echopoint branch `ci/bench-flake`,
`go.yml` replaced by a full `dagger check` with every cache busted (a comment
appended to one frontend and one Go file per run, no changed-files list, so
all 1,481 stories ran). 5 rounds, each: one job on 1340p and one on the devbox
at once, then two jobs on 1340p at once. A sampler on 1340p recorded load,
free memory and engine memory every 15 s.

| Case | Runs | Median | Range | Failed | Failing checks |
|---|---|---|---|---|---|
| devbox alone | 5 | 247 s | 240–375 s | 0 | none |
| 1340p alone | 5 | 297 s | 287–325 s | 1 | browser-app (status-page tests, round 1) |
| 1340p pair | 10 | 671 s | 459–840 s | 7 | storybook-test 5, browser-app 5, go-test 2, browser-tooling 1 |

Flake rate before this refactor (attempt 1 failed, a rerun of the same commit
passed; `gh run list`, 2026-11-11): echopoint 9.1 % (23 of 254 runs in 6
days), atelier 9.8 %, nanostack-framework 3.2 %, anchor 2.6 %,
homescanner 1.8 %, design system 1.1 %, echopoint-runner 0.7 %,
echopoint-cli 0.6 %.

Failing checks in the last 53 failed echopoint `go.yml` runs (devbox proof
runs excluded): browser-app 27 (11 of them `anchor:latest`), go-test 15,
storybook-test 15, api-client/stale 7, motion 6, go-lint 4. No
`ERR_NETWORK_CHANGED` and no dynamic-import failure inside Dagger; 3 runs were
OOM-killed (exit 137).

### Job durations

The longest jobs before and after the 2026-11-11 pass. Before: median of the
successful runs of the previous week (`gh api .../actions/runs`). After: runs
of the `ci/refactor` branches.

| Repository: job | Before | After | Change |
|---|---|---|---|
| anchor `go.yml`, whole run | 763 s (one `dagger-backend` job) | 89–117 s with no Go change; about 2 min after a change to a widely imported Go package | backend and frontend checks on parallel hosted runners; lint and Go tests native with restored caches (23–41 s per job when results replay); component tests in 8 parts; Storybook in 4 shards with a cached browser (45–69 s); publish builds the binary natively (56 s, 87 s after a Go change) |
| anchor `e2e-app` | 264–385 s (median 288, 7 runs) | 203–248 s | 2 shards of 2 Playwright workers. 3 or 4 workers on one runner saved about 30 s but added an 8 s timeout flake in `templates.e2e.ts` (see principle 8) |
| HomeScanner `React and Rust checks` | 352 s | 75–84 s on a warm slot (11 runs on 4 slots passed; 1 more failed uploading its screenshots: GitHub's artifact service answered HTML) | Cargo target directory kept in the slot (Rust 209 s → under 15 s); 5 browser suites in parallel, one per route viewport (182 s → 46 s) |
| nanostack-framework `DB` | 364 s | 123 s wall on a warm cache (longest job 123 s) | race and statement-cache suites in parallel jobs; the postgres suite's two drivers in parallel jobs; CockroachDB no longer tested (ADR 0015); one Go build cache per package and race flag (setup-go's single go.sum key let a SQLite job's cache win, so the postgres race builds compiled from scratch: test step 189 s → 95 s); `ANALYZE TABLE` before the keyset contract's computed-key walks (MariaDB planned them badly on fresh tables: 46 s → 11 s per pass); the read-only keyset walks as parallel subtests (postgres walk test under `-race` 46 s → 14 s) |
| echopoint `dagger-check`, every check with the cache busted | 272–277 s on one host (3 runs) | 169–171 s (2 runs) | two parts, one per heavy host: `frontend and go` (frontend, Storybook, motion, ESLint, `go-test`, `go-lint`) and `rest` (`--skip` of that list, `browser-app` included). The parts take 163 s and 157 s |

What is left, and why it stays:

- anchor: a run after a `go.sum` change compiles every leg from scratch
  (about 200 s). Later commits restore the newest cache of their leg.
- anchor, after a Go change: the component parts are the critical path,
  about 25 s of setup, 33-51 s compiling and 20-38 s of tests (measured
  2026-11-12 with `main`'s caches and a change to `internal/repository`).
  The compile is real work: each part rebuilds the 26 packages that import
  the changed one, then links the test binary. Splitting does not cut it:
  every part compiles the same packages, and 16 parts instead of 8 would
  save about 10 s of tests. Lint in three shards took 33/50/67 s against
  83 s for one lint, but stays shorter than the component parts, so it
  would not shorten the run. The free arm runners (`ubuntu-24.04-arm`)
  compile faster: component parts 86-104 s, lint 55 s, the run 114 s
  against 131 s on x64, so anchor's backend jobs run there since
  2026-11-12 (the image build stays on x64).
  With no Go change every job replays its results: component parts 31-36 s.
- echopoint: `browser-app` alone takes about 134 s, so a part holding it
  cannot go much under 160 s. Two pull requests at once now share both hosts
  part by part: the first finishes in about 170 s and the second in about 340
  s, against 272 s each before (about the same on average).
- nanostack-framework: the first run after a `go.sum` or Go toolchain change
  compiles every suite from scratch (postgres jobs about 280 s). Later
  commits restore the newest cache of their package and race flag.
- anchor `component-tests`: test names come from the sources, every eighth
  test per part; a part that ran fewer tests than it selected fails.
