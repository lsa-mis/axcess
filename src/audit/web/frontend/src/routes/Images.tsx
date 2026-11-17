import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useParams, useSearchParams } from "react-router";
import { Download } from "lucide-react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import {
  AltCheckOff,
  CurrentAlt,
  IMAGE_PAGES_COLUMN,
  IMAGES_VIEW,
  ImageThumb,
  SuggestionBox,
  VerdictSummary,
  imageName,
  imagePath,
} from "../components/ImageParts";
import ReportHeader from "../components/ReportHeader";
import { SummaryStat } from "../components/ReportSummary";
import Tabs from "../components/Tabs";
import { PagedTable } from "../components/TablePagination";
import {
  Cell,
  ColumnHeader,
  Row,
  RowHeader,
  Table,
  TableBar,
  TableEmpty,
  TableHead,
  TableRegion,
  TableSearch,
  TableStatus,
} from "../components/table/Table";
import { ActiveFilters, FilterMenu, activeFilterItems, type FilterGroup } from "../components/table/FilterMenu";
import { Button, Card, HelpTip, withReturnTrail } from "../components/ui";
import { usePreferences } from "../hooks/usePreferences";
import { useScanQuery } from "../hooks/useScanQuery";
import { cn } from "../lib/cn";
import { ALT_VERDICT_COUNT_LABEL, ALT_VERDICT_LABEL, IMAGE_GROUP_LABEL } from "../lib/terms";
import type { AltVerdict, ImageGroup, ImageGroupCounts, ReportImage, ReportImagesFilter } from "../api/types";

/**
 * The report's Images tab: every image the scan saw, grouped by what to
 * check, with a verdict on its alt text and, on request, alt text the
 * local AI model suggests.
 *
 * Why a tab of its own, and not more Issues rows. The Issues table counts
 * image *issue types* and only images the scan read text in. This tab
 * answers "which images need alt text work?" for every image, including
 * those with no text, which have no issue. It is a view of the same report,
 * so it sits in the report's tab row (REPORT_VIEWS) beside Issues and
 * Compare reports, in that order: Issues stays the landing view.
 *
 * The three groups are questions asked of the list, so an image can be in
 * two ("Images with text" and one of the other two); the "?" after the
 * heading says so. They are the shared `Tabs` in filter mode
 * (aria-pressed toggle buttons over one table), not three tables and not
 * links: the choice narrows this table in place. The Claude Design draft
 * (2026-11-13) drew them as large cards with the verdict split in each;
 * the shared chips were kept instead, one control for one kind of choice
 * across the app (SC 3.2.4 Consistent Identification, Level AA; W3C COGA
 * "Making Content Usable", https://www.w3.org/TR/coga-usable/), and the
 * split moved to the counts on the verdict filter's choices (2026-11-16;
 * before that, a line under the row).
 *
 * Verdicts come from the most direct evidence (src/audit/web/image_inventory.py):
 * the page code, then the text match, then the local model when a person
 * asked. Each verdict cell names its source in words, so a model's view is
 * never shown as if it were a measured fact, and colour is never the only
 * signal (SC 1.4.1 Use of Color, Level A): every chip carries its words.
 *
 * The model runs only when a person presses a row's button, never on load:
 * it sends the image to the model the administrator set up, takes up to a
 * minute or more, and its answer is a lead, not a result. Pressing it
 * announces progress in a polite live region (SC 4.1.3 Status Messages,
 * Level AA) and, when the answer comes, moves focus to it, so focus is not
 * lost when the button is replaced (SC 2.4.3 Focus Order, Level A). A
 * failure is visible text in the row and is also announced.
 */

const PAGE_SIZE = 25;
const PAGER_ID = "pager-report-images";
const GROUPS: ImageGroup[] = ["with_text", "missing_alt", "with_alt"];
const VERDICTS: AltVerdict[] = ["needs_alt", "needs_better", "not_checked", "good"];

function isGroup(value: string | null): value is ImageGroup {
  return GROUPS.includes(value as ImageGroup);
}

function isVerdict(value: string | null): value is AltVerdict {
  return VERDICTS.includes(value as AltVerdict);
}

function plural(n: number, one: string, many: string): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

