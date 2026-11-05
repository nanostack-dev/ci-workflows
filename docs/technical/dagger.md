# Dagger CI

Nanostack repositories run their checks with [Dagger](https://docs.dagger.io) 1.0. Each repository's `dagger.toml` declares its checks. A workflow job installs the CLI with [setup-dagger](../../.github/actions/setup-dagger/action.yml) and runs `dagger check`. A developer runs the same command and gets the same result.

## Use it in a repository

```yaml
jobs:
  dagger-check:
    runs-on: nanostack-dev
    steps:
      - uses: actions/checkout@<pinned sha>
      - uses: nanostack-dev/ci-workflows/.github/actions/setup-dagger@main
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

1. Bump `version` and the checksums in `setup-dagger/action.yml` in this repository.
2. In each repository, bump `engineVersion` in `.dagger/modules/*/dagger-module.toml`, run `dagger check`, and open a pull request.
3. Expect the first run on each host to be cold, about the length of a full run without cache. The CLI starts the new engine and removes the old one. Then delete the old cache on the host: `docker volume rm dagger-engine-<old version>`.
