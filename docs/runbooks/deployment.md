# Publish and roll out workflow changes

This is a workflow library, not a deployable service. Commit and open a focused PR. For a behavior change, first point a disposable caller branch at the workflow branch or exact commit and run the affected verification path.

After review and merge, callers using `nanostack-dev/ci-workflows/.github/workflows/<file>@main` consume the new revision on subsequent runs. Callers pinned to a SHA/tag require an explicit ref update. Inspect actual caller runs and artifacts before reporting rollout complete.

Record the published workflow SHA and consumers exercised. Deployment work triggered by a handoff remains owned by the private control-plane repository.