export default function ImagesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const { aiOffNotice } = usePreferences();
  const tableCard = useRef<HTMLDivElement>(null);
  // This list as it stands, for the image page's way back.
  const here = `${location.pathname}${location.search}`;
  const scanQuery = useScanQuery(id);
  const queryClient = useQueryClient();

  const groupParam = params.get("group");
  const verdictParam = params.get("verdict");
  const group: ImageGroup = isGroup(groupParam) ? groupParam : "with_text";
  const verdict: AltVerdict | "" = isVerdict(verdictParam) ? verdictParam : "";
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? 1) || 1);
  const filter: ReportImagesFilter = {
    group,
    verdict,
    q,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  };

  const imagesQuery = useQuery({
    queryKey: ["report-images", id, filter],
    queryFn: () => api.listReportImages(id, filter),
    enabled: Number.isSafeInteger(id) && id > 0,
    placeholderData: keepPreviousData,
  });
  const data = imagesQuery.data;

  // Which image the model is checking, the words the live region says, and
  // per-image errors. One check at a time: the local model takes one image
  // at a time anyway (Ollama's concurrency is 1 by default).
  const [announcement, setAnnouncement] = useState("");
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [focusId, setFocusId] = useState<number | null>(null);
  const check = useMutation({
    mutationFn: (image: ReportImage) => api.checkImageAlt(id, image.image_id),
    onMutate: (image) => {
      setErrors((current) => {
        const next = { ...current };
        delete next[image.image_id];
        return next;
      });
      setAnnouncement(`Asking the local AI model about ${imageName(image)}. This can take a minute.`);
    },
    onSuccess: (row, image) => {
      setAnnouncement(
        `Done: ${imageName(image)}. ${ALT_VERDICT_LABEL[row.verdict]}. Suggested alt text: ${row.suggestion ?? "none"}.`,
      );
      setFocusId(image.image_id);
      void queryClient.invalidateQueries({ queryKey: ["report-images", id] });
    },
    onError: (error, image) => {
      const message =
        error instanceof ApiError || error instanceof Error
          ? error.message
          : "The check did not finish. Try again later.";
      setErrors((current) => ({ ...current, [image.image_id]: message }));
      setAnnouncement(`The check of ${imageName(image)} did not finish. ${message}`);
    },
  });

  const update = (changes: Record<string, string>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  };

  const filters: FilterGroup[] = [
    {
      key: "verdict",
      label: "Alt text verdict",
      value: verdict,
      options: [
        { value: "", label: "All", count: data?.counts[group].total ?? 0 },
        ...VERDICTS.map((value) => ({ value, label: ALT_VERDICT_LABEL[value], count: data?.counts[group][value] ?? 0 })),
      ],
    },
  ];
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const scan = scanQuery.data;
  // Every image is in exactly one of these two groups, so their counts add
  // up to the whole report.
  const totals: ImageGroupCounts | null = data
    ? {
        total: data.counts.missing_alt.total + data.counts.with_alt.total,
        needs_alt: data.counts.missing_alt.needs_alt + data.counts.with_alt.needs_alt,
        needs_better: data.counts.missing_alt.needs_better + data.counts.with_alt.needs_better,
        not_checked: data.counts.missing_alt.not_checked + data.counts.with_alt.not_checked,
        good: data.counts.missing_alt.good + data.counts.with_alt.good,
      }
    : null;

  return (
    <>
      <ReportHeader
        tabs
        scanId={id}
        previousScanId={scan?.previous_scan_id ?? null}
        title="Images"
        // The ZIP: the pictures in folders by group, then by verdict, and a
        // sheet listing them all (src/audit/exports/images_zip.py). In the
        // header's action slot, top right, where Issues keeps Export report,
        // so a report's downloads are in one place (SC 3.2.3 Consistent
        // Navigation, Level AA). Fetched and saved like Export report, not a
        // plain link: a plain link did nothing in some windows (2026-11-13).
        // Only a completed report offers it; the server refuses the rest.
        actions={scan?.status === "completed" ? <ZipDownload scanId={id} /> : undefined}
        // What the tab shows, behind the "?" after the heading (the
        // developer's request, 2026-11-16). These two paragraphs were on
        // screen under the heading until then. Lines kept to the shared
        // measure inside the panel (SC 1.4.8 Visual Presentation, Level AAA).
        //
        // The tradeoff, told to the developer before building it, who chose
        // to move all of it: "No verdict proves that the site meets
        // accessibility standards" is no longer on screen until someone
        // opens the "?", although AGENTS.md keeps that caveat in view
        // (Interface language rule 4). Each verdict cell still names its
        // source in words (page code, text match, local AI model), so a
        // model's view is never shown as a measured fact.
        help={
          <HelpTip
            question="What does the Images tab show"
            // The icon at the start of its 44px target, not its middle, so it
            // sits about 8px after the heading rather than 15px (the
            // developer's request, 2026-11-16). The target keeps its full
            // size (SC 2.5.5 Target Size (Enhanced), Level AAA) and reaches
            // right, into empty space.
            className="justify-start pl-1"
          >
            <div className="max-w-measure space-y-2">
              <p>
                Every image this scan found, grouped by what to check. Alt text is the text a
                screen reader reads for an image. One image can be in two groups: &ldquo;Images
                with text&rdquo; and one of the other two.
              </p>
              <p>
                Each verdict is a lead for a person to confirm. No verdict proves that the site
                meets accessibility standards.
              </p>
            </div>
          </HelpTip>
        }
      />

      {/* The report's numbers for its images, in the Issues tab's style
          (SummaryStat; the developer's request, 2026-11-16), replacing the
          "1,076 images" meta line under the heading: all the images, then
          one number per verdict, worst first, in the order the verdict
          filter and the line under the groups use (SC 3.2.4 Consistent
          Identification, Level AA).

          "Need a person to check" is shown too, though the request listed only
          found, need alt text, need better alt text and good: without it the
          verdicts add up to far fewer than the images found, and the rest
          read as fine (AGENTS.md, Interface language rule 4: never drop a
          limitation). It is left out only at zero, like every verdict.

          Whole-report counts: every image is in exactly one of "without alt
          text" and "with alt text", so the two groups' counts add up to the
          report without counting an image twice. They do not change with the
          group, filter or search, like the group buttons' numbers.

          The grid is the Issues strip's spacing: two across below 640px so
          nothing is squeezed at 320px (SC 1.4.10 Reflow, Level AA), then as
          many as there are numbers. */}
      {totals && (
        <dl className="mt-10 mb-8 grid grid-cols-2 gap-x-8 gap-y-8 sm:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] lg:gap-x-12">
          <SummaryStat label={totals.total === 1 ? "Image found" : "Images found"} value={totals.total} />
          {VERDICTS.filter((key) => totals[key] > 0).map((key) => (
            <SummaryStat
              key={key}
              label={totals[key] === 1 ? ALT_VERDICT_LABEL[key] : ALT_VERDICT_COUNT_LABEL[key]}
              value={totals[key]}
            />
          ))}
        </dl>
      )}

      <Tabs
        mode="filter"
        className="mb-4"
        label="Image groups"
        controls="report-images-table"
        value={group}
        onChange={(key) => update({ group: key, verdict: "" })}
        items={GROUPS.map((key) => ({
          key,
          label: (
            <>
              {IMAGE_GROUP_LABEL[key]}
              <span className="ml-1.5 tabular-nums">
                {data ? data.counts[key].total.toLocaleString() : ""}
              </span>
            </>
          ),
        }))}
      />

      {/* The line that split the chosen group by verdict ("Images with text:
          41 need alt text, …") was removed (the developer's request,
          2026-11-16): the numbers above say it for the whole report, and the
          split for the chosen group is on the verdict filter's choices, as
          counts, the way the Issues Filter menu counts its choices. */}

      {imagesQuery.error && (
        <Card className="mb-4 border-sev-critical/30 bg-sev-critical-bg p-4 text-sm text-sev-critical">
          The images could not be loaded. {imagesQuery.error instanceof Error ? imagesQuery.error.message : ""}
        </Card>
      )}

      {/* One polite live region for the model's progress and answers, kept
          mounted so its first message is read out (a region added with its
          words already in it is not). */}
      <p id="report-images-announcer" role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>

      {/* Focusable from script only (tabIndex -1), for "Don't show again":
          the button goes, and focus lands on the table it was above. */}
      <Card id="report-images-table" ref={tableCard} tabIndex={-1} className="focus:outline-none">
        {/* PagedTable draws the pager over the table and again under its last
            row, as on every paged table (components/TablePagination.tsx). The
            search and filter bar is drawn whether or not there is a pager, so
            a filter that emptied the table stays there to undo. */}
        <PagedTable
          pagination={
            data && {
              label: IMAGE_GROUP_LABEL[group],
              noun: "images",
              page,
              pages,
              total: data.total,
              pageSize: PAGE_SIZE,
              pagerId: PAGER_ID,
              disabled: imagesQuery.isFetching,
              setPage: (next: number) => update({ page: String(next) }, false),
            }
          }
          top={(pager) => (
            <TableBar
              pager={pager}
              footer={<ActiveFilters items={activeFilterItems(filters)} onClear={() => update({ verdict: "" })} />}
            >
              <TableSearch
                label="Search images"
                placeholder="Alt text, text in the image, or page address"
                value={q}
                onChange={(value) => update({ q: value })}
              />
              <FilterMenu
                label="Filter images"
                groups={filters}
                onChange={(key, value) => update({ [key]: value })}
                onReset={() => update({ verdict: "" })}
              />
            </TableBar>
          )}
        >
        {/* The order, and the count only when no pager shows it. The pager's
            "Showing 1–25 of 98 images" says the count, so repeating it here
            was one fact twice (the developer's catch, 2026-11-16). But the
            pager is drawn only when there is more than one page, so with 25
            or fewer images (a search, a small report) this line is the only
            place that says, and announces, how many match (SC 4.1.3 Status
            Messages, Level AA). It stays mounted, as a live region must. */}
        <TableStatus>
          {data
            ? pages > 1
              ? "The ones that need alt text come first."
              : `${plural(data.total, "image", "images")}. The ones that need alt text come first.`
            : "Loading images…"}
        </TableStatus>
        {data && !data.check_available && aiOffNotice === "on" && (
          // The line under the note spans the table; only the text is held to
          // a reading width (SC 1.4.8 Visual Presentation, Level AAA), so the
          // line is not cut short where the text ends. Hidden by "Don't show
          // again", the line goes; each row still says the check is off.
          <div className="border-b border-border px-4 py-2">
            <AltCheckOff onHidden={() => tableCard.current?.focus()} />
          </div>
        )}
        {data && data.rows.length === 0 ? (
          <TableEmpty>No images match. Clear the filter or shorten your search.</TableEmpty>
        ) : (
          <TableRegion label={IMAGE_GROUP_LABEL[group]} busy={imagesQuery.isFetching}>
            <Table caption={`${IMAGE_GROUP_LABEL[group]}, with a verdict on each image's alt text`} className="min-w-[60rem]">
              <TableHead>
                <tr>
                  <ColumnHeader className="w-44">Image</ColumnHeader>
                  <ColumnHeader>Text in the image</ColumnHeader>
                  <ColumnHeader>Current alt text</ColumnHeader>
                  <ColumnHeader className="w-52">Alt text verdict</ColumnHeader>
                  <ColumnHeader className="w-72">Suggested alt text</ColumnHeader>
                  <ColumnHeader numeric className="w-28">
                    {IMAGE_PAGES_COLUMN}
                  </ColumnHeader>
                </tr>
              </TableHead>
              <tbody>
                {(data?.rows ?? []).map((image, index) => (
                  <ImageRow
                    key={image.image_id}
                    index={index}
                    scanId={id}
                    image={image}
                    checkAvailable={Boolean(data?.check_available)}
                    pending={check.isPending && check.variables?.image_id === image.image_id}
                    busy={check.isPending}
                    error={errors[image.image_id]}
                    focus={focusId === image.image_id}
                    onFocused={() => setFocusId(null)}
                    onCheck={() => check.mutate(image)}
                    backTo={here}
                  />
                ))}
              </tbody>
            </Table>
          </TableRegion>
        )}
        </PagedTable>
      </Card>
    </>
  );
}

