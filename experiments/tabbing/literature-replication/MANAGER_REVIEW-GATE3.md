# Gate 3 — protocol cleared; scoring still BLOCKED

Manager: gpt-6-astra in Hermes, succeeding Opus 5's manager role. Independent
reviewer: fresh Codex CLI context. No scoring, detector edits, commits, captures,
network research, installs, or additional agent assignments in this task.
All operations were container-side in the verified Arch/podman environment.

## Disposition

| Finding | Gate-3 disposition | Evidence / next owner |
| --- | --- | --- |
| R1 | CLOSED at protocol-document level | FEASIBILITY.md §6.5–6.8; Codex concurs |
| R2 | CLOSED at protocol-document level | §6.1, §6.3, §6.5–6.6; Codex concurs |
| R7 | CLOSED at protocol-document level | §6.1, §6.4, §6.7; Codex concurs |
| R3 | REOPENED, major | Missing `tagged` metadata accepted; manager reproduced; Claude Code owns correction |
| R4 | REOPENED, blocking | Closed shadow roots collapse identities without exclusion; manager browser-confirmed; Claude Code owns correction |
| R6 | OPEN, separate user decision | Neither attempted nor waived |
| R5 | Deferred | Revisit before interactive subjects are scored |

The original R3/R4 fixes and their handover-verified tests remain accepted.
The new findings concern additional latent paths, not proof that the recorded
three-subject feasibility results were wrong. The manager did not re-derive
any result listed as verified in HANDOVER.md §4.

**Scoring is not approved.** Required: R3/R4 correction and independent clearance,
separate R6 clearance/decision, complete frozen execution manifest/control plan,
and explicit manager approval within Harry's authorization. No second Codex
review or Claude implementation run was launched in this task.

## What changed

Only FEASIBILITY.md §6 was rewritten in the existing scientific documents.
It fixes exact-fraction comparisons, exclusive outcome buckets, page/element
estimands, repeat/arm aggregation, unknown labels, abstention precedence and
positive/negative accounting, three-page versus historical-corpus scope, and
the historical claim ceiling. It explicitly supersedes §4's unsupported
functional-fidelity inference without altering retained observations. It leaves
manifest completion as a separate execution prerequisite, not a claim that a
scorer or baseline configuration has been implemented.

New audit artifacts: REVIEW_BRIEF-GATE3.md, CODEX_REVIEW-GATE3.md, this record.
HANDOVER.md receives a current-status banner; its historical body stays intact.

## Verification of the new protocol rules

Before testing, the manager predicted that equality is never a gain, comparisons
are exclusive, and all labelled pages survive denominator accounting. Any overlap
or leak would falsify closure. Controls: exact equality and no-abstention matrices.

In-memory Python/Fraction transcription, not a production scorer: two passes,
each checking 256 metric-pair combinations, 729 confusion-matrix/abstention
combinations, four disposition controls, and two repeat-agreement controls.
Both passes had zero assertion failures (spread zero). The old rounded-threshold
control demonstrates that 36/39 exceeds 923/1000 despite equalling the exact
reference; the new rule classifies exact equality as a tie.

Codex read the rewrite and independently returned R1/R2/R7 CLOSED. The manager
checked the report against §6's explicit definitions. This is documentation
closure, not evidence that a scoring implementation conforms to the protocol.

## New defect log and independent counterexamples

These are recorded here before any fix; the global out-of-repository defect log
was not modified under this narrowly scoped task.

| Defect ID | Author of reviewed implementation | Finder | Gate | Class | Severity |
| --- | --- | --- | --- | --- | --- |
| g3-missing-arm-metadata | Claude Code | Codex; independently reproduced by manager gpt-6-astra | gate-3-review | latent-correctness | major |
| g3-closed-shadow-identity | Claude Code | Codex inference; independently browser-confirmed by manager gpt-6-astra | gate-3-review | latent-correctness | blocking |

Pre-registered in chat before execution: missing `tagged` will incorrectly
receive H0 survival; two closed-root buttons will share one unmarked identity.
Rejecting the malformed record, or distinct/explicitly unsupported closed-root
identities, would falsify the respective finding. Controls: complete metadata
and the same two buttons in an open root. Two repeats, open/closed order reversed
on repeat two; all results retained. These checks use entirely synthetic in-memory
inputs and do not load captures, truth files, or previous feasibility results.

Exact manager command, from this experiment directory:

