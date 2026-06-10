/** React binding for the tracker store. */

import { useSyncExternalStore } from "react";
import { store } from "./store";
import type { AppData } from "./types";

export function useAppData(): AppData {
  return useSyncExternalStore(store.subscribe, store.getSnapshot);
}