/**
 * The ZIP download button, with what it is doing in words: "Preparing…"
 * while the server builds it (a large report takes a few seconds), then the
 * file name and size, or what went wrong. The words are in a polite live
 * region beside the button (SC 4.1.3 Status Messages, Level AA). The button
 * stays enabled and focusable while it works (aria-disabled), so focus is
 * not lost (SC 2.4.3).
 */
function ZipDownload({ scanId }: { scanId: number }) {
  const [state, setState] = useState<{ busy: boolean; message: string; error: boolean }>({
    busy: false,
    message: "",
    error: false,
  });
  const start = async () => {
    if (state.busy) return;
    setState({ busy: true, message: "Preparing the ZIP. A large report takes a few seconds.", error: false });
    try {
      const { filename, sizeBytes } = await api.downloadImagesZip(scanId);
      const mb = (sizeBytes / 1_000_000).toFixed(1);
      setState({ busy: false, message: `Saved ${filename} (${mb} MB) to your downloads.`, error: false });
    } catch (error) {
      const text = error instanceof Error ? error.message : "Try again later.";
      setState({ busy: false, message: `The ZIP could not be downloaded. ${text}`, error: true });
    }
  };
  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={() => void start()} aria-disabled={state.busy || undefined}>
        <Download className="h-4 w-4" aria-hidden />
        {state.busy ? "Preparing images and sheet (ZIP)…" : "Download images and sheet (ZIP)"}
      </Button>
      <p
        role="status"
        aria-live="polite"
        className={cn("max-w-xs text-right text-xs", state.error ? "text-sev-critical" : "text-fg-muted")}
      >
        {state.message}
      </p>
    </div>
  );
}

