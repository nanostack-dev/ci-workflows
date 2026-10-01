# Flakes on self-hosted runners

Two failures that only appear when several jobs share one self-hosted host. Both are fixed in these workflows. This page explains each one, so that a regression is recognised quickly.

## Storybook tests hang or fail to import a module

### Symptoms

- A `Storybook tests N/M` job prints results for some files, then nothing, until the step timeout. The job has no summary line. The runner then kills orphan `node`, `esbuild` and `chrome-headless-shell` processes. Sometimes no file reports at all.
- Or one or more files fail with `Failed to fetch dynamically imported module`, although every test in those files passes when run again.
- A file can also fail with `[MSW] Failed to register the Service Worker: An unknown error occurred when fetching the script`. This is the same failure.
- The failures happen when other jobs run on the same host, for example several stacked pull requests at once. They never reproduce on a laptop.

This is not an exit hang. Compare the job output with the file list of the shard: one to three files were queued and never collected.

### Cause

On Linux, Chrome treats any address change on the host as a network change. It then closes its connection pools with `net::ERR_NETWORK_CHANGED`, and requests to `localhost` are closed too. Chromium creates its Linux network change notifier with an empty list of ignored interfaces, and no command-line flag turns it off.

On a host that runs Docker, each container (test databases, image build steps, Swarm tasks) adds a `veth` interface and removes it later. About one second after it is created, the interface gets an IPv6 link-local address, and that address event is what Chrome reacts to. A container that lives less than a second does not trigger it. One host removed more than 600 of these interfaces in one day.

When Chrome closes a request for a module that Vitest is waiting on, the file fails with the dynamic import error. When it closes the first module load of a test file, nothing reports the error. Vitest has no timeout for loading a file into a browser tab, so it waits until the step timeout.

### Evidence

- In CI, the two stalls that were captured each had a burst of `ERR_NETWORK_CHANGED` (29 and 80 failed module requests). The kernel log showed a `veth` event 70 ms and about 2 s before each burst. The 46 healthy shards of the same runs had none.
- During those stalls, logs added to the MSW service worker and the Vite server showed no stuck MSW reply and no Vite request slower than 5 s. Chrome dropped the requests itself.
- On the host, a loop started a container that lives 3 s every second. Shards outside a namespace hung 3 of 3 times. Shards in a private network namespace passed 4 of 4, then 6 of 6 with three shards at a time.
- In CI after the fix: 48 of 48 shards ran in the namespace, with no `ERR_NETWORK_CHANGED`, no stall and no import failure.

The same Chromium behaviour with Kubernetes pods: [agentydragon/ducktape#7921](https://github.com/agentydragon/ducktape/issues/7921).

### Fix

`frontend-verify.yml` runs the Storybook tests through [`scripts/vitest-watchdog/run.mjs`](../scripts/vitest-watchdog/run.mjs):

1. **Private network namespace.** On Linux, Vitest, its Vite server and Chrome start in `unshare --map-root-user --net`, with loopback only. They never see the host's interfaces change. If the host does not allow unprivileged user namespaces (GitHub-hosted Ubuntu restricts them), the script runs the command directly and logs that it did. `VITEST_NETWORK_ISOLATION=0` turns the namespace off.
2. **Watchdog.** If no test file event happens for 60 s, the script kills the run. It then runs again only the files that did not finish and the files that failed with the dynamic import error. A file runs again at most twice. A file with a failing test never runs again, so a real failure still fails the step.
3. **Logs.** `VITEST_PW_DEBUG=1` logs each failed browser request with Chrome's `net::` error.

The job checks out `scripts/vitest-watchdog` from this repository at `job.workflow_sha`, so the scripts always match the workflow that runs them.

A host-wide alternative is to stop new interfaces from getting link-local addresses with `sysctl net.ipv6.conf.default.addr_gen_mode=1`. It also covers browser tests that do not go through this script, but it changes the whole host.

### Diagnose the next one

1. In the step log, look for `[watchdog] running in a private network namespace`. If the log says the namespace is not available, the host blocks unprivileged user namespaces, and the cause above is not fixed there.
2. Search for `ERR_NETWORK_CHANGED`. If it is there in spite of the namespace, a process outside the namespace issued the request.
3. If a file is printed as `in flight` and there is no `net::` error, the cause is different. The watchdog line tells you if the file was `queued` (it never loaded) or `collected` (a test is waiting for something).
4. Compare the time of the first failed request with `journalctl -k | grep veth` on the host.

## golangci-lint exits with "parallel golangci-lint is running"

### Symptoms

`Lint <app> app` fails after about 5 s with `Error: parallel golangci-lint is running` and exit code 3, while another lint job runs on the same host.

### Cause

golangci-lint takes a lock at `os.TempDir()/golangci-lint.lock` (`pkg/commands/run.go`). If it cannot get the lock within 5 s, it exits. Runner slots on one host share `/tmp`. A separate `HOME` or `GOLANGCI_LINT_CACHE` per slot does not help, because the lock is not in either of them.

### Fix

`go-build-test.yml` passes `--allow-parallel-runners`. The analysis cache stays shared between slots, so warm runs stay fast. The cache is a fork of the Go build cache, which supports concurrent processes. In a test with one shared cache, two concurrent runs both passed with the same result (`0 issues`). Without the flag, the second run failed after 5 s.
