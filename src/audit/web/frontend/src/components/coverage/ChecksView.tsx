import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { CheckCriterion, CheckMethod, CoverageChecks, WcagVersion } from "../../api/types";
import { cn } from "../../lib/cn";
import {
  CHECK_LABEL,
  CHECK_METHOD_BLURB,
  CHECK_METHOD_LABEL,
  CHECK_METHOD_TECH,
  STUDY_CHECK_LABEL,
} from "../../lib/terms";
import { PUBLIC_DEFAULTS } from "../newScan/scanPolicy";
import Loading from "../Loading";
import { Button, Card, Disclosure, Select } from "../ui";
import { Cell, ColumnHeader, Row, RowHeader, Table, TableHead, TableRegion, TableSearch } from "../table/Table";
import {
  ExternalTextLink,
  METHOD_EDGE,
  METHOD_ORDER,
  MethodLabel,
  MethodMark,
  formatCount,
  percent,
} from "./coverageParts";

const VERSIONS: WcagVersion[] = ["2.1", "2.2"];
const PRINCIPLES = ["Perceivable", "Operable", "Understandable", "Robust"];

/**
 * What Axcess checks, for each WCAG criterion (the first part of Coverage).
 *
 * Order: the one-sentence answer, then the criteria map with its filter
 * buttons directly above it, then the study estimate, the most common
 * problems, and how each check works. The map comes first because it is the
 * part people use; the filter buttons sit right on top of it so choosing one
 * visibly changes what is under it (user testing, 13 Nov 2026: with the
 * filter further up, the change happened out of sight and read as broken).
 *
 * Filter, search, version and chosen criterion live in the URL, as on the
 * Issues page, so a view can be bookmarked and Back works.
 *
 * Rejected: a bar chart per guideline, a weighted "depth" score with sliders,
 * and a criteria table beside the map. They repeated what the map shows (W3C
 * COGA "Making Content Usable", paraphrased: one way to do one thing, and no
 * duplicate controls), and the depth score's weights were guesses that
 * produced a made-up number.
 */
export default function ChecksView({ foundBySc }: { foundBySc: Map<string, number> | null }) {
  const [params, setParams] = useSearchParams();
  const version: WcagVersion = params.get("version") === "2.2" ? "2.2" : "2.1";
  const { data, isLoading, error } = useQuery({
    queryKey: ["coverage-checks", version],
    queryFn: () => api.getCoverageChecks(version),
  });

  const set = (updates: Record<string, string>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(updates)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setParams(next, { replace: true });
  };

  if (error) {
    return (
      <Card className="p-4">
        <p role="alert" className="text-sm text-sev-critical">
          Axcess could not load what it checks: {error instanceof Error ? error.message : String(error)}
        </p>
      </Card>
    );
  }
  if (isLoading || !data) return <Loading label="Loading what Axcess checks" />;
  return <Checks data={data} params={params} set={set} foundBySc={foundBySc} />;
}