function ImageRow({
  index,
  scanId,
  image,
  checkAvailable,
  pending,
  busy,
  error,
  focus,
  onFocused,
  onCheck,
  backTo,
}: {
  index: number;
  scanId: number;
  image: ReportImage;
  checkAvailable: boolean;
  pending: boolean;
  busy: boolean;
  error?: string;
  focus: boolean;
  onFocused: () => void;
  onCheck: () => void;
  /** This list, with its group, filter, search and page, for the image page's way back. */
  backTo: string;
}) {
  const name = imageName(image);
  const answerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focus && image.suggestion && answerRef.current) {
      answerRef.current.focus();
      onFocused();
    }
  }, [focus, image.suggestion, onFocused]);

  // "Check" when there is alt text the text match could not judge; else
  // "Suggest". Both send the image to the model and get a suggestion back.
  const action =
    image.verdict === "not_checked" && image.alt_text ? "Check alt text" : "Suggest alt text";

  return (
    <Row index={index} className="align-top">
      <RowHeader className="align-top">
        {/* The thumbnail and the name are one link to the image's own page
            (the developer's request, 2026-11-16, following the Documents
            tab, where a file's name opens its page): one link per image,
            not two that go to the same place (W3C COGA, "Making Content
            Usable": one way to do one thing). The picture is decorative
            (alt=""), so the link's name is the file name, with "full
            details" for a screen reader (WCAG technique C7; SC 2.4.9 Link
            Purpose (Link Only), Level AAA), as the Documents tab says it.
            It opened the image viewer until then; the viewer is on the
            image's page now. At least 44px tall (SC 2.5.5). */}
        <Link
          to={withReturnTrail(imagePath(scanId, image.image_id), IMAGES_VIEW, backTo)}
          className="group flex min-h-target flex-col items-start gap-1 rounded-xs text-umich-blue focus-visible:outline-none focus-visible:shadow-focus"
        >
          <ImageThumb image={image} />
          <span className="break-all text-xs font-semibold underline underline-offset-2 group-hover:text-umich-blue-600">
            {name}
          </span>
          <span className="sr-only">, full details</span>
        </Link>
      </RowHeader>
      <Cell className="align-top text-sm">
        {image.image_text ? (
          <span className="block break-words">{image.image_text}</span>
        ) : (
          <span className="text-fg-subtle">None found</span>
        )}
      </Cell>
      <Cell className="align-top">
        <CurrentAlt image={image} />
      </Cell>
      <Cell className="align-top">
        <VerdictSummary image={image} />
      </Cell>
      <Cell className="align-top">
        {image.suggestion ? (
          // Focus lands here when the model answers (see the route comment).
          <div ref={answerRef} tabIndex={-1} className="rounded-xs focus:outline-none focus-visible:shadow-focus">
            <SuggestionBox text={image.suggestion} name={name} />
          </div>
        ) : !checkAvailable ? (
          <span className="text-xs text-fg-subtle">Local AI check is off</span>
        ) : !image.can_check ? (
          <span className="text-xs text-fg-subtle">
            Check by hand: the model cannot look at an image drawn in the page code (SVG).
          </span>
        ) : (
          <>
            {/* aria-disabled, not disabled, while a check runs: a disabled
                button drops keyboard focus to the page, and the person who
                pressed it would lose their place (SC 2.4.3). */}
            <Button
              size="md"
              onClick={() => {
                if (!busy) onCheck();
              }}
              aria-disabled={busy || undefined}
              aria-describedby={error ? `alt-check-error-${image.image_id}` : undefined}>
              {pending ? "Checking…" : action}
              <span className="sr-only"> for {name}</span>
            </Button>
            {error && (
              <p id={`alt-check-error-${image.image_id}`} className="mt-2 text-xs text-sev-critical">
                {error}
              </p>
            )}
          </>
        )}
      </Cell>
      {/* How many pages, as a plain number: the pages are listed on the
          image's page. It was "Where it appears", the first page as a link
          and "and on 5 other pages" as text, which named one page and hid
          the rest (the developer's report, 2026-11-16). The Documents tab's
          "Pages it appears on" is the same number in the same words, and
          Issues' "Affected pages" is too (SC 3.2.4 Consistent
          Identification, Level AA). The last column, as on the Documents
          tab (the developer's request, 2026-11-16). */}
      <Cell numeric className="align-top">
        {image.page_count.toLocaleString()}
      </Cell>
    </Row>
  );
}
