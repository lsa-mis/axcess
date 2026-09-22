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
 */
export default function SettingsGroup({
  id,
  legend,
  description,
  note,
  children,
  className,
}: {
  id: string;
  legend: string;
  description?: string;
  note?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const descriptionId = `${id}-description`;
  return (
    <fieldset
      id={id}
      aria-describedby={description ? descriptionId : undefined}
      className={cn("m-0 min-w-0 border-0 p-0", className)}
    >
      <legend className="p-0 text-sm font-semibold text-fg">{legend}</legend>
      {description && (
        <p id={descriptionId} className="mt-0.5 text-xs text-fg-muted">
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
      <div className="mt-3 flex flex-col gap-4">{children}</div>
    </fieldset>
  );
}
