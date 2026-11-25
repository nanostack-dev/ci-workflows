# Prod Echopoint frontend ran ahead of its API: a per-push diff stranded #1006's backend

| | |
|---|---|
| **Date** | 2026-11-25 |
| **Severity** | SEV3 |
| **Status** | In review |
| **Service** | echopoint (CI: ci-workflows detect-changes) |
| **Authors** | Nanostack routine (echopoint-investigation) |
| **Duration** | 2h 17m (trigger to resolution) |
| **Time to detect** | ~1h 35m |
| **Time to mitigate** | 2h 11m |

> Blameless: this document names systems, processes and missing guards, not people.

## Summary

echopoint #1006 (MCP permissions allow/deny, ADR-0042) merged at 16:06Z. Its main CI run went red on two frontend flakes, so its backend never built or deployed. The next four pushes were frontend-only. `detect_changes` diffed each push only against the previous push, so each reported `backend_changed=false`. The frontend-only deploy path then shipped #1006's web app to dev and prod, against an API that stayed on 8334a800 with ask mode and program runs. Echopoint has about zero users, so no customer impact is known. The fix diffs a push against the last commit a green run verified, so a red run's changes ride the next green push.

## Impact

From 16:24Z, the prod web app showed #1006's Allow/Deny MCP page and no program-run pages, while the prod API still served ask mode, `/program-runs/*` and `/allowed-tools/*`. The same skew existed on dev. A fourth frontend-only push (#1012) shipped at 18:34Z. No customer report and no known customer impact (Echopoint has about zero users). The #1006 migrations 117 and 118 waited with the backend.

