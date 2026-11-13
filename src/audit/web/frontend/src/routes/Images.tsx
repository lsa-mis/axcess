import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router";
import { X } from "lucide-react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, blobUrl, ApiError } from "../api/client";
import ReportHeader, { ReportMeta } from "../components/ReportHeader";
import Tabs from "../components/Tabs";
import { TablePagination } from "../components/TablePagination";
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
import { AltTag, Button, Card, PageLink } from "../components/ui";
import { useModalDialog } from "../hooks/useModalDialog";
import { useScanQuery } from "../hooks/useScanQuery";
import { cn } from "../lib/cn";
import { ALT_VERDICT_LABEL, ALT_VERDICT_SOURCE_LABEL, IMAGE_GROUP_LABEL } from "../lib/terms";
import type { AltVerdict, ImageGroup, ReportImage, ReportImagesFilter } from "../api/types";

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
 * two ("Images with text" and one of the other two); the page says so
 * under the group row. They are the shared `Tabs` in filter mode
 * (aria-pressed toggle buttons over one table), not three tables and not
 * links: the choice narrows this table in place. The Claude Design draft
 * (2026-11-13) drew them as large cards with the verdict split in each;
 * the shared chips were kept instead, one control for one kind of choice
 * across the app (SC 3.2.4 Consistent Identification, Level AA; W3C COGA
 * "Making Content Usable", https://www.w3.org/TR/coga-usable/), and the
 * split moved to the line under the row.
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

/** Verdict chip colours. The words carry the meaning; colour only repeats it. */
const VERDICT_CHIP: Record<AltVerdict, string> = {
  needs_alt: "border-sev-critical/40 bg-sev-critical-bg text-sev-critical",
  needs_better: "border-sev-major/40 bg-sev-major-bg text-sev-major",
  not_checked: "border-dashed border-border-strong bg-surface-muted text-fg-muted",
  good: "border-ok/40 bg-ok-bg text-ok",
};

function isGroup(value: string | null): value is ImageGroup {
  return GROUPS.includes(value as ImageGroup);
}

function isVerdict(value: string | null): value is AltVerdict {
  return VERDICTS.includes(value as AltVerdict);
}

/** The image's file name, the row's name: "banner.png". */
export function imageName(image: ReportImage): string {
  try {
    const path = new URL(image.image_url).pathname;
    const last = decodeURIComponent(path.split("/").filter(Boolean).pop() ?? "");
    if (last) return last.length > 60 ? `${last.slice(0, 57)}…` : last;
  } catch {
    // An inline SVG has no address of its own; fall through.
  }
  return image.has_svg_text ? "Inline SVG" : "Image";
}

function plural(n: number, one: string, many: string): string {
  return `${n.toLocaleString()} ${n === 1 ? one : many}`;
}

export default function ImagesRoute() {
  const { scanId } = useParams<{ scanId: string }>();
  const id = Number(scanId);
  const [params, setParams] = useSearchParams();
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
  const [viewing, setViewing] = useState<ReportImage | null>(null);
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
        { value: "", label: "All" },
        ...VERDICTS.map((value) => ({ value, label: ALT_VERDICT_LABEL[value] })),
      ],
    },
  ];
  const counts = data?.counts[group];
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const scan = scanQuery.data;
  // Every image is in exactly one of these two groups.
  const allImages = data ? data.counts.missing_alt.total + data.counts.with_alt.total : null;

  return (
    <>
      <ReportHeader
        tabs
        scanId={id}
        previousScanId={scan?.previous_scan_id ?? null}
        title="Images"
        meta={
          <ReportMeta
            counts={allImages == null ? "Loading images…" : plural(allImages, "image", "images")}
            note=""
          />
        }
      />

      {/* Lines kept to the shared measure (max-w-measure, 35em) (SC 1.4.8 Visual Presentation,
          Level AAA: 80 or fewer). The caveat sits here, not on the meta line,
          where it ran past 80. */}
      <div className="mb-3 max-w-measure space-y-2 text-sm leading-6 text-fg-muted">
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

      <Tabs
        mode="filter"
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

      {counts && (
        <p className="mb-4 mt-3 text-sm text-fg-muted">
          <span className="font-semibold text-fg">{IMAGE_GROUP_LABEL[group]}:</span>{" "}
          {[
            counts.needs_alt && `${counts.needs_alt.toLocaleString()} need alt text`,
            counts.needs_better && `${counts.needs_better.toLocaleString()} need better alt text`,
            counts.not_checked && `${counts.not_checked.toLocaleString()} not checked yet`,
            counts.good && `${counts.good.toLocaleString()} good`,
          ]
            .filter(Boolean)
            .join(", ") || "none"}
          .
        </p>
      )}

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

      <Card id="report-images-table">
        <TableBar
          pager={
            data && (
              <TablePagination
                label={IMAGE_GROUP_LABEL[group]}
                noun="images"
                page={page}
                pages={pages}
                total={data.total}
                pageSize={PAGE_SIZE}
                pagerId={PAGER_ID}
                disabled={imagesQuery.isFetching}
                setPage={(next) => update({ page: String(next) }, false)}
              />
            )
          }
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
        <TableStatus>
          {data
            ? `${plural(data.total, "image", "images")}, the ones that need alt text first.`
            : "Loading images…"}
        </TableStatus>
        {data && !data.check_available && (
          <p className="max-w-measure border-b border-border px-4 py-2 text-sm text-fg-muted">
            The local AI check is off, so no alt text can be suggested here. The person who runs
            Axcess can turn it on by choosing a local model.
          </p>
        )}
        {data && data.rows.length === 0 ? (
          <TableEmpty>No images match. Clear the filter or shorten your search.</TableEmpty>
        ) : (
          <TableRegion label={IMAGE_GROUP_LABEL[group]} busy={imagesQuery.isFetching}>
            <Table caption={`${IMAGE_GROUP_LABEL[group]}, with a verdict on each image's alt text`} className="min-w-[60rem]">
              <TableHead>
                <tr>
                  <ColumnHeader className="w-44 text-left">Image</ColumnHeader>
                  <ColumnHeader className="text-left">Text in the image</ColumnHeader>
                  <ColumnHeader className="text-left">Where it appears</ColumnHeader>
                  <ColumnHeader className="text-left">Current alt text</ColumnHeader>
                  <ColumnHeader className="w-52 text-left">Alt text verdict</ColumnHeader>
                  <ColumnHeader className="w-72 text-left">Suggested alt text</ColumnHeader>
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
                    onView={() => setViewing(image)}
                  />
                ))}
              </tbody>
            </Table>
          </TableRegion>
        )}
      </Card>
      <ImageViewer image={viewing} onClose={() => setViewing(null)} />
    </>
  );
}

