import type { ConformanceLabel } from "../api/types";

/** WCAG conformance badge (A/AA/AAA/BP), shared by the list, detail, and evidence. */
export default function ConformanceBadge({ level }: { level: ConformanceLabel }) {
  const bg = {
    A: "bg-[#b00060]",
    AA: "bg-[#4b1d8a]",
    AAA: "bg-[#2e6694]",
    BP: "bg-[#4a4a4a]",
  }[level];
  return (
    <span
      className={`${bg} inline-block rounded-xs px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-white`}
      title="WCAG conformance level"
    >
      {level}
    </span>
  );
}
