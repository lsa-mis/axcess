import type { AlfaCapability, LocalAnalysisCapability } from "../../api/types";
import type { FieldError, ScanPolicy, ScanSettings } from "./scanPolicy";

/** What the server says this installation can do; `undefined` while loading. */
export type Capabilities = {
  alfa?: AlfaCapability;
  local?: LocalAnalysisCapability;
};

/** The props every settings group takes. */
export type GroupProps = {
  settings: ScanSettings;
  update: (patch: Partial<ScanSettings>) => void;
  policy: ScanPolicy;
  capabilities: Capabilities;
  errors: FieldError[];
  /** DOM ids for the fields the error alert can link to. */
  fieldIds: { static_only: string };
};
