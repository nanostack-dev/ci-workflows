# Workflow troubleshooting

- Storybook module imports/network hangs or concurrent golangci-lint locks: follow [the existing runner-flake evidence](../self-hosted-runner-flakes.md); correlate with concurrent host jobs before changing application tests.
- All tracks skipped unexpectedly: inspect caller patterns and comparison SHAs against [detect-changes.yml](../../.github/workflows/detect-changes.yml). Missing history must choose full verification.
- Dispatch fails with `dispatch not configured`: supply both the caller's `deploy_repository` input and `DEPLOY_TOKEN` secret with permission to dispatch to that repository. [The handoff](../../.github/workflows/dispatch-deploy-event.yml) intentionally fails when either is absent; its summary identifies the missing configuration.
- Flow-suite rerun fails with `409 IDEMPOTENCY_KEY_CONFLICT` ("Idempotency key reused with different launch parameters") after `TRANSPORT-RERUN`: the rerun launched with a key that an earlier launch in the same job already used for another flow. Up to echopoint-cli v4.1.0, a single-flow `echopoint flows run` in GitHub Actions uses one key per job attempt, so only the first rerun ran ([infra run 43953894269](https://github.com/nanostack-dev/infra/actions/runs/43953894269), attempt 1: 1 of 4 reruns ran, 3 got 409). [echopoint-test.yml](../../.github/workflows/echopoint-test.yml) now passes `--idempotency-key transport-rerun-<run id>-<attempt>-<flow>` for each rerun. That key also differs from the suite's own launch of the flow; reusing that one would replay the failed execution instead of running the flow again. To check the fix, list the flow's executions (`GET /flows/<id>/executions`): each rerun creates a new execution.
- A workflow works here but fails in the app: verify the caller's exact repository/ref, working directories, runner label and explicit secret/permission contract.

Capture verified causes and fixes here or in the owning capability guide, linked to the relevant caller run.

## Every Dagger check fails with `start engine: new client: context deadline exceeded`

Symptom: a `dagger check` job waits 10 minutes at `connecting to engine`, then fails. On the runner, `docker logs dagger-engine-<version>` shows why the engine exited. On 2026-11-17, `v1.0.0-beta.27` failed with `failed to create engine: merge the engine image's entries: root 4875 did not merge (expired true, retained false)` on every fresh start; engines started earlier kept working.

Check: `docker run --rm --privileged registry.dagger.io/engine:<version>` must stay up. If it exits, pin the last version whose fresh engine starts (`version` default in [setup-dagger](../../.github/actions/setup-dagger/action.yml), then each repository's `engineVersion` and action SHA), as [Dagger CI](../technical/dagger.md#current-pin-v100-beta24) records for beta.27.
