import { useId } from "react";
import type { SearchConfig, SearchField, SearchTarget } from "../api/types";
import { Button, Checkbox, Select } from "./ui";

const control = "min-h-target w-full rounded-xs border border-border bg-surface px-3 py-2 text-sm text-fg";
const defaults: SearchConfig = {
  confirmed: false, page_url: "", fields: [{ by: "label", target: "Search", value: "", kind: "text" }],
  submit: null, results_selector: "[role=option], a[href]", next_button: null,
  max_result_pages: 3, max_results: 20, timeout_ms: 5000,
};

function Text({ label, value, onChange, required = false, maxLength = 300, type = "text", hint }: {
  label: string; value: string; onChange: (value: string) => void; required?: boolean; maxLength?: number;
  type?: "text" | "url"; hint?: string;
}) {
  const hintId = useId();
  return <div>
    <label className="block text-sm">{label}<input className={control} type={type} pattern={type === "url" ? "https?://.+" : undefined} aria-describedby={hint ? hintId : undefined} required={required} maxLength={maxLength} value={value} onChange={e => onChange(e.target.value)} /></label>
    {hint && <p id={hintId} className="mt-1 text-xs text-fg-muted">{hint}</p>}
  </div>;
}

function Target({ label, value, onChange }: { label: string; value: SearchTarget; onChange: (value: SearchTarget) => void }) {
  return <div className="grid gap-2 sm:grid-cols-2">
    <Select stacked label={`${label}: find it by`} value={value.by}
      onChange={next => onChange({ ...value, by: next as SearchTarget["by"] })}
      options={[
        { value: "label", label: "Its label (accessible name)" },
        { value: "selector", label: "Element locator (CSS selector)" },
      ]} />
    <Text label={`${label} ${value.by === "label" ? "label" : "element locator (CSS selector)"}`} value={value.target} required onChange={target => onChange({ ...value, target })} />
  </div>;
}

export default function SearchSettings({ value, onChange, disabled = false }: {
  value?: SearchConfig | null; onChange: (value: SearchConfig | null) => void; disabled?: boolean;
}) {
  const update = (patch: Partial<SearchConfig>) => value && onChange({ ...value, ...patch });
  const field = (index: number, patch: Partial<SearchField>) => value && update({ fields: value.fields.map((item, i) => i === index ? { ...item, ...patch } : item) });
  // The switch sits at the same level as the other advanced options; only
  // the details it reveals are boxed, so an off switch takes one line like
  // its neighbours instead of a titled container of its own.
  return <>
    <Checkbox checked={!!value} disabled={disabled && !value} onChange={enabled => onChange(enabled ? structuredClone(defaults) : null)}
      label="Use a search box to find more pages" hint="For sites where some pages appear only after a search. Needs a browser and Rule check (axe)." />
    {value && <fieldset className="ml-6 space-y-3 rounded-xs border border-border p-4">
      <legend className="px-1 text-sm font-semibold">Search settings</legend>
      {disabled && <p role="alert" className="text-sm text-sev-major">To use search, choose axe or Both as the rule check tool, and turn off Fast scan.</p>}
      <p className="text-sm text-fg-muted">Use only harmless example words. Axcess saves these settings with the report on this computer. Never enter passwords, verification codes, or personal records.</p>
      <Text label="Search page address (leave blank to use the start page)" type="url" hint="Leave this blank to search on the start page. Or enter a full address that starts with http:// or https:// and is inside the scan. Put the words to search for in the field value below." value={value.page_url} maxLength={2048} onChange={page_url => update({ page_url })} />
      {value.fields.map((item, index) => <fieldset key={index} className="space-y-2 border-t border-border pt-3">
        <legend className="text-sm font-semibold">Search field {index + 1}</legend>
        <Target label={`Field ${index + 1}`} value={item} onChange={patch => field(index, patch)} />
        <Select stacked label={`Field ${index + 1} type`} value={item.kind}
          onChange={next => field(index, { kind: next as SearchField["kind"] })}
          options={[
            { value: "text", label: "Text box" },
            { value: "select", label: "Drop-down list (choose an option by its name)" },
          ]} />
        <Text label={`Field ${index + 1} value`} hint={item.kind === "text" ? "The words to search for, for example LSA." : "The name of the option to choose, as it appears on screen."} value={item.value} maxLength={200} onChange={text => field(index, { value: text })} />
        {value.fields.length > 1 && <Button type="button" onClick={() => update({ fields: value.fields.filter((_, i) => i !== index) })}>Remove search field {index + 1}</Button>}
      </fieldset>)}
      <Button type="button" disabled={value.fields.length >= 6} onClick={() => update({ fields: [...value.fields, { by: "label", target: "", value: "", kind: "text" }] })}>Add search field</Button>
      <Checkbox checked={!!value.submit} onChange={enabled => update({ submit: enabled ? { by: "label", target: "Search" } : null })} label="Press a search button" hint="Leave this off when results appear as you type (autocomplete)." />
      {value.submit && <Target label="Search button" value={value.submit} onChange={submit => update({ submit })} />}
      <Text label="Search result locator (CSS selector)" value={value.results_selector} required onChange={results_selector => update({ results_selector })} />
      <p className="text-xs text-fg-muted">Match only result links or result options you can click. For example, [role=option] or .results a.</p>
      <Checkbox checked={!!value.next_button} onChange={enabled => update({ next_button: enabled ? { by: "label", target: "Next" } : null })} label="Open more pages of results" />
      {value.next_button && <Target label="Next results button" value={value.next_button} onChange={next_button => update({ next_button })} />}
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="text-sm">Maximum results<input className={control} type="number" min={1} max={50} required value={value.max_results} onChange={e => update({ max_results: Number(e.target.value) })} /></label>
        <label className="text-sm">Maximum result pages<input className={control} type="number" min={1} max={5} required value={value.max_result_pages} onChange={e => update({ max_result_pages: Number(e.target.value) })} /></label>
      </div>
      <label className="flex min-h-target items-start gap-2 text-sm"><input type="checkbox" required checked={value.confirmed} onChange={e => update({ confirmed: e.target.checked })} className="mt-1" />
        I allow Axcess to type these searches and click the results. These settings only search and open results. They do not change any records.
      </label>
    </fieldset>}
  </>;
}
