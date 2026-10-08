# Workflow troubleshooting

- Storybook module imports/network hangs or concurrent golangci-lint locks: follow [the existing runner-flake evidence](../self-hosted-runner-flakes.md); correlate with concurrent host jobs before changing application tests.
- All tracks skipped unexpectedly: inspect caller patterns and comparison SHAs against [detect-changes.yml](../../.github/workflows/detect-changes.yml). Missing history must choose full verification.
- Dispatch fails with `dispatch not configured`: supply both the caller's `deploy_repository` input and `DEPLOY_TOKEN` secret with permission to dispatch to that repository. [The handoff](../../.github/workflows/dispatch-deploy-event.yml) intentionally fails when either is absent; its summary identifies the missing configuration.
- A workflow works here but fails in the app: verify the caller's exact repository/ref, working directories, runner label and explicit secret/permission contract.

Capture verified causes and fixes here or in the owning capability guide, linked to the relevant caller run.
