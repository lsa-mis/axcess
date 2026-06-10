/**
 * Local-first JSON store.
 *
 * One document in localStorage holds every table. Components subscribe
 * through useSyncExternalStore (see useStore.ts) and all writes go
 * through mutate(), which persists and notifies in one step.
 *
 * The store also owns the data invariant from the brief:
 * every issue points at exactly one existing check and exactly one
 * existing page. createIssue throws if either reference is missing,
 * so a floating issue cannot enter the system through any UI path.
 */

import { CHECK_CATALOG } from "./checks";
import { SEED_PAGES, SEED_ROLES, SEED_SITES, SEED_USERS } from "./seed";
import type {
  AppData,
  Check,
  CheckResult,
  Evidence,
  Issue,
  IssueStatus,
  ModuleId,
  Remediation,
  Severity,
  TestRun,
} from "./types";

const STORAGE_KEY = "a11y-tracker-v1";

type Listener = () => void;

function emptyData(): AppData {
  return {
    sites: SEED_SITES,
    pages: SEED_PAGES,
    components: [],
    checks: CHECK_CATALOG,
    testRuns: [],
    issues: [],
    remediations: [],
    users: SEED_USERS,
    roles: SEED_ROLES,
  };
}

function loadFromStorage(): AppData {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyData();
    const parsed = JSON.parse(raw) as AppData;
    // The check catalog is code-owned, not user data: always serve the
    // current catalog so new checks appear without a data reset.
    parsed.checks = CHECK_CATALOG;
    return parsed;
  } catch {
    return emptyData();
  }
}

export function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

class TrackerStore {
  private data: AppData;
  private listeners = new Set<Listener>();

  constructor() {
    this.data = typeof localStorage === "undefined" ? emptyData() : loadFromStorage();
  }

  /** Stable snapshot for useSyncExternalStore. */
  getSnapshot = (): AppData => this.data;

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  /** Apply a mutation, persist, notify. The only write path. */
  mutate(fn: (draft: AppData) => void): void {
    const next: AppData = structuredClone(this.data);
    fn(next);
    this.data = next;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Storage full or unavailable. The in-memory copy still works;
      // Settings surfaces an export button so nothing is lost silently.
    }
    this.listeners.forEach((l) => l());
  }

  /** Drop all user data and restore the seed. Used by Settings. */
  reset(): void {
    this.data = emptyData();
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore: localStorage may be unavailable in private mode.
    }
    this.listeners.forEach((l) => l());
  }

  // ----- domain operations -------------------------------------------

  startTestRun(siteId: string, pageId: string, module: ModuleId): TestRun {
    const run: TestRun = {
      id: newId("run"),
      siteId,
      pageId,
      module,
      startedAt: new Date().toISOString(),
      finishedAt: null,
      results: {},
      notes: {},
    };
    this.mutate((d) => {
      d.testRuns.push(run);
    });
    return run;
  }

  recordResult(
    runId: string,
    checkId: string,
    result: CheckResult,
    notes: string,
  ): void {
    this.mutate((d) => {
      const run = d.testRuns.find((r) => r.id === runId);
      if (!run) return;
      run.results[checkId] = result;
      if (notes.trim()) run.notes[checkId] = notes.trim();
    });
  }

  finishTestRun(runId: string): void {
    this.mutate((d) => {
      const run = d.testRuns.find((r) => r.id === runId);
      if (run && !run.finishedAt) run.finishedAt = new Date().toISOString();
    });
  }

  /**
   * Create an issue. Enforces the invariant: the check and the page
   * must both exist, or this throws and nothing is written.
   */
  createIssue(input: {
    checkId: string;
    pageId: string;
    testRunId: string | null;
    severity: Severity;
    notes: string;
    evidence: Evidence;
  }): Issue {
    const check = this.data.checks.find((c) => c.id === input.checkId);
    if (!check) {
      throw new Error(`createIssue: unknown check ${input.checkId}`);
    }
    const page = this.data.pages.find((p) => p.id === input.pageId);
    if (!page) {
      throw new Error(`createIssue: unknown page ${input.pageId}`);
    }
    const now = new Date().toISOString();
    const issue: Issue = {
      id: newId("issue"),
      checkId: check.id,
      pageId: page.id,
      testRunId: input.testRunId,
      severity: input.severity,
      status: "open",
      foundByTier: check.tier,
      notes: input.notes,
      evidence: input.evidence,
      createdAt: now,
      updatedAt: now,
    };
    this.mutate((d) => {
      d.issues.push(issue);
    });
    return issue;
  }

  setIssueStatus(issueId: string, status: IssueStatus): void {
    this.mutate((d) => {
      const issue = d.issues.find((i) => i.id === issueId);
      if (!issue) return;
      issue.status = status;
      issue.updatedAt = new Date().toISOString();
    });
  }

  addRemediation(issueId: string, assignee: string): Remediation {
    const issue = this.data.issues.find((i) => i.id === issueId);
    if (!issue) {
      throw new Error(`addRemediation: unknown issue ${issueId}`);
    }
    const rem: Remediation = {
      id: newId("rem"),
      issueId,
      assignee,
      status: "todo",
      externalRef: null,
      createdAt: new Date().toISOString(),
    };
    this.mutate((d) => {
      d.remediations.push(rem);
    });
    return rem;
  }

  // ----- lookups ------------------------------------------------------

  check(checkId: string): Check | undefined {
    return this.data.checks.find((c) => c.id === checkId);
  }
}

export const store = new TrackerStore();
