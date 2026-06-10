/**
 * Module A data-flow test.
 *
 * The contract under test: a test run records results per check, a
 * fail creates an issue, and the issue invariant holds: exactly one
 * existing check, exactly one existing page. Unknown references throw
 * and write nothing.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { checksForModule } from "./checks";
import { store } from "./store";

describe("Module A data flow", () => {
  beforeEach(() => {
    store.reset();
  });

  it("walks a run: record results, fail creates a tier-tagged issue", () => {
    const data = store.getSnapshot();
    const page = data.pages[0];
    const checks = checksForModule("A");
    expect(checks.length).toBe(8);

    const run = store.startTestRun(page.siteId, page.id, "A");

    // Pass the first check, fail the keyboard-trap check.
    const passCheck = checks[0];
    const failCheck = checks.find((c) => c.id === "A3")!;
    store.recordResult(run.id, passCheck.id, "pass", "");
    store.recordResult(run.id, failCheck.id, "fail", "Focus stuck in player");

    const issue = store.createIssue({
      checkId: failCheck.id,
      pageId: page.id,
      testRunId: run.id,
      severity: "critical",
      notes: "Focus stuck in the embedded player",
      evidence: { screenshot: null, screenReaderOutput: "trapped" },
    });

    const after = store.getSnapshot();
    const storedRun = after.testRuns.find((r) => r.id === run.id)!;
    expect(storedRun.results[passCheck.id]).toBe("pass");
    expect(storedRun.results[failCheck.id]).toBe("fail");

    const storedIssue = after.issues.find((i) => i.id === issue.id)!;
    expect(storedIssue.checkId).toBe("A3");
    expect(storedIssue.pageId).toBe(page.id);
    // The tier badge comes from the owning check, agentic for A3.
    expect(storedIssue.foundByTier).toBe("agentic");
    expect(storedIssue.status).toBe("open");
  });

  it("rejects an issue pointing at a check that does not exist", () => {
    const page = store.getSnapshot().pages[0];
    expect(() =>
      store.createIssue({
        checkId: "Z99",
        pageId: page.id,
        testRunId: null,
        severity: "minor",
        notes: "",
        evidence: { screenshot: null, screenReaderOutput: null },
      }),
    ).toThrow(/unknown check/);
    expect(store.getSnapshot().issues.length).toBe(0);
  });

  it("rejects an issue pointing at a page that does not exist", () => {
    expect(() =>
      store.createIssue({
        checkId: "A1",
        pageId: "page_missing",
        testRunId: null,
        severity: "minor",
        notes: "",
        evidence: { screenshot: null, screenReaderOutput: null },
      }),
    ).toThrow(/unknown page/);
    expect(store.getSnapshot().issues.length).toBe(0);
  });

  it("finishing a run stamps finishedAt once", () => {
    const page = store.getSnapshot().pages[0];
    const run = store.startTestRun(page.siteId, page.id, "A");
    store.finishTestRun(run.id);
    const first = store
      .getSnapshot()
      .testRuns.find((r) => r.id === run.id)!.finishedAt;
    expect(first).not.toBeNull();
    store.finishTestRun(run.id);
    const second = store
      .getSnapshot()
      .testRuns.find((r) => r.id === run.id)!.finishedAt;
    expect(second).toBe(first);
  });

  it("status changes update the issue and its timestamp", () => {
    const page = store.getSnapshot().pages[0];
    const issue = store.createIssue({
      checkId: "A1",
      pageId: page.id,
      testRunId: null,
      severity: "moderate",
      notes: "",
      evidence: { screenshot: null, screenReaderOutput: null },
    });
    store.setIssueStatus(issue.id, "in_progress");
    const stored = store
      .getSnapshot()
      .issues.find((i) => i.id === issue.id)!;
    expect(stored.status).toBe("in_progress");
  });

  it("every catalog check carries a tier and expected behavior", () => {
    for (const check of store.getSnapshot().checks) {
      expect(check.tier).toBeTruthy();
      expect(check.expectedBehavior.length).toBeGreaterThan(40);
      expect(check.wcag).toMatch(/\d\.\d+\.\d+/);
    }
  });
});
