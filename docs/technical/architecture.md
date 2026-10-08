# Reusable workflow architecture

| Workflow | Owned behavior |
| --- | --- |
| [go-build-test.yml](../../.github/workflows/go-build-test.yml) | Caller-configured Go lint/test suites and container publication. |
| [frontend-verify.yml](../../.github/workflows/frontend-verify.yml) | Frontend verification and affected Storybook/browser test planning. |
| [detect-changes.yml](../../.github/workflows/detect-changes.yml) | Backend/frontend boolean outputs from caller-defined glob patterns; full verification when comparison is unavailable. |
| [echopoint-test.yml](../../.github/workflows/echopoint-test.yml) | API flow-suite verification through the declared Echopoint CLI Action. |
| [dispatch-deploy-event.yml](../../.github/workflows/dispatch-deploy-event.yml) | Validated JSON event handoff to an explicitly configured private owner. |

A caller's `jobs.<name>.uses` binds a GitHub repository/ref; `with`, explicit secrets and caller permissions define the contract. Runtime deployment ownership stays outside this repository. The dispatch workflow requires both `deploy_repository` and `DEPLOY_TOKEN`: missing either prevents the handoff and fails the job so an unsent deployment or preview cleanup cannot appear successful.

Source files are authoritative for required values and defaults. Avoid copying a workflow's full schema into a second maintained table. Read [runner flakes](../self-hosted-runner-flakes.md) before changing job concurrency/network or lint execution assumptions.
