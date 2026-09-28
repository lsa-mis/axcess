import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

/**
 * One named group of settings: a real fieldset with a legend you can see.
 *
 * The advanced list used to sit under one sr-only "Options" legend, so a
 * screen reader heard fourteen unrelated switches as one list and a sighted
 * reader saw no structure at all. The legend here is the group's name, the
 * description is wired as the fieldset's own description, and `note` is
 * where a mode explains what it has pinned (the login form's fixed settings)
 * instead of rendering disabled controls for them.
 *
 * `card` draws the fieldset as a card with the legend sitting on its top
 * border, which is the fieldset's own layout, not a painted imitation.
 * `plain` is for a group that already sits inside a disclosure: the
 * disclosure's button shows the same name, so the legend is kept for a
 * screen reader only.
 */
export default function SettingsGroup({
  id,
  legend,
  description,
  note,
  children,
  variant = "card",
  className,
}: {
  id: string;
  legend: string;
  description?: string;
  note?: ReactNode;
  children: ReactNode;
  variant?: "card" | "plain";
  className?: string;
}) {
  const descriptionId = `${id}-description`;
  const card = variant === "card";
  return (
    <fieldset
      id={id}
      aria-describedby={description ? descriptionId : undefined}
      className={cn(
        "m-0 min-w-0",
        card ? "rounded-xs border border-border bg-surface px-4 pb-4 pt-1 sm:px-5" : "border-0 p-0",
        className,
      )}
    >
      <legend className={card ? "-ml-1 px-1 text-sm font-semibold text-fg" : "sr-only"}>{legend}</legend>
      {description && (
        <p id={descriptionId} className={cn("text-xs text-fg-muted", card && "mt-1")}>
          {description}
        </p>
      )}
      {note && (
        <p
          role="note"
          className="mt-3 rounded-xs bg-surface-muted px-3 py-2 text-xs leading-relaxed text-fg"
        >
          {note}
        </p>
      )}
      <div className={cn("flex flex-col gap-4", (card || description || note) && "mt-3")}>{children}</div>
    </fieldset>
  );
}

/**
 * Switch rows stacked in one column with a rule between each, the way the
 * cards list their settings. The negative margin lines each switch up
 * with the group's text while its row keeps the padding for its hover.
 */
export function SwitchList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("-mx-2 flex flex-col divide-y divide-border border-t border-border", className)}>
      {children}
    </div>
  );
}
