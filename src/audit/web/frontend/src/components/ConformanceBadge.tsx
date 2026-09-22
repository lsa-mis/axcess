import type { ConformanceLabel } from "../api/types";

/**
 * WCAG conformance badge (A/AA/AAA/BP), shared by the list, detail, and evidence.
 *
 * Every background here carries white bold 13px text, which is not "large
 * text" under WCAG, so it needs 7:1 for SC 1.4.6 (Contrast Enhanced), not
 * 4.5:1. Two of these used to sit just under that line — A at 6.97:1 and,
 * with no small irony, AAA at 6.10:1 — which reads fine and still fails the
 * criterion this tool reports on. Measured against white: A 7.71, AA 11.40,
 * AAA 7.79, BP 8.86.
 */
export default function ConformanceBadge({ level }: { level: ConformanceLabel }) {
  const bg = {
    A: "bg-[#a40059]",
    AA: "bg-[#4b1d8a]",
    AAA: "bg-[#275580]",
    BP: "bg-[#4a4a4a]",
  }[level];
  return (
    <span
      className={`${bg} inline-block rounded-xs px-2 py-0.5 text-xs font-bold text-white`}
      title="WCAG conformance level"
    >
      {level}
    </span>
  );
}
