// stopChildProcess: quitting the desktop app waits for the backend to stop,
// and kills it only if it does not (runtime.cjs). On 2026-11-20 closed apps
// left their backends and scan browsers running for hours.
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const test = require("node:test");
const { stopChildProcess } = require("../src/runtime.cjs");

function child(source) {
  return spawn(process.execPath, ["-e", source], { stdio: ["pipe", "ignore", "ignore"] });
}

test("a child that stops when its input closes is waited for, not killed", async () => {
  const proc = child("process.stdin.resume(); process.stdin.on('end', () => setTimeout(() => process.exit(0), 200));");
  const outcome = await stopChildProcess(proc, { graceMs: 5_000 });
  assert.equal(outcome, "exited");
  assert.equal(proc.exitCode, 0);
});

test("a child that ignores the request is killed after the wait", async () => {
  const proc = child("process.stdin.resume(); process.on('SIGTERM', () => {}); setInterval(() => {}, 1000);");
  const started = Date.now();
  const outcome = await stopChildProcess(proc, { graceMs: 300 });
  assert.equal(outcome, "killed");
  assert.ok(Date.now() - started >= 300);
  assert.equal(proc.signalCode, "SIGKILL");
});

test("a child that has already exited resolves at once", async () => {
  const proc = child("process.exit(0)");
  await new Promise((resolve) => proc.once("exit", resolve));
  assert.equal(await stopChildProcess(proc, { graceMs: 5_000 }), "exited");
});
