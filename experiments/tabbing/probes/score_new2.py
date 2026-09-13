"""Score R6-R9 on top of C13, offline, from saved observations.

Same discipline as score_new.py: C9 is rebuilt from the published artifact,
every rule is stated before it is applied, and the answer key is read only to
score, never to decide.
"""
import json, sys, pathlib

ROOT = pathlib.Path("experiments/tabbing")
S = pathlib.Path(sys.argv[1])
d = json.loads((ROOT / "fixtures/results/bakeoff-fixtures-cheap-study-v1.json").read_text())
truth = json.loads((ROOT / "fixtures/truth.json").read_text())
labels = {p: r.get("labels_by_viewport", {}).get("desktop", r["label"]) for p, r in truth["probes"].items()}
universe = set(labels)
positive = {p for p, l in labels.items() if l == "violation"}
negative = universe - positive

c9 = set(d["reported"][next(k for k in d["reported"] if k.startswith("C9"))])
unk = set(d["unobservable"][next(k for k in d["unobservable"] if k.startswith("C9"))])
feat = {p: f for ev in d["candidate_evidence"].values() for p, f in ev["features"].items()}
con = json.loads((S / "containment.json").read_text())
comp = json.loads((S / "composite.json").read_text())
eff = json.loads((S / "effect.json").read_text())
eff2 = json.loads((S / "effect2.json").read_text())

r1 = {p for p in c9 if con.get(p, {}).get("contains_focusable") or con.get(p, {}).get("inside_focusable")}
r2 = {p for p in c9 if comp.get(p, {}).get("owner_role") and comp.get(p, {}).get("sibling_tabbable")
      and (comp.get(p, {}).get("own_tabindex") or "") == "-1"}
r3 = {p for p in c9 if comp.get(p, {}).get("aria_keyshortcuts") or comp.get(p, {}).get("chord_in_text")}
r5 = {p for p in c9 if eff.get(p, {}).get("own_activation") == []
      and not feat.get(p, {}).get("delegated_types")
      and not feat.get(p, {}).get("label_toggle")
      and eff.get(p, {}).get("hover_reveal") is False}
c13 = c9 - r1 - r2 - r3 - r5

# R6 name twin: a visible, Tab-reachable native control carries the same
#    accessible name, so the action already has a keyboard route.
r6 = {p for p in c13 if eff2.get(p, {}).get("name_twin")}
# R7 framework props beat delegation: the element sits in a React tree and its
#    own props carry no activation prop, so the root delegation listener that
#    C7 saw says nothing about this element.
r7 = {p for p in c13 if eff2.get(p, {}).get("framework")
      and eff2.get(p, {}).get("framework_activation") is False}
# R8 no click effect: a real click changes nothing rendered, so there is no
#    action for a keyboard user to be missing.
r8 = {p for p in c13 if eff2.get(p, {}).get("click_effect") is False}
# R9 divergent key effect (a PROMOTION, not a dismissal): click and keyboard
#    both do something, but not the same something.
r9 = {p for p in universe if eff2.get(p, {}).get("click_effect")
      and eff2.get(p, {}).get("key_effect") and eff2.get(p, {}).get("same_effect") is False}


def score(name, reported, unknown=unk):
    reported = reported - unknown
    tp, fp = len(reported & positive), len(reported & negative)
    fn = len(positive - reported - unknown)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / len(positive)
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    print(f"{name:<44} TP {tp:>2} FP {fp:>2} FN {fn:>2}  P {pr*100:5.1f} R {rc*100:5.1f} F1 {f1*100:5.1f}")


for tag, rule, kind in (("R6 name twin", r6, "dismiss"), ("R7 framework props beat delegation", r7, "dismiss"),
                        ("R8 no click effect", r8, "dismiss"), ("R9 divergent key effect", r9, "promote")):
    if kind == "dismiss":
        print(f"{tag}: {sorted(rule)}  real defects LOST {sorted(rule & positive) or 'none'}"
              f"  false alarms removed {sorted(rule & negative) or 'none'}")
    else:
        add = rule - c13
        print(f"{tag}: {sorted(rule)}  newly flagged {sorted(add)}"
              f"  of which real {sorted(add & positive) or 'none'}, wrong {sorted(add & negative) or 'none'}")
print()
score("C13 (static rules only)", c13)
score("C14 = C13 - R6", c13 - r6)
score("C15 = C14 - R7 - R8", c13 - r6 - r7 - r8)
score("C16 = C15 + R9 promotions", (c13 - r6 - r7 - r8) | r9, unk - r9)
