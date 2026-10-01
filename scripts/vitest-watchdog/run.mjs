// Runs a Vitest browser-mode command in a private network namespace, under a
// watchdog.
//
// On Linux, Chrome treats any address change on the host as a network change and
// aborts its in-flight requests with net::ERR_NETWORK_CHANGED, requests to
// localhost included. On a self-hosted runner, Docker adds and removes veth
// interfaces whenever a test container or an image build step starts or stops
// (634 on 1340p on 2026-09-30). In a private network namespace that holds only
// loopback, Vitest, its Vite server and Chrome never see those changes. Where
// the host does not allow an unprivileged namespace (GitHub-hosted Ubuntu
// restricts them), the command runs directly.
//
// Vitest has no timeout on loading a test file into a browser tab. When a module
// request never gets an answer, the file stays in flight forever, the other tabs
// finish, and the run prints nothing until the step timeout. When the request
// fails instead, the file fails with "Failed to fetch dynamically imported
// module" although every test in it passes on its own.
//
// This script kills a run once no test file event has happened for
// VITEST_STALL_SECONDS, then runs the files that never finished, plus the files
// that failed with the dynamic import error, again, at most twice. A file that
// fails its tests is never run again, so a real failure still fails the step.
//
// Environment:
//   VITEST_COMMAND       command that ends in `vitest run`, e.g. `pnpm test-storybook`
//   VITEST_SHARD         optional `<index>/<count>`, appended as --shard on the first run
//   VITEST_STALL_SECONDS optional, default 60
//   VITEST_NETWORK_ISOLATION optional, `0` runs on the host network
import { spawn, spawnSync } from "node:child_process"
import { existsSync, mkdtempSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const command = process.env.VITEST_COMMAND
const shard = process.env.VITEST_SHARD ?? ""
const stallMs = Number(process.env.VITEST_STALL_SECONDS || 60) * 1000
// A run that reported its end but is still alive after this is killed and judged
// by what it reported.
const exitGraceMs = 30_000
const reporterPath = fileURLToPath(new URL("./progress-reporter.mjs", import.meta.url))

if (!command) {
  console.error("VITEST_COMMAND is not set")
  process.exit(2)
}

// `unshare -rn` maps the current user to root in a new user namespace, which may
// create a network namespace. Its loopback interface starts down.
const isolate = ["unshare", "--map-root-user", "--net", "bash", "-c", 'ip link set lo up && exec bash -c "$1"', "bash"]
const canIsolate =
  process.platform === "linux" &&
  process.env.VITEST_NETWORK_ISOLATION !== "0" &&
  spawnSync(isolate[0], [...isolate.slice(1), "true"], { stdio: "ignore" }).status === 0
console.log(
  canIsolate
    ? "[watchdog] running in a private network namespace (loopback only)"
    : "[watchdog] private network namespace not available, running on the host network",
)

const quote = (value) => `'${value.replaceAll("'", "'\\''")}'`
const relative = (file) => path.relative(process.cwd(), file)

function readProgress(progressFile) {
  if (!existsSync(progressFile)) return []
  return readFileSync(progressFile, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line))
}

function killGroup(child, signal) {
  try {
    process.kill(-child.pid, signal)
  } catch {
    // The group is already gone.
  }
}

