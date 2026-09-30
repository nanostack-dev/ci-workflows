// Vitest reporter used by run.mjs. It appends one JSON line per test file event
// to $VITEST_WATCHDOG_PROGRESS, so the watchdog can see which files are still in
// flight without parsing the human-readable output.
import { appendFileSync } from "node:fs"

const progressFile = process.env.VITEST_WATCHDOG_PROGRESS

const DYNAMIC_IMPORT_FAILURE = "Failed to fetch dynamically imported module"

function write(event) {
  appendFileSync(progressFile, `${JSON.stringify({ ...event, at: Date.now() })}\n`)
}

export default class WatchdogProgressReporter {
  onInit(vitest) {
    this.vitest = vitest
  }

  // Vitest reports every file here, before it applies --shard. The same
  // sequencer call Vitest makes gives this shard's files.
  async onTestRunStart(specifications) {
    const { shard, sequence } = this.vitest.config
    const files = shard ? await new sequence.sequencer(this.vitest).shard([...specifications]) : specifications
    write({ event: "start", files: files.map((spec) => spec.moduleId) })
  }

  onTestModuleQueued(testModule) {
    write({ event: "queued", file: testModule.moduleId })
  }

  onTestModuleCollected(testModule) {
    write({ event: "collected", file: testModule.moduleId })
  }

  onTestModuleEnd(testModule) {
    const errors = testModule.errors()
    write({
      event: "end",
      file: testModule.moduleId,
      state: testModule.state(),
      // The fetch error is the `cause` of "Failed to import test file".
      importFailed: errors.some((error) => JSON.stringify(error).includes(DYNAMIC_IMPORT_FAILURE)),
    })
  }

  onTestRunEnd(_testModules, unhandledErrors, reason) {
    write({ event: "run-end", reason, unhandledErrors: unhandledErrors.length })
  }
}
