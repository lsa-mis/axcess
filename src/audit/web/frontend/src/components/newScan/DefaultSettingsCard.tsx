import { Check, X } from "lucide-react";
import { Button, Card } from "../ui";
import { DEFAULTS_CARD } from "./copy";
import { isDefault, isFixed, switchOn, type ScanPolicy, type ScanSettings } from "./scanPolicy";

export function engineName(engine: ScanSettings["scan_engine"]): string {
  return engine === "both" ? "axe-core + Alfa" : engine === "alfa" ? "Siteimprove Alfa" : "axe-core";
}

/** The lines the default card shows, with whether each still applies. */
export function includedLines(settings: ScanSettings, policy: ScanPolicy): Array<{ text: string; on: boolean }> {
  const login = policy.mode === "login";
  const lines: Array<{ text: string; on: boolean }> = [
    { text: `Checks against WCAG 2.2 ${settings.axe_level} with ${engineName(settings.scan_engine)}`, on: true },
    { text: "Keyboard traps", on: switchOn(settings, "keyboard") },
  ];
  if (!isFixed(policy, "skip_focus")) lines.push({ text: "Focus visibility", on: switchOn(settings, "focus") });
  lines.push(
    { text: "Responsive layout and zoom", on: switchOn(settings, "responsive") },
    { text: "Clicks through menus and dialogs", on: switchOn(settings, "click_through") },
  );
  // A line is listed when the default profile includes it, or when it has
  // been turned on: a login scan starts without image reading, and a struck
  // line on an untouched card would claim a change nobody made.
  if (!policy.defaults.skip_ocr || switchOn(settings, "ocr")) {
    lines.push({ text: "Reads text inside images", on: switchOn(settings, "ocr") });
  }
  lines.push(
    {
      text: `Up to ${settings.max_pages.toLocaleString()} pages, ${settings.max_depth} clicks deep`,
      on: true,
    },
    login
      ? { text: "Stays on this website, 1 request per second", on: settings.rps <= 1 }
      : { text: "Respects robots.txt", on: !settings.ignore_robots },
  );
  lines.push({
    text: "Stores rendered pages for the Page inspector",
    on: !settings.skip_rendered_storage && !settings.static_only,
  });
  if (settings.static_only) lines.push({ text: "Renders every page in a real browser", on: false });
  return lines;
}

/**
 * What runs by default, in a list a first-time user can read in one pass.
 *
 * It replaces a closed disclosure whose contents the user had to open to
 * discover. It is also live: change anything under Advanced settings and
 * the badge flips to "Customized", the lines that no longer hold are struck
 * through with an ✕ and a spoken ", turned off", and a reset appears. The
 * strike-through is reinforcement; the icon and the suffix carry it.
 */
export default function DefaultSettingsCard({
  settings,
  policy,
  onReset,
}: {
  settings: ScanSettings;
  policy: ScanPolicy;
  onReset: () => void;
}) {
  const unchanged = isDefault(settings, policy);
  const lines = includedLines(settings, policy);
  return (
    <Card
      className="border-l-4 border-l-umich-blue p-5"
      aria-labelledby="default-settings-title"
      role="region"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="default-settings-title" className="flex flex-wrap items-center gap-2 text-base font-semibold text-fg">
            {DEFAULTS_CARD.title}
            <span
              className={
                unchanged
                  ? "inline-flex min-h-6 items-center rounded-full bg-umich-blue px-2.5 text-xs font-semibold text-fg-inverse"
                  : "inline-flex min-h-6 items-center rounded-full bg-sev-major-bg px-2.5 text-xs font-semibold text-sev-major"
              }
            >
              {unchanged ? DEFAULTS_CARD.selected : DEFAULTS_CARD.customized}
            </span>
          </h2>
          <p className="mt-1 text-sm text-fg-muted" role="status">
            {unchanged ? DEFAULTS_CARD.leadDefault : DEFAULTS_CARD.leadCustom}
          </p>
        </div>
        {!unchanged && (
          <Button type="button" onClick={onReset}>
            {DEFAULTS_CARD.reset}
          </Button>
        )}
      </div>
      <ul className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {lines.map((line) => (
          <li
            key={line.text}
            className={
              line.on
                ? "flex min-h-7 items-start gap-2 text-fg transition-colors duration-200 motion-reduce:transition-none"
                : "flex min-h-7 items-start gap-2 text-fg-subtle transition-colors duration-200 motion-reduce:transition-none"
            }
          >
            {line.on ? (
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-umich-blue" aria-hidden />
            ) : (
              <X className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            )}
            <span className={line.on ? undefined : "line-through decoration-border-strong"}>{line.text}</span>
            {!line.on && <span className="sr-only">, turned off</span>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
