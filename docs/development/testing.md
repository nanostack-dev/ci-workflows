# Workflow verification

For docs-only changes, validate affected local links and source references and run `git diff --check`. For YAML/workflow changes, run `actionlint` from this repository and inspect the changed `workflow_call` inputs/outputs and expression contexts.

For behavioral changes, use a caller branch that references the workflow branch or exact commit and exercises the affected case. Verify backend/frontend gating, required permissions, reports and error outcomes in that caller. For change detection include missing/zero base commits and manual dispatch behavior; expected fallback is full verification.

No tracked self-test workflow proves these reusable workflows end to end in isolation. Report the concrete caller run and its ref, or state that caller execution was not performed. Keep environment-specific credentials in the caller.
