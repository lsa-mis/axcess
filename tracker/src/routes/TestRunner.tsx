/**
 * Test Runner: walks a tester through one module's checks, one check
 * at a time. Each step shows the expected behavior, takes pass / fail /
 * not applicable plus notes, and offers evidence capture: a screenshot
 * upload and a paste field for screen reader output.
 *
 * A fail writes an issue through store.createIssue, which enforces the
 * one-check-one-page invariant and stamps the tier that found it.
 *
 * Accessibility notes for this screen specifically:
 * - The step content lives inside a section with aria-labelledby so
 *   screen reader users hear which check they are on.
 * - After recording a result, focus moves to the next-step heading via
 *   a ref, so keyboard users never lose their place.
 * - The progress indicator is text, not a color bar alone.
 */

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { checksForModule } from "../data/checks";
import { store } from "../data/store";
import { useAppData } from "../data/useStore";
import { MODULE_TITLE } from "../data/types";
import type {
  CheckResult,
  Evidence,
  ModuleId,
  Severity,
  TestRun,
} from "../data/types";
import {
  Button,
  Card,
  Field,
  PageTitle,
  SampleTag,
  TierBadge,
  cn,
  inputClass,
} from "../components/ui";

const MODULES: ModuleId[] = ["A", "B", "C", "D", "E", "F"];

/** Modules already built out in the iteration loop. The rest stay
    visible but disabled so the roadmap is honest in the UI. */
const ENABLED_MODULES: ModuleId[] = ["A"];