function Checks({
  data,
  params,
  set,
  foundBySc,
}: {
  data: CoverageChecks;
  params: URLSearchParams;
  set: (updates: Record<string, string>) => void;
  foundBySc: Map<string, number> | null;
}) {
  const all = data.criteria;
  const methods = METHOD_ORDER.filter((m) => all.some((c) => c.method === m));
  const rawType = params.get("type") ?? "";
  const type = (methods as string[]).includes(rawType) ? (rawType as CheckMethod) : "";
  const q = (params.get("q") ?? "").trim().toLowerCase();
  const searchMatch = (c: CheckCriterion) => !q || c.sc.includes(q) || c.name.toLowerCase().includes(q);
  const matches = (c: CheckCriterion) => searchMatch(c) && (!type || c.method === type);
  const shown = all.filter(matches);
  const count = (m: CheckMethod) => all.filter((c) => c.method === m).length;
  const tileCount = (m: CheckMethod) => all.filter((c) => searchMatch(c) && c.method === m).length;
  const filtering = Boolean(type || q);

  const wanted = params.get("criterion") ?? "";
  const selected = shown.find((c) => c.sc === wanted) ?? shown[0] ?? all.find((c) => c.sc === wanted) ?? all[0];

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="checks-summary-h" className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-measure">
          <h2 id="checks-summary-h" className="text-lg font-semibold text-fg">
            What Axcess checks
          </h2>
          <p className="mt-1 text-base leading-7 text-fg">
            Of {all.length} WCAG {data.wcag_version} criteria, Axcess checks <strong>{count("automated")}</strong>,
            partly checks <strong>{count("partial")}</strong> and gives AI hints on{" "}
            <strong>{count("ai-assisted")}</strong>. You check the other <strong>{count("manual")}</strong>.
          </p>
          <p className="mt-1 text-sm text-fg-muted">No scan proves a site meets WCAG.</p>
        </div>
        <Select
          label="WCAG version"
          stacked
          value={data.wcag_version}
          onChange={(value) => set({ version: value, type: "", criterion: "" })}
          options={VERSIONS.map((v) => ({
            value: v,
            label: v === data.scan_default_version ? `WCAG ${v} (what scans use)` : `WCAG ${v}`,
          }))}
        />
      </section>

      <Card className="p-5">
        <section aria-labelledby="map-h" className="flex flex-col gap-4">
          <div>
            <h2 id="map-h" className="text-base font-semibold text-fg">
              Every criterion at a glance
            </h2>
            <p className="mt-1 text-sm text-fg-muted">Filter by type of check. Choose a square for details.</p>
          </div>

          {/* Toggle buttons (aria-pressed), not tabs: they narrow the map in
              place and have no panel each (WAI-ARIA APG Button pattern,
              toggle button). Each says what it means for the tester first and
              its technical name second (docs/plain-language.md rule 3). The
              shared Tabs filter row was considered; its chips hold one word,
              and these must carry a count and a one-line meaning. */}
          <div role="group" aria-labelledby="map-h" className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(11rem,1fr))]">
            {methods.map((m) => {
              const on = type === m;
              return (
                <Button
                  key={m}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set({ type: on ? "" : m, criterion: "" })}
                  className={cn(
                    "h-auto flex-col items-start justify-start gap-1 px-4 py-3 text-left font-normal",
                    METHOD_EDGE[m],
                    on && "border-2 border-umich-blue bg-surface-muted",
                  )}
                >
                  <span className="flex items-center gap-2 text-sm font-semibold text-fg">
                    <MethodMark method={m} />
                    <span className="sr-only">Show only </span>
                    {CHECK_METHOD_LABEL[m]}
                  </span>
                  {/* 4.1.1 Parsing is the W3C's title for the criterion, quoted as written. */}
                  <span className="text-xs text-fg-subtle" data-official-title={m === "not_needed" ? "" : undefined}>
                    {CHECK_METHOD_TECH[m]}
                  </span>
                  <span className="text-2xl font-semibold text-fg">
                    {tileCount(m)}
                    <span className="text-sm font-normal text-fg-muted">{tileCount(m) === 1 ? " criterion" : " criteria"}</span>
                  </span>
                  <span className="text-xs leading-5 text-fg-muted">{CHECK_METHOD_BLURB[m]}</span>
                  {on && <span className="text-xs font-semibold text-fg">✓ Showing only these</span>}
                </Button>
              );
            })}
          </div>

          <div className="flex flex-wrap items-end justify-between gap-3 border-t border-border pt-4">
            <div className="flex flex-wrap items-center gap-3">
              <p role="status" className="text-sm font-semibold text-fg">
                {filtering
                  ? `Showing ${shown.length} of ${all.length}${type ? `: ${CHECK_METHOD_LABEL[type]}` : ""}`
                  : `Showing all ${all.length} criteria`}
              </p>
              {filtering && (
                <Button type="button" onClick={() => set({ type: "", q: "", criterion: "" })}>
                  Show all criteria
                </Button>
              )}
            </div>
            <TableSearch
              label="Find a criterion"
              placeholder="For example, contrast or 2.4"
              value={params.get("q") ?? ""}
              onChange={(value) => set({ q: value, criterion: "" })}
            />
          </div>

          <div className="flex flex-wrap items-start gap-7">
            <div className="flex min-w-0 flex-[1_1_26rem] flex-col gap-5">
              {PRINCIPLES.map((principle) => {
                const rows = all.filter((c) => c.principle === principle);
                if (!rows.length) return null;
                const n = rows.filter(matches).length;
                return (
                  <div key={principle} className="flex flex-col gap-2">
                    <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-muted">
                      {principle}{" "}
                      <span className="font-normal normal-case tracking-normal">
                        · {filtering ? `${n} of ${rows.length} shown` : `${rows.length} criteria`}
                      </span>
                    </h3>
                    {/* Each square is a toggle button showing its number, level
                        and method symbol; its full name, method and whether it
                        is outside the filter are screen-reader text (WCAG
                        technique C7), so the visible text stays short. Kept,
                        not removed, outside the filter, so the grid keeps its
                        shape and the reader keeps their place. Outside the
                        filter a square loses its colour edge and fill and gets
                        a dashed border, but its text keeps full contrast: an
                        earlier version faded the whole square to 30% and failed
                        SC 1.4.3 Contrast (Minimum), Level AA (axe, 13 Nov 2026). */}
                    <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(5.25rem,1fr))]">
                      {rows.map((c) => {
                        const on = c.sc === selected.sc;
                        const inFilter = matches(c);
                        return (
                          <Button
                            key={c.sc}
                            type="button"
                            variant="ghost"
                            aria-pressed={on}
                            onClick={() => set({ criterion: c.sc })}
                            className={cn(
                              "relative h-auto min-h-16 flex-col items-start justify-start gap-1.5 border px-2.5 pb-2 pt-3 text-left",
                              inFilter
                                ? cn("border-border bg-surface-subtle", METHOD_EDGE[c.method])
                                : "border-dashed border-border bg-transparent font-normal shadow-none",
                              on && "border-solid border-fg ring-2 ring-fg",
                            )}
                          >
                            <span className={cn("text-sm", inFilter ? "font-bold text-fg" : "font-medium text-fg-muted")}>
                              {c.sc}
                            </span>
                            <span className="flex items-center gap-1.5 text-xs font-semibold text-fg-muted">
                              <MethodMark method={c.method} />
                              {c.level}
                            </span>
                            {/* Sentences, so each part starts with a capital where a
                                reader expects one. The criterion's name is the
                                W3C's own title, quoted as written. */}
                            <span className="sr-only">
                              . <span data-official-title="">{c.name}</span>. {CHECK_METHOD_LABEL[c.method]}.
                              {inFilter ? " Not in your filter." : ""}
                            </span>
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
            <CriterionPanel criterion={selected} version={data.wcag_version} found={foundBySc} />
          </div>
        </section>
      </Card>

      <StudyCard data={data} shown={shown} filtering={filtering} typeLabel={type ? CHECK_METHOD_LABEL[type] : ""} q={params.get("q") ?? ""} />
      <CommonProblems data={data} />
      <HowAxcessTests />
    </div>
  );
}

/**
 * The chosen criterion. Its heading changes with the choice and a polite
 * status line names it, so a screen reader hears what opened without focus
 * leaving the square (WAI-ARIA APG, paraphrased: a live region announces a
 * change the user did not move focus to). The whole panel is not a live
 * region: re-reading every row on each choice would drown the announcement.
 */
function CriterionPanel({
  criterion: c,
  version,
  found,
}: {
  criterion: CheckCriterion;
  version: WcagVersion;
  found: Map<string, number> | null;
}) {
  const checked = c.checks.length > 0;
  const n = found?.get(c.sc) ?? 0;
  const study = c.study;
  return (
    <div className="flex min-w-0 flex-[1_1_22rem] flex-col gap-3.5 pt-6">
      <p role="status" className="sr-only">
        Showing {c.sc} {c.name}
      </p>
      <h3 className="text-lg font-semibold text-fg">
        {c.sc} {c.name}
      </h3>
      <p className="text-sm">
        <ExternalTextLink standalone href={c.understanding_url} detail={`Understanding ${c.sc}, WCAG ${version}`}>
          Read WCAG {c.sc} on the W3C site
        </ExternalTextLink>
      </p>
      <ul aria-label="Summary" className="flex flex-wrap gap-2">
        <li className="flex min-h-8 items-center rounded-full bg-surface-muted px-3 text-sm">
          <MethodLabel method={c.method} />
        </li>
        <li className="flex min-h-8 items-center rounded-full bg-surface-muted px-3 text-sm">Level {c.level}</li>
      </ul>

      {c.method === "not_needed" ? (
        <p className="max-w-measure text-base leading-7">
          WCAG 2.2 removed this criterion. The W3C now says today&apos;s HTML always meets it, so there is nothing for
          Axcess or you to check. It is listed because it is still part of WCAG 2.1.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-[minmax(0,10.5rem)_minmax(0,1fr)] gap-x-5 gap-y-3 text-base leading-7">
            <dt className="text-fg-subtle">What Axcess does</dt>
            <dd>{c.does || "Nothing. Axcess can't test this one."}</dd>
            <dt className="text-fg-subtle">What you still check</dt>
            <dd>{c.you}</dd>
            {checked && (
              <>
                <dt className="text-fg-subtle">Checks used</dt>
                <dd>{c.checks.map((p) => CHECK_LABEL[p]).join(", ")}</dd>
              </>
            )}
            <dt className="text-fg-subtle">How common</dt>
            <dd>
              {study
                ? `${percent(study.share)} of all problems. Axcess finds about ${percent(study.rule_check + study.other_checks)} of them.`
                : "Not listed on its own in the study."}
            </dd>
            {checked && (
              <>
                <dt className="text-fg-subtle">Found in your reports</dt>
                <dd>
                  {found === null ? (
                    "Not counted yet"
                  ) : n > 0 ? (
                    <Link to="/coverage/found" className="text-umich-blue underline underline-offset-2">
                      {formatCount(n)} {n === 1 ? "occurrence" : "occurrences"}
                    </Link>
                  ) : (
                    "None found yet"
                  )}
                </dd>
              </>
            )}
          </dl>
          <Disclosure id={`dev-${c.sc}`} title="Details for developers" headingLevel={4}>
            <DeveloperDetails criterion={c} />
          </Disclosure>
        </>
      )}
    </div>
  );
}

function DeveloperDetails({ criterion: c }: { criterion: CheckCriterion }) {
  return (
    <div className="flex flex-col gap-4 text-sm leading-6 text-fg-muted">
      <dl className="grid grid-cols-[minmax(0,10.5rem)_minmax(0,1fr)] gap-x-5 gap-y-2">
        <dt>Guideline</dt>
        <dd className="text-fg">{c.guideline}</dd>
        <dt>How sure (confidence)</dt>
        <dd className="text-fg">{c.confidence === "n/a" ? "Does not apply" : c.confidence}</dd>
        {c.technical && (
          <>
            <dt>How the check works</dt>
            <dd className="text-fg">{c.technical}</dd>
          </>
        )}
      </dl>
      {c.rules.length > 0 && (
      <section aria-labelledby={`rules-${c.sc}`}>
        <h5 id={`rules-${c.sc}`} className="font-semibold text-fg">
          Rule check (axe) rules
        </h5>
        {(
          // Each rule's own description is shown, not hidden behind hover:
          // text that appears only on hover is out of reach by keyboard and
          // touch (SC 1.4.13 Content on Hover or Focus, Level AA, and its
          // Understanding document).
          <ul className="mt-2 flex flex-col gap-2.5">
            {c.rules.map((rule) => (
              <li key={rule.id} className="border-l-[3px] border-border pl-3">
                <p>
                  <code className="rounded-2xs bg-surface-muted px-1 text-xs text-fg">{rule.id}</code>{" "}
                  <span className="font-semibold text-fg">{rule.help}</span>
                </p>
                <p>Checks: {rule.description}</p>
                <ExternalTextLink standalone href={rule.url}>
                  Deque&apos;s page for {rule.id}
                </ExternalTextLink>
              </li>
            ))}
          </ul>
        )}
      </section>
      )}
      <section aria-labelledby={`apg-${c.sc}`}>
        <h5 id={`apg-${c.sc}`} className="font-semibold text-fg">
          WAI-ARIA Authoring Practices (APG)
        </h5>
        {c.apg.length === 0 ? (
          <p>No APG page covers this criterion. The APG is about building widgets.</p>
        ) : (
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
            {c.apg.map((page) => (
              <li key={page.url}>
                <ExternalTextLink standalone href={page.url} detail="WAI-ARIA Authoring Practices Guide">
                  {page.title}
                </ExternalTextLink>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/**
 * The study estimate, following the filter and search. Only study rows for
 * the criteria shown are summed; "All other criteria" is a group the study
 * cannot split, so a filtered view leaves it out and says how many shown
 * criteria that skips. The "For:" tag names the current choice in the same
 * words as the filter buttons (SC 3.2.4 Consistent Identification, Level AA).
 */
function StudyCard({
  data,
  shown,
  filtering,
  typeLabel,
  q,
}: {
  data: CoverageChecks;
  shown: CheckCriterion[];
  filtering: boolean;
  typeLabel: string;
  q: string;
}) {
  const rows = useMemo(() => {
    if (!filtering) return data.study;
    const numbers = new Set(shown.map((c) => c.sc));
    return data.study.filter((row) => numbers.has(row.sc));
  }, [data.study, filtering, shown]);
  const total = rows.reduce((sum, row) => sum + row.share, 0);
  const ruleCheck = total ? rows.reduce((sum, row) => sum + row.share * row.rule_check, 0) / total : 0;
  const other = total ? rows.reduce((sum, row) => sum + row.share * row.other_checks, 0) / total : 0;
  const skipped = filtering ? shown.filter((c) => !c.study).length : 0;
  const forText = [typeLabel, q.trim() ? `“${q.trim()}”` : ""].filter(Boolean).join(", ") || "All criteria";
  const byNumber = new Map(data.criteria.map((c) => [c.sc, c.name]));

  return (
    <Card className="p-5">
      <section aria-labelledby="study-h" className="flex flex-col gap-3.5">
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="study-h" className="text-base font-semibold text-fg">
            Share of real problems Axcess finds
          </h2>
          <span className="rounded-2xs bg-sev-major-bg px-2 py-0.5 text-xs font-bold text-sev-major">Estimate</span>
          <span
            className={cn(
              "rounded-full px-2.5 py-0.5 text-xs font-bold",
              filtering ? "bg-umich-blue text-fg-inverse" : "bg-surface-muted text-fg-muted",
            )}
          >
            For: {forText}
          </span>
        </div>
        {total === 0 ? (
          <p className="font-semibold text-fg">
            The study has no separate numbers for the criteria shown. It groups them under “All other criteria”.
          </p>
        ) : (
          <>
            <p className="max-w-measure text-base">
              {filtering
                ? `The ${rows.length} ${rows.length === 1 ? "criterion" : "criteria"} shown that the study lists cause ${percent(total)} of all problems. Of those problems:`
                : "All criteria, counted by how often each problem occurs on a typical website (4.1.1 left out)."}
            </p>
            <dl className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(10rem,1fr))]">
              {[
                [percent(ruleCheck), "rule check (axe)"],
                [`+${percent(other)}`, "other checks"],
                [percent(ruleCheck + other), "Axcess in total"],
                [percent(1 - ruleCheck - other), "left for you"],
              ].map(([value, label]) => (
                <div key={label} className="flex flex-col-reverse rounded-xs border border-border bg-surface-subtle px-4 py-3">
                  <dt className="text-sm text-fg-muted">{label}</dt>
                  <dd className="text-3xl font-semibold text-fg">{value}</dd>
                </div>
              ))}
            </dl>
          </>
        )}
        {skipped > 0 && (
          <p className="text-xs text-fg-subtle">
            {skipped} {skipped === 1 ? "criterion shown is" : "criteria shown are"} not listed on its own in the study,
            so not counted here.
          </p>
        )}
        <p className="max-w-measure text-sm text-fg-muted">
          Source:{" "}
          <ExternalTextLink href={data.study_source_url} detail="Deque's Automated Accessibility Coverage Report">
            Deque, 2,000+ audits of its clients&apos; sites
          </ExternalTextLink>
          . Deque makes the rule check. For your sites, see{" "}
          <Link to="/coverage/found" className="text-umich-blue underline underline-offset-2">
            What Axcess found
          </Link>
          .
        </p>
        {rows.length > 0 && (
          <Disclosure id="study-rows" title="Numbers for each criterion" headingLevel={3}>
            <TableRegion label="Study numbers for each criterion">
              <Table caption="Share of problems and share found, by criterion" captionClassName="px-4 py-2 text-left text-sm font-semibold">
                <TableHead>
                  <tr>
                    <ColumnHeader>WCAG criterion</ColumnHeader>
                    <ColumnHeader>Share of all problems</ColumnHeader>
                    <ColumnHeader>Found by the rule check</ColumnHeader>
                    <ColumnHeader>Also found by other checks</ColumnHeader>
                    <ColumnHeader>Which other checks</ColumnHeader>
                  </tr>
                </TableHead>
                <tbody>
                  {rows.map((row, index) => (
                    <Row key={row.sc} index={index}>
                      <RowHeader className="font-medium">
                        {row.sc === "other" ? "All other criteria" : `${row.sc} ${byNumber.get(row.sc) ?? ""}`}
                      </RowHeader>
                      <Cell numeric>{percent(row.share)}</Cell>
                      <Cell numeric>{percent(row.rule_check)}</Cell>
                      <Cell numeric>{row.other_checks ? `+${percent(row.other_checks)}` : "None"}</Cell>
                      <Cell>{row.checks.map((check) => STUDY_CHECK_LABEL[check]).join(", ") || "None"}</Cell>
                    </Row>
                  ))}
                </tbody>
              </Table>
            </TableRegion>
            <p className="mt-2 text-xs text-fg-subtle">
              “Other checks” is a judgment, not a measurement. It assumes each finds{" "}
              {Math.round(data.other_checks_hit_rate * 10)} in 10 of its problems, and that the AI checks are turned on.
            </p>
          </Disclosure>
        )}
      </section>
    </Card>
  );
}

function CommonProblems({ data }: { data: CoverageChecks }) {
  return (
    <Card className="p-5">
      <section aria-labelledby="common-h" className="flex flex-col gap-3">
        <h2 id="common-h" className="text-base font-semibold text-fg">
          Most common website problems
        </h2>
        <p className="max-w-measure text-base">
          96% of errors found by a program on the top 1,000,000 home pages. Axcess checks all six.
        </p>
        {/* A list with the share as words; the bar is decoration that only
            repeats the number (aria-hidden). */}
        <ul className="flex flex-col gap-2.5">
          {data.common_problems.map((problem) => (
            <li key={problem.rule} className="grid items-center gap-3 sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]">
              <span className="text-base">{problem.label}</span>
              <span className="flex items-center gap-3">
                <span aria-hidden className="h-3 flex-1 rounded-full bg-surface-muted">
                  <span
                    className="block h-3 rounded-full bg-umich-blue"
                    style={{ width: `${problem.share_of_sites * 100}%` }}
                  />
                </span>
                <span className="min-w-28 text-sm font-semibold">{percent(problem.share_of_sites)} of sites</span>
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-fg-subtle">
          Source:{" "}
          <ExternalTextLink standalone href={data.common_source_url}>
            WebAIM Million, February 2026
          </ExternalTextLink>
          .
        </p>
      </section>
    </Card>
  );
}

/**
 * How each check works, and whether a new scan runs it. "On" comes from the
 * New scan form's own defaults (newScan/scanPolicy.ts), so this page cannot
 * claim a check runs when the form has it off. A tag says on or off in words
 * and with a filled or dashed shape, never colour alone (SC 1.4.1).
 */
const HOW: { name: string; on: boolean; criteria: string; points: string[] }[] = [
  {
    name: CHECK_LABEL.axe,
    on: PUBLIC_DEFAULTS.scan_engine !== "alfa",
    criteria: "All criteria it has rules for",
    points: [
      "Tests the page code against fixed rules for your WCAG version.",
      "Reports only clear failures. Borderline cases are left to you.",
    ],
  },
  {
    name: "Click-Through",
    on: !PUBLIC_DEFAULTS.skip_interaction,
    criteria: "Rule check criteria",
    points: [
      "Opens menus, tabs and dialogs, then runs the rule check on what appears.",
      "Never clicks Delete, Buy, Submit, Save, Send or Sign out.",
      "Stops after 100 clicks or 2 minutes per page.",
    ],
  },
  {
    name: CHECK_LABEL.responsive,
    on: !PUBLIC_DEFAULTS.skip_responsive,
    criteria: "1.4.4, 1.4.10, 1.4.12",
    points: [
      "Finds sideways scrolling at 320 pixels wide.",
      "Finds text cut off at a 200% zoom size or with wider spacing.",
    ],
  },
  {
    name: CHECK_LABEL.keyboard,
    on: !PUBLIC_DEFAULTS.skip_keyboard,
    criteria: "2.1.2",
    points: ["Finds places where Tab and Shift+Tab can't move focus."],
  },
  {
    name: CHECK_LABEL.focus,
    on: !PUBLIC_DEFAULTS.skip_focus,
    criteria: "2.4.3, 2.4.11",
    points: ["Finds elements that change the normal Tab order.", "Finds focused controls hidden behind sticky bars."],
  },
  {
    name: CHECK_LABEL.image,
    on: !PUBLIC_DEFAULTS.skip_ocr,
    criteria: "1.1.1, 1.4.5",
    points: [
      "Reads text in images and compares it with the alt text.",
      PUBLIC_DEFAULTS.skip_vlm
        ? "Sorting images by purpose uses AI, which is off by default."
        : "AI sorts images by purpose. Needs Ollama.",
    ],
  },
  {
    name: CHECK_LABEL.visual,
    on: !PUBLIC_DEFAULTS.skip_visual,
    criteria: "1.3.2, 1.4.2, 2.2.2",
    points: [
      "Finds sound or video that plays on its own with no control.",
      "AI compares the on-screen order with the page-code order. Needs Ollama.",
    ],
  },
  {
    name: CHECK_LABEL.semantic,
    on: !PUBLIC_DEFAULTS.skip_semantic,
    criteria: "1.2.1, 2.4.4, 2.4.6, 3.3.2",
    points: [
      "AI judges link text, headings, form labels and transcripts. Needs Ollama.",
      "Every result is a hint for you to confirm.",
    ],
  },
  {
    name: CHECK_LABEL.alfa,
    on: PUBLIC_DEFAULTS.scan_engine !== "axe",
    criteria: "Many criteria",
    points: ["A second set of rules. Not counted on this page."],
  },
];

function HowAxcessTests() {
  return (
    <Card className="p-5">
      <section aria-labelledby="how-h" className="flex flex-col gap-3">
        <h2 id="how-h" className="text-base font-semibold text-fg">
          How Axcess tests a page
        </h2>
        <p className="max-w-measure text-base">
          Each page opens in a real browser, then the checks that are on run. You turn checks on or off in{" "}
          <Link to="/scans/new" className="text-umich-blue underline underline-offset-2">
            New scan
          </Link>
          .
        </p>
        <div className="flex flex-col gap-2">
          {HOW.map((check) => (
            <Disclosure
              key={check.name}
              id={`how-${check.name.replace(/\W+/g, "-").toLowerCase()}`}
              title={check.name}
              headingLevel={3}
              meta={
                <span className="flex flex-wrap items-center justify-end gap-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 font-bold",
                      check.on ? "bg-umich-blue text-fg-inverse" : "border border-dashed border-border-strong text-fg-muted",
                    )}
                  >
                    {check.on ? "✓ On in a new scan" : "○ Off unless you turn it on"}
                  </span>
                  <span className="font-normal text-fg-subtle">{check.criteria}</span>
                </span>
              }
            >
              <ul className="flex list-disc flex-col gap-1.5 pl-5 text-base leading-7">
                {check.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </Disclosure>
          ))}
        </div>
      </section>
    </Card>
  );
}