async function attempt(label, extraArgs) {
  const progressFile = path.join(mkdtempSync(path.join(tmpdir(), "vitest-watchdog-")), "progress.jsonl")
  const reporters = ["default", ...(process.env.GITHUB_ACTIONS === "true" ? ["github-actions"] : []), reporterPath]
  const args = [...extraArgs, ...reporters.map((reporter) => `--reporter=${quote(reporter)}`)]
  const commandLine = `${command} ${args.join(" ")}`
  console.log(`[watchdog] ${label}: ${commandLine}`)

  const startedAt = Date.now()
  // detached puts vitest and everything it spawns in one process group, so a
  // stalled run can be killed whole.
  const [file, ...spawnArgs] = canIsolate ? [...isolate, commandLine] : ["bash", "-c", commandLine]
  const child = spawn(file, spawnArgs, {
    detached: true,
    stdio: "inherit",
    // VITEST_PW_DEBUG makes @vitest/browser-playwright log each failed browser
    // request with Chrome's net:: error, the only record of why an import failed.
    env: { VITEST_PW_DEBUG: "1", ...process.env, VITEST_WATCHDOG_PROGRESS: progressFile },
  })
  const exited = new Promise((resolve) => child.on("exit", (code, signal) => resolve(code ?? (signal ? 1 : 0))))

  let verdict = "exited"
  let exitCode = null
  const timer = setInterval(() => {
    const events = readProgress(progressFile)
    const lastEventAt = events.at(-1)?.at ?? startedAt
    const runEnd = events.find((event) => event.event === "run-end")
    if (runEnd && Date.now() - runEnd.at > exitGraceMs) {
      verdict = "lingered"
    } else if (!runEnd && Date.now() - lastEventAt > stallMs) {
      verdict = "stalled"
    } else {
      return
    }
    clearInterval(timer)
    killGroup(child, "SIGTERM")
    setTimeout(() => killGroup(child, "SIGKILL"), 5_000).unref()
  }, 2_000)

  exitCode = await exited
  clearInterval(timer)
  // The group can outlive bash when bash exits first.
  killGroup(child, "SIGKILL")

  const events = readProgress(progressFile)
  const files = events.find((event) => event.event === "start")?.files ?? []
  const ended = new Map(events.filter((event) => event.event === "end").map((event) => [event.file, event]))
  const lastEvent = new Map(events.filter((event) => event.file).map((event) => [event.file, event]))
  const runEnd = events.find((event) => event.event === "run-end")
  const seconds = Math.round((Date.now() - startedAt) / 1000)

  if (verdict === "stalled") {
    console.log(`\n[watchdog] ${label}: no test file event for ${stallMs / 1000} s, killed after ${seconds} s.`)
    for (const file of files.filter((file) => !ended.has(file))) {
      const event = lastEvent.get(file)
      const state = event ? `${event.event} ${Math.round((Date.now() - event.at) / 1000)} s ago` : "never queued"
      console.log(`[watchdog]   in flight: ${relative(file)} (${state})`)
    }
  } else if (verdict === "lingered") {
    console.log(`\n[watchdog] ${label}: reported "${runEnd.reason}" but did not exit within ${exitGraceMs / 1000} s, killed.`)
  }

  return {
    started: files.length > 0,
    passed: verdict === "lingered" ? runEnd.reason === "passed" && runEnd.unhandledErrorFiles.length === 0 : exitCode === 0,
    testFailures: [...ended.values()].filter((event) => event.state === "failed" && !event.importFailed).map((event) => event.file),
    unhandledErrorFiles: runEnd?.unhandledErrorFiles ?? [],
    retryable: files.filter((file) => !ended.has(file) || ended.get(file).importFailed),
  }
}

// Only a stall or a dynamic import failure is retried, at most twice: on
// 2026-09-30 three files hit the import failure twice in a row, one second
// apart. An unhandled error blocks the retry unless it came from a file that
// runs again: the network failure that breaks a module import also breaks
// MSW's service worker registration in that file. Anything else, including a
// run that failed before it listed its files, fails the step as it is.
function retryableFiles(result) {
  const isRetried = (file) => file !== null && result.retryable.some((retried) => retried === file || retried.endsWith(`/${file}`))
  const retry =
    result.started &&
    result.testFailures.length === 0 &&
    result.unhandledErrorFiles.every(isRetried) &&
    result.retryable.length > 0
  return retry ? result.retryable.map(relative) : []
}

const maxRuns = 3
let result = await attempt("run 1", shard ? [`--shard=${quote(shard)}`] : [])
for (let run = 2; !result.passed && run <= maxRuns; run++) {
  const files = retryableFiles(result)
  if (files.length === 0) break
  console.log(`::warning::Running ${files.length} test file(s) again after a stall or a dynamic import failure: ${files.join(", ")}`)
  result = await attempt(`run ${run}`, files.map(quote))
}
process.exit(result.passed ? 0 : 1)