```bash
uv run --offline --no-sync python -B -c 'import copy, json; from tools.adjudicate_g1c import adjudicate; from tools.replay import FOCUS_PROBE_JS, OPAQUE_SCOPE; from playwright.sync_api import sync_playwright
for n in range(2):
 rows=[dict(subject=s,tagged=a,repeat=r,ok=True,focus_trail=[str(i) for i in range(15)]) for s in ("citiprogram","coronavirus","craigslist") for a in (False,True) for r in (0,1)]
 control=adjudicate(rows); broken=copy.deepcopy(rows); del broken[0]["tagged"]; result=adjudicate(broken)
 print(json.dumps(dict(check="R3",repeat=n,control=control.verdict,missing_tagged=result.verdict,invalid_problems=result.problems)))
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True)
 for n in range(2):
  for mode in (("open","closed") if n==0 else ("closed","open")):
   c=b.new_context(); p=c.new_page(); p.set_content("<div id=host></div>")
   p.evaluate("mode => { window.root = document.getElementById(\"host\").attachShadow({mode}); root.innerHTML = \"<button>A</button><button>B</button>\"; }",mode)
   ids=[]; actual=[]
   for i in range(2):
    p.evaluate("i => root.children[i].focus()",i); ids.append(p.evaluate(FOCUS_PROBE_JS)); actual.append(p.evaluate("root.activeElement.textContent"))
   print(json.dumps(dict(check="R4",repeat=n,mode=mode,actual_focus=actual,identities=ids,distinct=len(set(ids)),unsupported=any(OPAQUE_SCOPE in x for x in ids))))
   c.close()
 b.close()'
```

Observed manager output (exit 0), retained without dropping either repeat:

```jsonl
{"check":"R3","repeat":0,"control":"H0 NOT FALSIFIED -- tagged and untagged trails identical on all three subjects","missing_tagged":"H0 NOT FALSIFIED -- tagged and untagged trails identical on all three subjects","invalid_problems":[]}
{"check":"R3","repeat":1,"control":"H0 NOT FALSIFIED -- tagged and untagged trails identical on all three subjects","missing_tagged":"H0 NOT FALSIFIED -- tagged and untagged trails identical on all three subjects","invalid_problems":[]}
{"check":"R4","repeat":0,"mode":"open","actual_focus":["A","B"],"identities":["1:body/0:div/#s0:button","1:body/0:div/#s1:button"],"distinct":2,"unsupported":false}
{"check":"R4","repeat":0,"mode":"closed","actual_focus":["A","B"],"identities":["1:body/0:div","1:body/0:div"],"distinct":1,"unsupported":false}
{"check":"R4","repeat":1,"mode":"closed","actual_focus":["A","B"],"identities":["1:body/0:div","1:body/0:div"],"distinct":1,"unsupported":false}
{"check":"R4","repeat":1,"mode":"open","actual_focus":["A","B"],"identities":["1:body/0:div/#s0:button","1:body/0:div/#s1:button"],"distinct":2,"unsupported":false}
```

Within-condition distinct-identity spread: zero. R3 incorrectly accepts malformed
metadata in both repeats. R4's closed-root condition produces one identity versus
two in the open control, despite the fixture confirming actual focus on A then B.
The fixture's retained closed-root reference is only an answer-key observation;
it is not injected into the production probe or offered as a repair.

## Review budget and provenance

One Codex run, `--sandbox read-only`, existing ChatGPT login, no bypass.
Process handle: `proc_2d3acb969d02`, exit 0. Brief cap: eight shell commands,
12,000 words of file output, ten minutes. Codex reports six commands across five
shell calls and approximately 11.4k words of file output; those are reviewer
self-reports, not independently recounted here.

CLI completion event usage: input_tokens=186998, cached_input_tokens=152320,
output_tokens=6238, reasoning_output_tokens=3736. Dollar cost and live subscription
quota are unavailable; no API-funded fallback was selected. No efficiency claim
is inferred from comparison with prior reviews.

SHA-256 fingerprints taken after the rewrite and during the read-only review:

```text
6230e1b9a9db330e505127a3139b326d82367730d4d890bc34fbfcd72b4f2835  FEASIBILITY.md
f4ba70f2ba91e9cad8ac9914f3c28b4d855335732494cc12cc64e909da6ec48f  REVIEW_BRIEF-GATE3.md
19dd9a21cf7d503c4c93ddc40fde63ee86cfb593e7b35c362573aaa8f16b2b82  tools/replay.py
e309f1f7493966eb1c0b110116ea4ddbc6618c91b6e9427fd917097165e099a0  tools/adjudicate_g1c.py
```

The manager read back CODEX_REVIEW-GATE3.md before accepting the reviewer
verdict. Git tracked-file diff remained empty at the review checkpoint;
these experiment artifacts remain untracked and nothing was committed.