export default function TestRunnerRoute() {
  const data = useAppData();
  const [params, setParams] = useSearchParams();
  const [run, setRun] = useState<TestRun | null>(null);
  const [stepIndex, setStepIndex] = useState(0);

  const siteId = params.get("site") ?? "";
  const pageId = params.get("page") ?? "";
  const module = (params.get("module") ?? "") as ModuleId | "";

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const sitePages = data.pages.filter((p) => p.siteId === siteId);
  const checks = module ? checksForModule(module) : [];

  if (run) {
    return (
      <RunnerSession
        run={run}
        stepIndex={stepIndex}
        onStep={setStepIndex}
        onExit={() => {
          store.finishTestRun(run.id);
          setRun(null);
          setStepIndex(0);
        }}
      />
    );
  }

  const canStart =
    siteId !== "" &&
    pageId !== "" &&
    module !== "" &&
    ENABLED_MODULES.includes(module as ModuleId);

  return (
    <>
      <PageTitle
        title="Test Runner"
        subtitle="Pick a site, a page, and a module. The runner walks you through each check, one at a time."
      />
      <Card className="max-w-2xl p-4">
        <div className="flex flex-col gap-4">
          <Field label="Site" htmlFor="runner-site">
            <select
              id="runner-site"
              className={inputClass}
              value={siteId}
              onChange={(e) => {
                setParam("site", e.target.value);
                setParam("page", "");
              }}
            >
              <option value="">Choose a site</option>
              {data.sites.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                  {s.isSample ? " (sample)" : ""}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Page" htmlFor="runner-page">
            <select
              id="runner-page"
              className={inputClass}
              value={pageId}
              onChange={(e) => setParam("page", e.target.value)}
              disabled={!siteId}
            >
              <option value="">
                {siteId ? "Choose a page" : "Choose a site first"}
              </option>
              {sitePages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </Field>

          <fieldset className="flex flex-col gap-2">
            <legend className="font-semibold text-ink">Module</legend>
            {MODULES.map((m) => {
              const enabled = ENABLED_MODULES.includes(m);
              const count = checksForModule(m).length;
              return (
                <label
                  key={m}
                  className={cn(
                    "flex min-h-target cursor-pointer items-center gap-3 rounded border border-line px-3 py-2",
                    module === m && "border-brand bg-brand/5",
                    !enabled && "cursor-not-allowed opacity-60",
                  )}
                >
                  <input
                    type="radio"
                    name="module"
                    value={m}
                    checked={module === m}
                    disabled={!enabled}
                    onChange={(e) => setParam("module", e.target.value)}
                    className="h-5 w-5"
                  />
                  <span className="font-semibold">
                    Module {m}: {MODULE_TITLE[m]}
                  </span>
                  <span className="ml-auto text-sm text-ink-muted">
                    {count} checks{enabled ? "" : ", coming in a later iteration"}
                  </span>
                </label>
              );
            })}
          </fieldset>

          <div>
            <Button
              variant="primary"
              disabled={!canStart}
              onClick={() => {
                const newRun = store.startTestRun(
                  siteId,
                  pageId,
                  module as ModuleId,
                );
                setRun(newRun);
                setStepIndex(0);
              }}
            >
              Start run: {checks.length > 0 ? `${checks.length} checks` : "pick a module"}
            </Button>
          </div>
        </div>
      </Card>
    </>
  );
}

function RunnerSession({
  run,
  stepIndex,
  onStep,
  onExit,
}: {
  run: TestRun;
  stepIndex: number;
  onStep: (i: number) => void;
  onExit: () => void;
}) {
  const data = useAppData();
  const checks = checksForModule(run.module);
  const check = checks[stepIndex];
  const page = data.pages.find((p) => p.id === run.pageId);
  const site = data.sites.find((s) => s.id === run.siteId);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const [notes, setNotes] = useState("");
  const [severity, setSeverity] = useState<Severity>("serious");
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [srOutput, setSrOutput] = useState("");
  const [recorded, setRecorded] = useState<CheckResult | null>(null);

  // Move focus to the step heading whenever the step changes, so a
  // keyboard or screen reader user lands on the new check immediately.
  useEffect(() => {
    headingRef.current?.focus();
  }, [stepIndex]);

  if (!check || !page || !site) {
    return (
      <Card className="p-4">
        <p>This run has no more checks, or its page was removed.</p>
        <Button onClick={onExit} className="mt-3">
          Back to runner setup
        </Button>
      </Card>
    );
  }

  const evidence: Evidence = {
    screenshot,
    screenReaderOutput: srOutput.trim() ? srOutput.trim() : null,
  };

  const resetStepState = () => {
    setNotes("");
    setSeverity("serious");
    setScreenshot(null);
    setSrOutput("");
    setRecorded(null);
  };

  const record = (result: CheckResult) => {
    store.recordResult(run.id, check.id, result, notes);
    if (result === "fail") {
      store.createIssue({
        checkId: check.id,
        pageId: page.id,
        testRunId: run.id,
        severity,
        notes,
        evidence,
      });
    }
    setRecorded(result);
  };

  const next = () => {
    resetStepState();
    if (stepIndex + 1 >= checks.length) {
      onExit();
    } else {
      onStep(stepIndex + 1);
    }
  };

  const onScreenshotChange = (file: File | null) => {
    if (!file) {
      setScreenshot(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setScreenshot(String(reader.result));
    reader.readAsDataURL(file);
  };

  return (
    <>
      <PageTitle
        title={`Module ${run.module}: ${MODULE_TITLE[run.module]}`}
        subtitle={
          <>
            Testing <strong>{page.title}</strong> on {site.name}
            {site.isSample ? (
              <>
                {" "}
                <SampleTag />
              </>
            ) : null}
          </>
        }
        actions={
          <Button onClick={onExit}>Save and exit run</Button>
        }
      />

      <p className="mb-3 font-semibold text-ink-muted" aria-live="polite">
        Check {stepIndex + 1} of {checks.length}
      </p>

      <Card className="max-w-3xl p-5">
        <section aria-labelledby="check-heading">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <TierBadge tier={check.tier} />
            <span className="text-sm font-semibold text-ink-muted">
              WCAG {check.wcag}
            </span>
          </div>
          <h2
            id="check-heading"
            ref={headingRef}
            tabIndex={-1}
            className="text-xl font-bold text-ink"
          >
            {check.title}
          </h2>
          <h3 className="mt-3 text-sm font-bold uppercase tracking-wide text-ink-muted">
            What to verify
          </h3>
          <p className="mt-1 text-ink">{check.expectedBehavior}</p>

          <div className="mt-4 flex flex-col gap-4">
            <Field
              label="Notes"
              htmlFor="step-notes"
              hint="What you observed. Required for a fail, helpful for everything else."
            >
              <textarea
                id="step-notes"
                className={cn(inputClass, "min-h-[5rem]")}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </Field>

            <Field
              label="Severity if this fails"
              htmlFor="step-severity"
            >
              <select
                id="step-severity"
                className={inputClass}
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
              >
                <option value="critical">Critical: blocks the task</option>
                <option value="serious">Serious: major barrier</option>
                <option value="moderate">Moderate: meaningful friction</option>
                <option value="minor">Minor: small friction</option>
              </select>
            </Field>

            <Field
              label="Evidence: screenshot"
              htmlFor="step-screenshot"
              hint="Optional. Attach a capture of what you saw."
            >
              <input
                id="step-screenshot"
                type="file"
                accept="image/*"
                className="min-h-target text-ink"
                onChange={(e) => onScreenshotChange(e.target.files?.[0] ?? null)}
              />
            </Field>
            {screenshot ? (
              <img
                src={screenshot}
                alt="Screenshot evidence you attached for this check"
                className="max-h-48 w-auto rounded border border-line"
              />
            ) : null}

            <Field
              label="Evidence: screen reader output"
              htmlFor="step-sr"
              hint="Optional. Paste what the screen reader announced."
            >
              <textarea
                id="step-sr"
                className={cn(inputClass, "min-h-[4rem] font-mono text-sm")}
                value={srOutput}
                onChange={(e) => setSrOutput(e.target.value)}
              />
            </Field>
          </div>

          {recorded === null ? (
            <div
              className="mt-5 flex flex-wrap gap-2"
              role="group"
              aria-label="Record the result for this check"
            >
              <Button variant="primary" onClick={() => record("pass")}>
                Pass
              </Button>
              <Button variant="danger" onClick={() => record("fail")}>
                Fail: log an issue
              </Button>
              <Button onClick={() => record("not_applicable")}>
                Not applicable
              </Button>
            </div>
          ) : (
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <p className="font-semibold" role="status">
                {recorded === "fail"
                  ? "Issue logged with the evidence above."
                  : `Recorded: ${recorded === "not_applicable" ? "not applicable" : "pass"}.`}
              </p>
              <Button variant="primary" onClick={next}>
                {stepIndex + 1 >= checks.length
                  ? "Finish run"
                  : "Next check"}
              </Button>
            </div>
          )}
        </section>
      </Card>
    </>
  );
}
