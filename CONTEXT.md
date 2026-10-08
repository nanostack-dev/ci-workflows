# CI vocabulary

| Term | Meaning |
| --- | --- |
| Reusable workflow | A GitHub Actions workflow exposed through `workflow_call`. |
| Caller | Repository workflow supplying the reusable workflow's inputs, permissions and secrets. |
| Verification track | Backend/frontend checks selected by explicit changed-path patterns. |
| Fail open for verification | Run all verification when the comparison cannot be resolved. |
| Dispatch handoff | Explicit repository-dispatch event sent to the private deployment owner. |
| Self-hosted runner | Caller-selected runner label whose host can be shared by concurrent jobs. |
| Artifact | Built image, test report or other output passed to later caller-owned steps. |

[Architecture](docs/technical/architecture.md) owns the workflow boundaries.
