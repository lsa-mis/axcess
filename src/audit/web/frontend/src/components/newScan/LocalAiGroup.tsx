import { GROUPS, SWITCHES } from "./copy";
import type { GroupProps } from "./groupProps";
import { isFixed, switchOn, switchPatch, type ScanSettings, type SwitchKey } from "./scanPolicy";
import SettingsGroup from "./SettingsGroup";
import SwitchRow from "./SwitchRow";

/** How many local-AI switches are on, for the disclosure header. */
export function localAiCount(settings: ScanSettings, policy: GroupProps["policy"]) {
  const keys: SwitchKey[] = ["ocr", "vision", "semantic", "motion"];
  const shown = keys.filter(
    (key) =>
      !(key === "semantic" && isFixed(policy, "skip_semantic")) &&
      !(key === "motion" && isFixed(policy, "skip_visual")),
  );
  return { on: shown.filter((key) => switchOn(settings, key)).length, total: shown.length };
}

function formatBytes(value: number | null): string {
  if (!value || value < 1) return "size unavailable";
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`;
  return `${Math.round(value / 1024 ** 2)} MB`;
}

/**
 * The reviews that run on models already installed on this computer.
 *
 * Each switch says why it is unavailable instead of going quietly grey:
 * "not installed" and "turn on OCR first" are the two reasons, and both
 * are things the reviewer can act on.
 */
export default function LocalAiGroup({ settings, update, policy, capabilities }: GroupProps) {
  const local = capabilities.local;
  const ocrOff = local?.ocr.available === false;
  const visionOff = local?.vision.available === false;
  const semanticOff = local?.semantic.available === false;
  const ocrOn = switchOn(settings, "ocr");

  return (
    <SettingsGroup id="local-ai" legend={GROUPS.localAi.legend} description={GROUPS.localAi.description}>
      <div className="-mx-2 grid gap-x-4 sm:grid-cols-2">
        <SwitchRow
          checked={ocrOn}
          onChange={(on) => update(switchPatch(settings, "ocr", on))}
          disabled={ocrOff}
          label={SWITCHES.ocr.label}
          hint={
            ocrOff
              ? "Tesseract OCR is not available in this installation."
              : `${SWITCHES.ocr.hint} Up to ${local?.ocr.max_workers ?? 2} workers.`
          }
        />
        <SwitchRow
          checked={switchOn(settings, "vision")}
          onChange={(on) => update(switchPatch(settings, "vision", on))}
          disabled={!ocrOn || visionOff}
          label={SWITCHES.vision.label}
          hint={
            !ocrOn
              ? "Turn on image text reading first; the vision model only reviews images where OCR found text."
              : local?.vision.available
                ? `${SWITCHES.vision.hint} ${local.vision.model} is installed (${formatBytes(local.vision.installed_size_bytes)}).`
                : (local?.vision.reason ?? "Checking whether the local vision model is ready…")
          }
        />
        {!isFixed(policy, "skip_semantic") && (
          <SwitchRow
            checked={switchOn(settings, "semantic")}
            onChange={(on) => update(switchPatch(settings, "semantic", on))}
            disabled={semanticOff}
            label={SWITCHES.semantic.label}
            hint={
              local?.semantic.available
                ? `${SWITCHES.semantic.hint} Up to ${local.semantic.checks_per_page} checks per page.`
                : (local?.semantic.reason ?? "Checking whether the local text models are ready…")
            }
          />
        )}
        {!isFixed(policy, "skip_visual") && (
          <SwitchRow
            checked={switchOn(settings, "motion")}
            onChange={(on) => update(switchPatch(settings, "motion", on))}
            label={SWITCHES.motion.label}
            hint={
              local?.vision.available
                ? `${SWITCHES.motion.hint} Adds one vision-model review per page.`
                : `${SWITCHES.motion.hint} The vision review joins once the local model is installed.`
            }
          />
        )}
      </div>
    </SettingsGroup>
  );
}
