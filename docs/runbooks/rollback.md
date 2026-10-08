# Roll back a workflow change

Identify the broken workflow SHA and affected caller runs. Revert the faulty source change through a focused PR, or explicitly pin an affected caller to a previously verified workflow commit while the repair is prepared.

Rerun the affected caller verification path and confirm the workflow ref, expected gate decisions and artifacts. A reverted library commit does not undo images already published or deployments already dispatched; coordinate any resulting operational recovery with their owner.

Preserve the failed run and verified root cause in the owning troubleshooting or decision record.
