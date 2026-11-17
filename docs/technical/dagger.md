# Dagger CI

Nanostack repositories run their checks with [Dagger](https://docs.dagger.io) 1.0. Each repository's `dagger.toml` declares its checks. A workflow job installs the CLI with [setup-dagger](../../.github/actions/setup-dagger/action.yml) and runs `dagger check`. A developer runs the same command and gets the same result.

## Use it in a repository

```yaml
jobs:
  dagger-check:
    runs-on: nanostack-dev
    steps:
      - uses: actions/checkout@<pinned sha>
      - uses: nanostack-dev/ci-workflows/.github/actions/setup-dagger@<pinned sha>
      - run: dagger check --progress=report
```

- `--progress=report` prints each failed check's output. `plain` prints only span names.
- Secrets reach a check through a module setting in `dagger.toml` (`env://NAME`). The job maps the repository secret to that environment variable. A secret never goes on the command line or into a file.
- Releases and deploys stay workflow jobs. They may call a module function (`dagger api call <module> publish ...`), but they are not checks.

## Where the engine runs

The engine is the cache. A check whose inputs did not change is a cache hit, so a warm engine makes most of a pull request free.

| Runner | Engine | Cache |
|---|---|---|
| `nanostack-dev` slots on `1340p` | One container on the host's Docker daemon, shared by all slots | Named volume `dagger-engine-<version>`: persists across jobs, restarts, reboots and a recreated container |
| `nanostack-ci` (GARM, one VM per job) | Inside the job's VM | Deleted with the VM: every run is cold |
| GitHub-hosted (`ubuntu-latest`, public repositories) | Inside the job's VM | Every run is cold |

Dagger's own guidance is the same: give each engine a persistent disk, and do not run engines on a pool of ephemeral machines ([self-hosting](https://github.com/dagger/dagger/blob/main/docs/current_docs/self-hosting/index.mdx)). Repositories keep the runner they had. A job on an ephemeral runner gains local and CI parity from Dagger, but not speed.

The engine on `1340p` runs outside the slots' `MemoryMax`, like any container a job starts. One engine for every repository means one cache and one place where checks compete for CPU. A repository that saturates it should split heavy checks rather than add parallel copies (see each repository's Dagger guide).

Every job on a host must use the exact `DAGGER_ENGINE` string that `setup-dagger` sets. The CLI matches an engine by container name, and it removes engines of the same version that another string started. Two strings on one host make jobs kill each other's engine.

## Writing checks that stay maintainable

These follow Dagger's [checks](https://github.com/dagger/dagger/blob/main/docs/current_docs/using/checking.mdx) guidance and what we measured on echopoint.

- **Prefer official modules** (`dagger module recommend`): `dagger.io/go/golangci-lint`, `dagger.io/js/eslint`, and others. Write a check in the repository's own module only when no official module covers it.
- **Versions are settings.** Tool and image versions live in `dagger.toml` settings, not in function bodies, so a bump is one line. `dagger.lock` pins module refs and image digests. Commit both files.
- **Checks take no required arguments,** and one failure points to one problem. Give each check a name a reader understands (`frontend-build`, not `step-3`).
- **Generated files are generators.** A function annotated `@generate` returns a `Changeset`. `dagger generate` writes it, and its `stale` check fails CI when the committed files differ.
- **Narrow each check's inputs.** `ws.directory(path, include:, exclude:)` decides what invalidates the cache. A docs change must not re-run the Go tests.
- **Install dependencies in a layer of their own.** Copy only the manifest and lockfile, install, then copy the sources, so a source change reuses the install.
- **Mind the shared CPU.** Every check runs at once on one engine. Browser suites with tight timeouts suffer first: shard by fewer, larger runs rather than many parallel servers.
- **Avoid thousands of checks.** The official Go module makes one check per test. On echopoint (about 4,400 tests) that pushed the CLI past 8 GiB. Run `go test ./...` as one check there.

## Upgrade Dagger

Dagger 1.0 is in beta. Upgrades are deliberate:

0. Check that a fresh engine of the new version starts: `docker run --rm --privileged registry.dagger.io/engine:<version>` must stay up (stop it with Ctrl-C). A warm engine on `1340p` does not prove this, because an engine that started before a fault keeps working.
1. Bump `version` and the checksums in `setup-dagger/action.yml` in this repository.
2. In each repository, bump the pinned commit of the `setup-dagger` action in the workflows (callers pin it by SHA, so step 1 alone changes nothing for them), bump `engineVersion` in `.dagger/modules/*/dagger-module.toml`, run `dagger check`, and open a pull request.
3. Expect the first run on each host to be cold, about the length of a full run without cache. The CLI starts the new engine and removes the old one. Then delete the old cache on the host: `docker volume rm dagger-engine-<old version>`.

## Current pin: v1.0.0-beta.24

The default is `v1.0.0-beta.24`. On 2026-11-17 a freshly started `v1.0.0-beta.27` engine exited at once with `failed to create engine: merge the engine image's entries: root 4875 did not merge (expired true, retained false)`. Every `dagger check` on a fresh engine (GitHub-hosted runners, the per-job devbox VM) then waited 10 minutes and failed with `start engine: new client: context deadline exceeded`. The beta.27 engine already running on `1340p` kept working, which hid the fault there. A fresh beta.24 engine starts normally, so every repository went back to beta.24 ([troubleshooting](../development/troubleshooting.md#every-dagger-check-fails-with-start-engine-new-client-context-deadline-exceeded)).

The action keeps the beta.27 checksums, so `version: v1.0.0-beta.27` still installs that CLI. Move the default forward only to a release that passes step 0 of the upgrade.