- **4** frontend-only deploys to prod against the old API
- **0** known affected customers
- **2nd** time this mechanism stranded a backend (first: #860, 2026-11-13)

## Trigger

The frontend of 2207351b (#1010) reached prod at 16:24:11Z through Deploy Router run 45652997315, while the prod API stayed on 8334a800.

## Detection

The `echopoint-investigation` routine found the skew on its run, about two hours later, by comparing `/health` with `main`. No alert fires on a red main run or on an API commit that stays behind `main`. That alert is an open action of the 2026-11-23 SEV4 (A3, owned by a human, due 2026-12-07).

## Resolution

The routine first made the gate flow `Admin impersonation refusals` (fc768d01) accept both the old and the #1006 behaviour, so the #1006 deploy cannot turn the echopoint gate red. ci-workflows #62 added `last-success-sha.yml` and a `base_sha` input to `detect-changes.yml`. echopoint #1013 opted in. Its merge push changed `go.yml`, a backend pattern, so it built and deployed the stranded #1006 backend. Dev served it at 18:36Z, the echopoint gate passed at 18:40Z, and prod API and frontend were both on 7a390ffc at 18:41:58Z.

## Timeline (UTC)

| Time | | Event |
|---|---|---|
| 22:09:28 | T−18h 14m | **8334a800 main run green; API deployed at 8334a800** ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45498201256)) |
| 05:17:39 | T−11h 06m | **33c0f752 frontend-only main run green (last green before #1006)** ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45552560971)) |
| 16:06:41 | T−17m 30s | **#1006 merged as bdef245f** Backend and frontend: MCP permissions allow/deny, migrations 117 (delete `ask` rows) and 118 (drop five tables), removes `/program-runs/*`, `/allowed-tools/*` and `MCP_ASK_USER`. ([link](https://github.com/nanostack-dev/echopoint/pull/1006)) |
| 16:09:08 | T−15m 03s | **#1010 pushed as 2207351b (frontend-only)** ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45651390918)) |
| 16:19:11 | T−5m 00s | **bdef245f dagger-check red on two frontend flakes** `echopoint/motion` `ui-motion.spec.ts:416` *monitor cadence obeys reduced motion* [mobile] failed twice (`toHaveAttribute`). Storybook `flow-explorer.stories.tsx > Worst Case Table` timed out (33 s, after a retry). `ci-ok` red; `dispatch-deploy-dev` skipped. ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45651109811/job/139335526783)) |
| 16:19:21 | T−4m 50s | **2207351b detect: base bdef245f, backend_changed=false** `BASE_SHA` was `github.event.before` = bdef245f, so the diff held only #1010's files. ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45651390918/job/139340692645)) |
| 16:24:11 | T+0s | **2207351b frontend live on prod; prod API on 8334a800** Deploy Router `deploy-frontend` deployed the frontend to dev at 16:23:25Z and to prod at 16:24:11Z, with no check of the prod API commit. ([link](https://github.com/nanostack-dev/infra/actions/runs/45652997315)) |
| 16:27:15 | T+3m 04s | **b5c6a51e (#1008) frontend live on prod** ([link](https://github.com/nanostack-dev/infra/actions/runs/45653697683)) |
| 16:46:09 | T+21m 58s | **bc85aa39 (#1009) frontend live on prod** ([link](https://github.com/nanostack-dev/infra/actions/runs/45657051443)) |
| ~18:00 | T+1h 35m | **Routine finds dev and prod API on 8334a800 behind main** ([link](https://api.echopoint.dev/health)) |
| 18:14:00 | T+1h 49m | **Gate flow fc768d01 accepts old or new #1006 behaviour** So the deploy of #1006 cannot turn the echopoint post-deploy gate red. |
| 18:25:43 | T+2h 01m | **ci-workflows #62 merged: last-success-sha.yml and base_sha** ([link](https://github.com/nanostack-dev/ci-workflows/pull/62)) |
| 18:28:22 | T+2h 04m | **#1012 pushed as f09065ac (frontend-only)** ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45675751841)) |
| 18:33:46 | T+2h 09m | **echopoint #1013 merged as 7a390ffc (opt-in)** ([link](https://github.com/nanostack-dev/echopoint/pull/1013)) |
| 18:33:59 | T+2h 09m | **7a390ffc detect: base f09065ac from the last green run** `last_success` found run 45675751841 at f09065ac; `backend_changed=true` (this push changed `go.yml`, a backend pattern). ([link](https://github.com/nanostack-dev/echopoint/actions/runs/45676429158)) |
| 18:34:44 | T+2h 10m | **f09065ac (#1012) frontend live on prod: fourth skewed deploy** ([link](https://github.com/nanostack-dev/infra/actions/runs/45676288271)) |
| 18:36:04 | T+2h 11m | **Dev API live at 7a390ffc with #1006** ([link](https://github.com/nanostack-dev/infra/actions/runs/45676570346)) |
| 18:40:07 | T+2h 15m | **Echopoint post-deploy gate green on dev** ([link](https://github.com/nanostack-dev/infra/actions/runs/45676570346)) |
| 18:41:58 | T+2h 17m | **Prod API and frontend both at 7a390ffc with #1006** Backend deployed to prod at 18:41:48Z, frontend promoted at 18:41:58Z; `api.echopoint.dev/health` reports 7a390ffc. ([link](https://github.com/nanostack-dev/infra/actions/runs/45676570346)) |

## Root cause analysis: the five whys

Start at the impact and ask why until the answer is something the team can change. Solid edges ask why it happened; dashed edges ask why the impact was as large as it was.

```mermaid
flowchart TD
  P["The prod web app shipped #1006's MCP Allow/Deny page while the prod API kept ask mode and program runs"]
  W1["Four frontend-only deploys shipped HEAD's frontend; #1006's backend image was never built"]
  W2["`detect_changes` reported `backend_changed=false` for 2207351b, b5c6a51e, bc85aa39 and f09065ac"]
  W3["It diffed each push only against `github.event.before`, the previous push"]
  W4["A red run deploys nothing, and nothing carried its changes into the next push's diff"]
  R1["R1 · Change detection measured a push against the previous push, not against the last commit a green run verified and deployed"]
  W5["The frontend-only path promoted to prod without checking which API commit prod runs"]
  R2["R2 · The frontend-only deploy assumes the API already runs every earlier main commit, and nothing checks it"]
  W6["#1006's main run went red although #1006 broke nothing it tested"]
  W7["Both tests fail on unrelated changes: motion in 3 runs since 2026-11-24, Worst Case Table in 5 runs since 2026-11-22"]
  R3["R3 · Repeat flakes in the frontend checks have no tracker, owner or quarantine, so they keep failing main runs"]
  W8["Why each test flakes (timing of the reduced-motion state on mobile, a 33 s story timeout) is not diagnosed yet"]
  W9["The skew lasted hours and no alert fired"]
  W10["No monitor compares the deployed API commit with main, and a red main run alerts nobody"]
  R4["R4 · A stranded backend change is invisible until someone compares /health with main by hand"]
  W11["It happened a second time: on 2026-11-13 #860 was stranded the same way"]
  W12["The postmortem and CI fix went to a spawned task chip that nobody started"]
  R5["R5 · A ledger row could rest at `mitigated` with its root cause unfixed and its only fix in an unstarted task"]
  P -->|why?| W1
  W1 -->|why?| W2
  W2 -->|why?| W3
  W3 -->|why?| W4
  W4 -->|why?| R1
  W1 -->|why?| W5
  W5 -->|why?| R2
  P -->|why?| W6
  W6 -->|why?| W7
  W7 -->|why?| R3
  W7 -->|why?| W8
  P -.->|why so bad?| W9
  W9 -->|why?| W10
  W10 -->|why?| R4
  P -.->|why so bad?| W11
  W11 -->|why?| W12
  W12 -->|why?| R5
  class P problem
  class R1,R2,R3,R4,R5 root
  class W8 open
  classDef problem fill:#fdecea,stroke:#c2362f,stroke-width:2px,color:#4a1210
  classDef root fill:#e7f5ec,stroke:#1f7a45,stroke-width:2px,color:#0f3a20,font-weight:bold
  classDef open fill:#fff4d9,stroke:#9a6200,stroke-dasharray:5 4,color:#3f2a00
```

- **Problem:** The prod web app shipped #1006's MCP Allow/Deny page while the prod API kept ask mode and program runs
  - **Why?** Four frontend-only deploys shipped HEAD's frontend; #1006's backend image was never built _Evidence: Deploy Router runs [45652997315](https://github.com/nanostack-dev/infra/actions/runs/45652997315), [45653697683](https://github.com/nanostack-dev/infra/actions/runs/45653697683), [45657051443](https://github.com/nanostack-dev/infra/actions/runs/45657051443) ran only `deploy-echopoint-frontend` and `-prod`; `/health` stayed 8334a800_
    - **Why?** `detect_changes` reported `backend_changed=false` for 2207351b, b5c6a51e, bc85aa39 and f09065ac _Evidence: [detect log](https://github.com/nanostack-dev/echopoint/actions/runs/45651390918/job/139340692645): `BASE_SHA: bdef245f…`, `backend_changed=false frontend_changed=true`_
      - **Why?** It diffed each push only against `github.event.before`, the previous push _Evidence: ci-workflows `detect-changes.yml` before #62: `BASE_SHA: … || github.event.before`_
        - **Why?** A red run deploys nothing, and nothing carried its changes into the next push's diff _Evidence: Run [45651109811](https://github.com/nanostack-dev/echopoint/actions/runs/45651109811): `ci-ok` failure, `dispatch-deploy-dev` skipped_
          - **Why?** Change detection measured a push against the previous push, not against the last commit a green run verified and deployed → **Root cause R1** (fixed by A1, A2, A3, A8)
    - **Why?** The frontend-only path promoted to prod without checking which API commit prod runs _Evidence: echopoint `go.yml` `dispatch-frontend-deploy-dev` sends `promote_to_prod: true`; the Deploy Router frontend runs have no gate or API check_
      - **Why?** The frontend-only deploy assumes the API already runs every earlier main commit, and nothing checks it → **Root cause R2** (fixed by A4)
  - **Why?** #1006's main run went red although #1006 broke nothing it tested _Evidence: [Job 139335526783](https://github.com/nanostack-dev/echopoint/actions/runs/45651109811/job/139335526783): motion reduced-motion [mobile] failed twice; storybook `Worst Case Table` timed out after a retry; both pass on the next pushes_
    - **Why?** Both tests fail on unrelated changes: motion in 3 runs since 2026-11-24, Worst Case Table in 5 runs since 2026-11-22 _Evidence: Scan of the 90 runs with a failed dagger-check among 418 completed Go Build and Test runs, 2026-11-11..25. Main runs: Worst Case Table 8f2e4c6e and bdef245f; motion bdef245f_
      - **Why?** Repeat flakes in the frontend checks have no tracker, owner or quarantine, so they keep failing main runs → **Root cause R3** (fixed by A5)
      - **Why?** Why each test flakes (timing of the reduced-motion state on mobile, a 33 s story timeout) is not diagnosed yet → _open, still investigating_
  - **Why so bad?** The skew lasted hours and no alert fired _Evidence: First signal is the routine's own `/health` check, about 2 h after the trigger_
    - **Why?** No monitor compares the deployed API commit with main, and a red main run alerts nobody _Evidence: 2026-11-23 SEV4 ([Atelier](http://nanostack-dev-1340p:4320/postmortems/01a20aeb-3a9c-7ee2-be59-4f6bdf466d7f)) action A3 red-main alert: open, due 2026-12-07_
      - **Why?** A stranded backend change is invisible until someone compares /health with main by hand → **Root cause R4** (fixed by A6)
  - **Why so bad?** It happened a second time: on 2026-11-13 #860 was stranded the same way _Evidence: Routine ledger row 87: `mitigated`, "root cause unfixed, waits on task_ad0e05c4 or a human"_
    - **Why?** The postmortem and CI fix went to a spawned task chip that nobody started _Evidence: No postmortem or PR for row 87 in ci-workflows or echopoint between 2026-11-13 and 2026-11-25_
      - **Why?** A ledger row could rest at `mitigated` with its root cause unfixed and its only fix in an unstarted task → **Root cause R5** (fixed by A7, A8)

## Root causes

- **R1** Change detection measured a push against the previous push, not against the last commit a green run verified and deployed
- **R2** The frontend-only deploy assumes the API already runs every earlier main commit, and nothing checks it
- **R3** Repeat flakes in the frontend checks have no tracker, owner or quarantine, so they keep failing main runs
- **R4** A stranded backend change is invisible until someone compares /health with main by hand
- **R5** A ledger row could rest at `mitigated` with its root cause unfixed and its only fix in an unstarted task

## Contributing factors

- Four frontend-only pushes came within 2.5 hours of the red run, so each green run moved the push-to-push base past #1006.
- Each frontend-only run was green, so the newest green commit before the fix (f09065ac) also predates it: the fix covers red runs from now on, and #1006 shipped only because #1013 itself changed a backend pattern.
- The `dagger_check` story scope also diffed from `github.event.before`, so a story that failed on a red push was not rerun on the next push.

## Lessons learned

### What went well

- The routine changed the gate flow to accept both behaviours before the stranded backend deployed, so the deploy could not turn the echopoint gate red.
- `ci-ok` blocked the backend deploy of a red run, as designed: nothing unverified reached prod's API.

### What went wrong

- The same mechanism hit on 2026-11-13 and its fix was never written.
- The first version of echopoint #1013 skipped `last_success` on pull requests. GitHub then skipped `migrations-verify`, `migration-lint` and `preview-flag` transitively, and `ci-ok` would still pass. The PR run showed it before the merge.

### Where we got lucky

- Echopoint has about zero users, so a prod web app that called an older API reached nobody.
- #1006's frontend and the old API failed in a visible way (missing pages), not by writing wrong data.
- Adding `actions: read` directly to `detect-changes.yml` would have failed anchor and atelier at startup, since a called workflow cannot ask for more than its caller grants. The design review caught it before the merge.

## Action items

| ID | Action | Type | Owner | Due | Status | Ticket | Fixes |
|---|---|---|---|---|---|---|---|
| A1 | `last-success-sha.yml` finds the last green push run; `detect-changes.yml` diffs a push from its commit (`base_sha`), else the previous push | prevent | Nanostack routine (echopoint-investigation) | 2026-11-25 | done | [ci-workflows#62](https://github.com/nanostack-dev/ci-workflows/pull/62) | R1 |
| A2 | echopoint `go.yml` opts in (`last_success` job with `actions: read`), scopes the frontend stories from the same commit, and `ci-ok` fails if the lookup fails | prevent | Nanostack routine (echopoint-investigation) | 2026-11-25 | done | [echopoint#1013](https://github.com/nanostack-dev/echopoint/pull/1013) | R1 |
| A3 | anchor and atelier `go.yml` opt in the same way (last_success never skipped, `actions: read`, `base_sha`, ci-ok gate) | prevent | Nanostack routine (echopoint-investigation) | 2026-12-02 | open |  | R1 |
| A4 | infra Deploy Router `deploy-frontend` promotes to prod only when the prod API runs the newest backend-changing main commit at or before the frontend's commit; otherwise it holds and says why | prevent | infra maintainers | 2026-12-09 | open |  | R2 |
| A5 | Diagnose and fix or quarantine the motion reduced-motion [mobile] test and the `Worst Case Table` story, and track repeat frontend flakes with an owner | prevent | echopoint frontend maintainers | 2026-12-09 | open |  | R3 |
| A6 | Alert when main CI is red, or when the API `/health` commit stays behind main's newest backend change for over an hour (2026-11-23 SEV4 action A3) | detect | human (infra maintainers) | 2026-12-07 | open |  | R4 |
| A7 | Postmortem loop: a `mitigated` row with an unfixed root cause gets its fix in the next routine run, never only in a spawned task | process | Nanostack routine (echopoint-investigation) parent | 2026-11-26 | open |  | R5 |
| A8 | Guide lines: ci-workflows AGENTS.md (change detection gates deploys, diff from the last green commit) and echopoint AGENTS.md (a red-run PR ships with the next green push; check `/health`) | process | Nanostack routine (echopoint-investigation) | 2026-11-25 | done |  | R1, R5 |

## Responders

- **Detection, diagnosis and fix**: Nanostack routine (echopoint-investigation)

## Messaging

### Internal

SEV3 echopoint: #1006's backend did not deploy after a red main run (two frontend flakes), while four frontend-only pushes shipped its web app to prod against the old API. Root cause: detect_changes diffed a push only against the previous push. Fixed in ci-workflows #62 and echopoint #1013, which also deploys #1006. Open: anchor/atelier opt-in, an infra frontend-promotion guard, the two flakes, and a red-main alert.

### Customers

None: no known customer impact.

## Supporting information

- [Atelier postmortem](http://nanostack-dev-1340p:4320/postmortems/01a21406-a689-75bd-ba7a-b40b42f9c01e)
- [echopoint#1006](https://github.com/nanostack-dev/echopoint/pull/1006)
- [Red main run 45651109811](https://github.com/nanostack-dev/echopoint/actions/runs/45651109811)
- [ci-workflows#62 (fix)](https://github.com/nanostack-dev/ci-workflows/pull/62)
- [echopoint#1013 (opt-in)](https://github.com/nanostack-dev/echopoint/pull/1013)
- [Related SEV4 2026-11-23 (CT flake stranded #988)](http://nanostack-dev-1340p:4320/postmortems/01a20aeb-3a9c-7ee2-be59-4f6bdf466d7f)
