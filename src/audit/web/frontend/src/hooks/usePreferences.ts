import { useSyncExternalStore } from "react";
import {
  applyPreferences,
  DEFAULT_PREFERENCES,
  loadPreferences,
  savePreferences,
  watchSystemTheme,
  type Preferences,
} from "../lib/preferences";

/**
 * One store for the whole app, outside React, so the shell, the Settings
 * page and a table's pager all read the same value and a change applies
 * everywhere at once without a provider around the tree.
 */
let current: Preferences = loadPreferences();
const listeners = new Set<() => void>();

function commit(next: Preferences) {
  current = next;
  savePreferences(next);
  applyPreferences(next);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

// Another tab changed them: pick that up rather than overwrite it later.
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key !== "axcess.preferences") return;
    current = loadPreferences();
    applyPreferences(current);
    listeners.forEach((listener) => listener());
  });
  // Theme "System" re-resolves when the OS switches between light and dark.
  watchSystemTheme(() => {
    if (current.theme === "system") applyPreferences(current);
  });
}

export function getPreferences(): Preferences {
  return current;
}

export function setPreference<K extends keyof Preferences>(key: K, value: Preferences[K]) {
  if (current[key] === value) return;
  commit({ ...current, [key]: value });
}

export function updatePreferences(values: Partial<Preferences>) {
  commit({ ...current, ...values });
}

export function resetPreferences() {
  commit({ ...DEFAULT_PREFERENCES });
}

export function usePreferences(): Preferences {
  return useSyncExternalStore(subscribe, getPreferences, getPreferences);
}

/** Rows per page for every paged table. */
export function useTablePageSize(): number {
  return Number(usePreferences().rowsPerPage);
}

/**
 * The Confirm before deleting setting, for a native confirm() gate: returns
 * true straight away when the reader has turned confirmations off.
 */
export function confirmDestructive(message: string): boolean {
  if (current.confirmDelete === "off") return true;
  return window.confirm(message);
}
