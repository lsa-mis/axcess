# Model trials on llama.cpp, 2026-11-11

Small first look at newer models for the private AI tiers (decision 6 in
`llama-cpp-plan.md`). Not a measurement that can pick a model: the sets are
far too small (see "What this can and cannot show").

## Setup

- llama.cpp b12284, Vulkan build, Intel Iris Xe (TGL GT2), 8 CPU cores,
  15 GB RAM. One `llama-server` per model on a UNIX socket, `-c 8192`,
  `-ngl 99`. All models Q4_K_M; vision projectors Q8_0.
- Files downloaded from Hugging Face and checked against its SHA-256.
- Fix suggestions: `python -m audit.suggest.evals` with
  `AUDIT_MODEL_BACKEND=llama_cpp`, on `cases_v1.yaml` (5 made-up cases) and
  `cases_real_v1.yaml` (8 axe failures from the local scan of
  accessibility.umich.edu). Every answer was read by Claude; the verdicts
  below are Claude's reading and have not been checked by a person.
- Image text: the scan's classify prompt and parser (`OllamaProvider` with
  `backend="llama_cpp"`) on the 5 text images from that scan (4 distinct; 195
  and 202 are near-copies of one status legend) plus 2 fixture images, sent
  with empty OCR text for the fixtures.

## Models tried

| Model | Size (Q4_K_M) | Licence | Role tried |
| --- | --- | --- | --- |
| Qwen3-VL-2B-Instruct (today's Small vision model) | 1.1 GB + 0.45 GB projector | Apache-2.0 | images, fixes |
| Qwen3-4B-Instruct-2507 (newer than today's `qwen3:4b`) | 2.5 GB | Apache-2.0 | fixes |
| LFM3-Omni-2B (Liquid AI) | 1.1 GB + 0.5 GB projector | LFM Open License 1.0: no licence for commercial use by an organisation with $10M or more in yearly revenue | images, fixes |
| LFM3-VL-2B (Liquid AI) | 1.1 GB + 0.2 GB projector | LFM Open License 1.0 | images |
| LFM3-1.7B (Liquid AI) | 1.1 GB | LFM Open License 1.0 | fixes |
| Spark-X2.5-4B, Spark-X2.5-1.7B (XHToken) | 2.6 GB, 1.1 GB | Apache-2.0 | fixes |

Ruled out from the model cards without downloading: the d3 and d1 models
(decision classifiers with their own API, no free text), Mage-VL-Cowork (a
computer-use agent), Nemotron-3.5-Bolt-E4B (text only, Q8 8 GB is the
smallest GGUF).

## Fix suggestions

"Reasonable" is Claude's reading of each answer on the 8 real cases: would
the change fix the failure without breaking the element. Only aria-valid-attr
can be re-checked by axe on the fragment.

| Model | Made-up cases: rule check passed | Real cases: reasonable (Claude's reading) | Time per answer |
| --- | --- | --- | --- |
| Qwen3-4B-Instruct-2507 | 4/5 | about 5/8 | ~30 s |
| Spark-X2.5-4B (thinking off) | 5/5 | about 2/8 | ~55 s |
| LFM3-Omni-2B | 3/5 (one answer unusable) | 2/8 | ~20 s |
| Spark-X2.5-1.7B (thinking off) | 4/5 | about 1/8 | ~30 s |
| Qwen3-VL-2B | 4/5 | 0/8 | ~20 s |
| LFM3-1.7B | none: each request thought until the 120 s limit; not rerun with thinking off | | |

What went wrong, by case:
- Blue button (#333333 on #05a4d3, 4.37:1): every model made it worse
  (white text 2.89:1, #333333 on black 1.66:1, a swap that keeps 4.37:1).
- `aria-role="button"`: only Spark-X2.5-4B removed it; Qwen3-4B renamed it
  to the equally invalid `aria-button`; the rest left it unchanged.
- Skipped heading levels: Qwen3-4B moved them up a level (h3 to h2, likely
  right); Qwen3-VL-2B and LFM3-Omni-2B moved them down (wrong); Spark-X2.5-4B
  invented a new heading ("Introduction") or duplicated an id.
- Small links: only Qwen3-4B used `display: inline-block` with a minimum
  size; the others set width on an inline link, which does nothing, or
  fixed the width at 24 px, which cuts the text.
- Reasoning models (LFM3-1.7B, both Spark models) think for 2,000+ tokens
  per answer unless `llama-server` runs with `--reasoning off`.

The made-up cases do not separate the models; the real ones do.

## Image text

| Model | Near-copies 195 and 202 | "BUY NOW TODAY" banner with no OCR text | Time per image |
| --- | --- | --- | --- |
| Qwen3-VL-2B | different labels (essential, decorative) | "no meaningful text" (missed it) | 3–32 s |
| LFM3-Omni-2B | same label | essential (read it from the picture) | 4–17 s |
| LFM3-VL-2B | same label | essential | 15–121 s |

All three called the infographics (4, 63) "informational" and the button
image (8) "essential". No answers have been labelled by a person, so none of
this is accuracy.

## What this can and cannot show

- It can show failure patterns and speed on this machine. It cannot rank
  models: 8 real fix cases from one site, 4 distinct real images, one
  reader, no person has checked the verdicts.
- Speeds are for an Intel Iris Xe over Vulkan; LFM3-VL-2B's slowness may be
  this GPU.

## Leads for the next round

1. Fix suggestions, Small tier: Qwen3-4B-Instruct-2507 is the lead (Apache-2.0,
   best on the real cases). Today's Standard and Large text models
   (`qwen2.5-coder:7b`, `:14b`) were not tried (disk space).
2. A 2B vision model is not good enough at fixes to serve both jobs, so plan
   on two models per tier.
3. Image text: LFM3-Omni-2B looks better than Qwen3-VL-2B, but its licence
   needs a decision before it ships, and a labelled set of real images is
   needed before any switch.
4. The Phase 2 launcher must pass `--reasoning off` (or a budget) for
   reasoning models.
5. Colour fixes failed everywhere: the prompt could give the model the
   computed ratio of each candidate colour, or Axcess could compute a passing
   colour itself.
