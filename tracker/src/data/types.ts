/**
 * Data model for the accessibility testing tracker.
 *
 * Nine tables, mirroring the brief: sites, pages, components, checks,
 * test_runs, issues, remediations, users, roles. The store (store.ts)
 * owns persistence and the one invariant that must always hold:
 * every issue points at exactly one check and exactly one page.
 */

/** Testing tiers, cheapest first. The Reports view labels these T1 to T5. */
export type Tier =
  | "automated"
  | "ai_assisted"
  | "agentic"
  | "manual"
  | "local_vlm";

export const TIER_LABEL: Record<Tier, string> = {
  automated: "T1 Automated",
  ai_assisted: "T2 AI assisted",
  agentic: "T3 Agentic",
  manual: "T4 Manual",
  local_vlm: "T5 Local VLM",
};

export type ModuleId = "A" | "B" | "C" | "D" | "E" | "F";

export const MODULE_TITLE: Record<ModuleId, string> = {
  A: "Keyboard and focus",
  B: "Screen reader",
  C: "Visual and low vision",
  D: "Cognitive and content",
  E: "Media and motion",
  F: "WCAG 2.2",
};

export type Severity = "critical" | "serious" | "moderate" | "minor";

export type CheckResult = "pass" | "fail" | "not_applicable";

export type IssueStatus =
  | "open"
  | "in_progress"
  | "remediated"
  | "accepted_risk"
  | "false_positive";

export type RoleName = "lead" | "tester" | "developer";

export interface Site {
  id: string;
  name: string;
  baseUrl: string;
  /** Sample rows ship with the app and are labeled in the UI. */
  isSample: boolean;
}

export interface Page {
  id: string;
  siteId: string;
  url: string;
  title: string;
  isSample: boolean;
}

export interface ComponentRecord {
  id: string;
  pageId: string;
  name: string;
  selector: string;
}

export interface Check {
  id: string;
  title: string;
  /** Dotted WCAG criteria, for example "2.4.3" or "1.3.1, 2.4.6". */
  wcag: string;
  module: ModuleId;
  /** Cheapest tier that can clear this check. */
  tier: Tier;
  /** Plain language guidance shown to the tester in the runner. */
  expectedBehavior: string;
}

export interface TestRun {
  id: string;
  siteId: string;
  pageId: string;
  module: ModuleId;
  startedAt: string;
  finishedAt: string | null;
  /** checkId to result, filled in as the tester walks the module. */
  results: Record<string, CheckResult>;
  notes: Record<string, string>;
}

export interface Evidence {
  /** Data URL of an uploaded screenshot, if any. */
  screenshot: string | null;
  /** Pasted screen reader output, if any. */
  screenReaderOutput: string | null;
}

export interface Issue {
  id: string;
  /** Invariant: exactly one check and exactly one page. Never null. */
  checkId: string;
  pageId: string;
  testRunId: string | null;
  severity: Severity;
  status: IssueStatus;
  /** The tier that found the issue, shown as a badge everywhere. */
  foundByTier: Tier;
  notes: string;
  evidence: Evidence;
  createdAt: string;
  updatedAt: string;
}

export interface Remediation {
  id: string;
  issueId: string;
  assignee: string;
  status: "todo" | "doing" | "done";
  /** External handoff reference, for example a JIRA or TDX key. */
  externalRef: string | null;
  createdAt: string;
}

export interface User {
  id: string;
  name: string;
  roleId: string;
}

export interface Role {
  id: string;
  name: RoleName;
}

export interface AppData {
  sites: Site[];
  pages: Page[];
  components: ComponentRecord[];
  checks: Check[];
  testRuns: TestRun[];
  issues: Issue[];
  remediations: Remediation[];
  users: User[];
  roles: Role[];
}