/**
 * The image at full size, in a native modal ``<dialog>`` (useModalDialog), the
 * same pattern as the issue guidance dialog: the browser traps focus inside,
 * Escape closes it, and focus goes back to the thumbnail that opened it (WAI-ARIA
 * APG, Dialog (Modal) pattern, https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/).
 * A click on the dimmed area around it also closes it, as people expect of an
 * image viewer; the close button is the way that works for everyone.
 *
 * The close button says "Close image viewer" in visible words, not an X with
 * an aria-label (the repo's control-text rule). The picture itself has
 * alt="": the dialog's heading names it, and its current alt text and the
 * text read from it are written out below, so a screen reader user gets the
 * same facts without the picture claiming one of them as its description.
 */
function ImageViewer({ image, onClose }: { image: ReportImage | null; onClose: () => void }) {
  const ref = useModalDialog(image != null);
  const name = image ? imageName(image) : "";
  return (
    // The click handler only catches clicks on the dimmed backdrop, a mouse
    // extra. Keyboard users close the dialog with Escape (native to a modal
    // <dialog>) or the close button, so no key listener is needed here.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- Keep: backdrop click; Escape and the close button cover keyboard
    <dialog
      ref={ref}
      aria-labelledby="image-viewer-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className="max-h-[92vh] w-[min(94vw,60rem)] overflow-y-auto rounded-xs border border-border bg-surface-raised p-0 text-fg shadow-raised backdrop:bg-black/60"
    >
      {image && (
        <>
          <div className="sticky top-0 z-[1] flex flex-wrap items-start justify-between gap-3 border-b border-border bg-surface px-5 py-3">
            <h2 id="image-viewer-title" className="min-w-0 break-all text-lg font-semibold">
              {name}
            </h2>
            <Button type="button" variant="secondary" onClick={onClose}>
              <X className="h-4 w-4" aria-hidden />
              Close image viewer
            </Button>
          </div>
          <div className="px-5 py-4">
            <img
              src={blobUrl(image.content_hash)}
              alt=""
              className="mx-auto max-h-[65vh] max-w-full rounded-xs border border-border bg-white object-contain"
            />
            <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_minmax(0,1fr)]">
              <dt className="font-semibold text-fg-muted">Current alt text</dt>
              <dd className="min-w-0">
                <AltTag value={image.alt_text} wrap />
              </dd>
              <dt className="font-semibold text-fg-muted">Text in the image</dt>
              <dd className="min-w-0 break-words">{image.image_text ?? "None found"}</dd>
              <dt className="font-semibold text-fg-muted">Alt text verdict</dt>
              <dd>
                {ALT_VERDICT_LABEL[image.verdict]}. {image.verdict_reason}
              </dd>
            </dl>
          </div>
        </>
      )}
    </dialog>
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
  onView,
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
  onView: () => void;
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
  const otherPages = image.page_count - 1;

  return (
    <Row index={index} className="align-top">
      <RowHeader className="align-top">
        {image.has_svg_text || !image.content_hash ? (
          <span className="flex h-12 w-[72px] items-center justify-center rounded-xs border border-border bg-surface-muted font-mono text-2xs font-semibold text-fg-muted">
            SVG
          </span>
        ) : (
          // The thumbnail is the button that opens the image viewer (the
          // developer's request, 2026-11-13): a 72 by 48 picture is too small
          // to judge alt text against. The picture is decorative (alt=""); the
          // button's words, partly screen-reader-only (WCAG technique C7),
          // say what it does and which image. A 44 px tall target (SC 2.5.5).
          <Button
            variant="ghost"
            onClick={onView}
            className="min-h-target p-0.5"
          >
            <img
              src={blobUrl(image.content_hash)}
              alt=""
              loading="lazy"
              decoding="async"
              width={72}
              height={48}
              className="h-12 w-[72px] rounded-xs border border-border bg-white object-contain"
            />
            <span className="sr-only">View larger image: {name}</span>
          </Button>
        )}
        <span className="mt-1 block break-all text-xs font-semibold">{name}</span>
      </RowHeader>
      <Cell className="align-top text-sm">
        {image.image_text ? (
          <span className="block break-words">{image.image_text}</span>
        ) : (
          <span className="text-fg-subtle">None found</span>
        )}
      </Cell>
      <Cell className="align-top">
        {image.sample_page_id != null && image.sample_page_url ? (
          <>
            <PageLink
              scanId={scanId}
              pageId={image.sample_page_id}
              pageUrl={image.sample_page_url}
              showUrlBelow={false}
              actions={false}
              origin="Images"
            />
            {otherPages > 0 && (
              <span className="block text-xs text-fg-muted">
                and on {plural(otherPages, "other page", "other pages")}
              </span>
            )}
          </>
        ) : (
          <span className="text-fg-subtle">Does not apply</span>
        )}
      </Cell>
      <Cell className="align-top">
        <AltTag value={image.alt_text} wrap />
        {image.alt_text_variants > 1 && (
          <span className="mt-1 block text-xs text-fg-muted">
            Differs between pages: this is the worst one.
          </span>
        )}
      </Cell>
      <Cell className="align-top">
        <span
          className={cn(
            "inline-flex items-center rounded-xs border px-2 py-0.5 text-xs font-semibold",
            VERDICT_CHIP[image.verdict],
          )}
        >
          {ALT_VERDICT_LABEL[image.verdict]}
        </span>
        <span className="mt-1 block text-xs text-fg-muted">{image.verdict_reason}</span>
        {image.verdict_source && (
          <span className="mt-0.5 block text-xs text-fg-subtle">
            {ALT_VERDICT_SOURCE_LABEL[image.verdict_source]}
          </span>
        )}
      </Cell>
      <Cell className="align-top">
        {image.suggestion ? (
          // Focus lands here when the model answers (see the route comment).
          <div ref={answerRef} tabIndex={-1} className="rounded-xs focus:outline-none focus-visible:shadow-focus">
            <span className="block break-words text-sm text-fg">{image.suggestion}</span>
            <span className="mt-1 block text-xs text-fg-muted">
              Written by the local AI model. Check it before you use it.
            </span>
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
    </Row>
  );
}
