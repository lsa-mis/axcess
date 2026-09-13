"""Score candidate dismissal rules on top of C9, offline, from saved evidence.

Rebuilds C9 exactly as analyze_candidates.py does, then subtracts each new
rule's dismissals and reprints precision / strict recall / F1. No detector or
scoring code is imported; the answer key is read only to score, never to decide.
"""
import json, sys, pathlib
ROOT = pathlib.Path("experiments/tabbing")
SCRATCH = pathlib.Path(sys.argv[1])

data = json.loads((ROOT / "fixtures/results/bakeoff-fixtures-cheap-study-v1.json").read_text())
truth = json.loads((ROOT / "fixtures/truth.json").read_text())
labels = {p: r.get("labels_by_viewport", {}).get("desktop", r["label"]) for p, r in truth["probes"].items()}
universe, positive = set(labels), {p for p, l in labels.items() if l == "violation"}
negative = universe - positive

contain = json.loads((SCRATCH / "containment.json").read_text())
comp = json.loads((SCRATCH / "composite.json").read_text())
feat = {p: f for ev in data["candidate_evidence"].values() for p, f in ev["features"].items()}

c9 = set(data["reported"]["C9 = C8 and a clear center hit"]) if "C9 = C8 and a clear center hit" in data["reported"] \
     else set(data["reported"][next(n for n in data["reported"] if n.startswith("C9"))])
unk9 = set(data["unobservable"][next(n for n in data["unobservable"] if n.startswith("C9"))])

def score(name, reported, unknown):
    tp, fp = len(reported & positive), len(reported & negative)
    fn = len(positive - reported - unknown)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / len(positive)
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    print(f"{name:<46} TP {tp:>2} FP {fp:>2} FN {fn:>2}  P {p*100:5.1f} R {r*100:5.1f} F1 {f1*100:5.1f}")
    return reported

# --- the candidate dismissal rules, each stated before it is scored -----------
# R1 redundant click surface: the lead wraps, or sits inside, a keyboard-
#    reachable native control, so the same action already has a tab stop.
r1 = {p for p in c9 if contain.get(p, {}).get("contains_focusable") or contain.get(p, {}).get("inside_focusable")}
# R2 roving tabindex: an ARIA item role inside a composite container whose
#    sibling holds the tab stop -- the APG arrow-key pattern, not a defect.
r2 = {p for p in c9 if comp.get(p, {}).get("owner_role") and comp.get(p, {}).get("sibling_tabbable")
      and (comp.get(p, {}).get("own_tabindex") or "").strip() == "-1"}
# R3 declared shortcut: aria-keyshortcuts, or a chord such as "Alt+K" in the
#    element's own accessible text, names a keyboard path to the same action.
r3 = {p for p in c9 if comp.get(p, {}).get("aria_keyshortcuts") or comp.get(p, {}).get("chord_in_text")}
# R4 (comparison only) any directly bound key handler.
r4 = {p for p in c9 if feat.get(p, {}).get("has_key_handler")}

for tag, rule in (("R1 redundant click surface", r1), ("R2 roving tabindex", r2),
                  ("R3 declared shortcut", r3), ("R4 any direct key handler", r4)):
    lost, removed = sorted(rule & positive), sorted(rule & negative)
    print(f"{tag}: dismisses {sorted(rule)}  real defects LOST {lost or 'none'}  false alarms removed {removed or 'none'}")
print()
score("C9 (Codex baseline)", c9, unk9)
score("C10 = C9 - R1", c9 - r1, unk9)
score("C11 = C9 - R1 - R2", c9 - r1 - r2, unk9)
score("C12 = C9 - R1 - R2 - R3", c9 - r1 - r2 - r3, unk9)
score("(compare) C9 - R4 only", c9 - r4, unk9)

# --- R5, added after the structural-hover measurement ------------------------
# R5 no action path at all: no activation listener bound to the element, no
#    delegated listener reaching it, no label/control relation, and hovering
#    reveals nothing that was hidden. Nothing observed can carry out an action,
#    so there is no keyboard operation to be missing.
eff = json.loads((SCRATCH / "effect.json").read_text())
def inert_lead(p):
    e, f = eff.get(p, {}), feat.get(p, {})
    return (e.get("own_activation") == [] and not f.get("delegated_types")
            and not f.get("label_toggle") and e.get("hover_reveal") is False)
r5 = {p for p in c9 if inert_lead(p)}
print()
lost, removed = sorted(r5 & positive), sorted(r5 & negative)
print(f"R5 no observable action path: dismisses {sorted(r5)}  real defects LOST {lost or 'none'}  false alarms removed {removed or 'none'}")
allp = {p for p in universe if inert_lead(p)}
print(f"   fires on {len(allp)} probes corpus-wide; real defects it would suppress anywhere: {sorted(allp & positive) or 'none'}")
print()
score("C13 = C9 - R1 - R2 - R3 - R5", c9 - r1 - r2 - r3 - r5, unk9)
