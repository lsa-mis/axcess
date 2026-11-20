"""Evolutionary search for the Word "no headings" visual-heading probe (an experiment).

Not product code: the probe it chose is frozen in office_check.py.

The product rule (``office_check._word_visual_headings`` at 946ad6f) fails a
Word file that uses no heading style and shows at least 2 "visual headings".
On the first fresh set all 6 file-level errors came from it (research doc,
"Why the fresh errors happen"). This script defines a family of probes,
each a set of switches and thresholds that say what makes a line look like
a heading relative to its own document, and searches it with a genetic
algorithm whose fitness is cross-validated on the development data only:
every labelled Word file in ``tests/real_pages/office_files.json`` whose
split is NOT "fresh2". The fresh2 files are never read here.

Commands (from the worktree root):

    env -u VIRTUAL_ENV uv run python scripts/office_heading_search.py features
    env -u VIRTUAL_ENV uv run python scripts/office_heading_search.py search [--generations N]
    env -u VIRTUAL_ENV uv run python scripts/office_heading_search.py nested [--generations N]
    env -u VIRTUAL_ENV uv run python scripts/office_heading_search.py report
    env -u VIRTUAL_ENV uv run python scripts/office_heading_search.py show '<genome json>'

``features`` reads each development file once with the app's own reader
(``office_check``) and caches one row per paragraph in
``artifacts/office-search/features.json``. ``search`` checkpoints its
population after every generation (``artifacts/office-search/main/``) and
resumes from the last checkpoint; ``nested`` runs the same search inside
each outer fold (``artifacts/office-search/nested/fold_K/``) to estimate
how well the whole procedure does on files it did not see.

File verdict = "Mostly sure" when another counted check (alt text, table
header, language, as at 946ad6f) fails, or the file uses no heading style
and the probe fires. Scored against the label ``barrier``; "disputed" and
damaged files are left out, as in the scorer.
"""

# ruff: noqa: S311 (random numbers drive a search, not security)
from __future__ import annotations

import argparse
import io
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audit.linked_files import office_check as oc  # noqa: E402

FILES = ROOT / "artifacts" / "office-real-files"
OUT = ROOT / "artifacts" / "office-search"
LABELS = ROOT / "tests" / "real_pages" / "office_files.json"
DEV_SPLITS = {"holdout", "tuning", "fresh"}

# ---------------------------------------------------------------------------
# Features: one row per non-empty paragraph, in body order


_NUMBERED = re.compile(
    r"^((section|part|article|chapter|step|appendix)\s+[\dIVXA-Z]+\b|"
    r"[IVX]{1,5}\.\s|[A-Z]\.\s|\d{1,2}(\.\d{1,2})*\.?\s)",
    re.IGNORECASE,
)


def _ppr_chain(part: Any) -> dict[str, tuple[str | None, Any]]:
    styles = oc._styles_part(part)
    out: dict[str, tuple[str | None, Any]] = {}
    if styles is None:
        return out
    for style in styles.element.iter(oc._q(oc._W, "style")):
        sid = style.get(oc._q(oc._W, "styleId")) or ""
        parent = style.find(oc._q(oc._W, "basedOn"))
        out[sid] = (
            parent.get(oc._q(oc._W, "val")) if parent is not None else None,
            style.find(oc._q(oc._W, "pPr")),
        )
    return out


def _para_props(
    paragraph: Any, chain: dict[str, tuple[str | None, Any]], default: str | None
) -> dict[str, Any]:
    """keepNext, numbering (a list item), spacing before/after, centred.

    Read from the style chain, then the paragraph."""
    props = paragraph.find(oc._q(oc._W, "pPr"))
    style = props.find(oc._q(oc._W, "pStyle")) if props is not None else None
    sid = style.get(oc._q(oc._W, "val")) if style is not None else default
    layers = []
    seen: set[str] = set()
    while sid and sid not in seen and sid in chain:
        seen.add(sid)
        parent, ppr = chain[sid]
        layers.append(ppr)
        sid = parent
    layers = [layer for layer in reversed(layers) if layer is not None]
    if props is not None:
        layers.append(props)
    out = {"keep_next": False, "list": False, "before": 0, "after": 0, "center": False}
    for layer in layers:
        keep = layer.find(oc._q(oc._W, "keepNext"))
        if keep is not None:
            value = keep.get(oc._q(oc._W, "val"))
            out["keep_next"] = value is None or oc._on(value)
        num = layer.find(oc._q(oc._W, "numPr"))
        if num is not None:
            num_id = num.find(oc._q(oc._W, "numId"))
            out["list"] = num_id is None or (num_id.get(oc._q(oc._W, "val")) or "0") != "0"
        spacing = layer.find(oc._q(oc._W, "spacing"))
        if spacing is not None:
            for side in ("before", "after"):
                value = spacing.get(oc._q(oc._W, side))
                if value and value.lstrip("-").isdigit():
                    out[side] = int(value)
        jc = layer.find(oc._q(oc._W, "jc"))
        if jc is not None:
            out["center"] = (jc.get(oc._q(oc._W, "val")) or "") == "center"
    return out


def _table_place(paragraph: Any) -> dict[str, Any] | None:
    cell = next(paragraph.iterancestors(oc._q(oc._W, "tc")), None)
    if cell is None:
        return None
    row = cell.getparent()
    table = row.getparent()
    rows = table.findall(oc._q(oc._W, "tr"))
    cells = [r.findall(oc._q(oc._W, "tc")) for r in rows]
    index = rows.index(row) if row in rows else -1
    plain = len(rows) >= 2 and max(len(r) for r in cells) >= 2 and oc._word_plain_grid(table, cells)
    marked_first = oc._word_look_first_row(table) or (
        bool(rows) and oc._word_repeats_first_row(rows[0])
    )
    header = (index == 0 and marked_first) or (row is not None and oc._word_repeats_first_row(row))
    return {
        "header_row": bool(header),
        "plain": bool(plain),
        "cols": max((len(r) for r in cells), default=0),
        "rows": len(rows),
        "row_index": index,
        "table": id(table),
    }


def file_features(data: bytes) -> dict[str, Any]:
    from docx.package import Package

    package = Package.open(io.BytesIO(data))
    part = package.main_document_part
    body = part.document.element.body
    oc._drop_fallbacks(body)
    look = oc._RunLook(part)
    chain = _ppr_chain(part)
    paras = []
    tables: dict[int, int] = {}
    for paragraph in body.iter(oc._q(oc._W, "p")):
        runs = look.runs(paragraph)
        text = "".join(chunk for chunk, _ in runs).strip()
        if not text:
            continue
        letters = sum(c.isalnum() for c in text)

        def share(test: Any, runs: list = runs, letters: int = letters) -> float:
            if not letters:
                return 0.0
            return sum(sum(c.isalnum() for c in w) for w, lk in runs if test(lk)) / letters

        sizes: dict[int, int] = {}
        for chunk, lk in runs:
            size = lk.get("sz", 20)
            sizes[size] = sizes.get(size, 0) + sum(c.isalnum() for c in chunk)
        alphabetic = [c for c in text if c.isalpha()]
        place = _table_place(paragraph)
        if place is not None:
            place["table"] = tables.setdefault(place["table"], len(tables))
        in_box = next(paragraph.iterancestors(oc._q(oc._W, "txbxContent")), None) is not None
        props = _para_props(paragraph, chain, look.default_paragraph)
        paras.append(
            {
                "words": len(text.split()),
                "letters": letters,
                "first": text[0],
                "colon": text.rstrip().endswith(":"),
                "numbered": bool(_NUMBERED.match(text)),
                "b": round(share(lambda lk: lk.get("b")), 3),
                "u": round(share(lambda lk: lk.get("u")), 3),
                "caps": round(share(lambda lk: lk.get("caps") or lk.get("smallCaps")), 3),
                "upper": len(alphabetic) >= 2 and all(c.isupper() for c in alphabetic),
                "sizes": sorted(sizes.items()),
                "table": place,
                "box": in_box,
                **props,
                "text": text[:80],
            }
        )
    levels = oc._word_heading_levels(part, body)
    other = oc.check_office(data, "docx")
    counted_other = sorted(c for c in other.failed if c in oc.COUNTED and c != "no_headings")
    return {
        "has_heading_style": bool(levels),
        "outcome": other.outcome,
        "other_counted": counted_other,
        "product_no_headings": "no_headings" in other.failed,
        "paras": paras,
    }


def load_dev() -> list[dict[str, Any]]:
    entries = json.loads(LABELS.read_text(encoding="utf-8"))["files"]
    return [e for e in entries if e["split"] in DEV_SPLITS and e["kind"] in {"docx", "google_doc"}]


def build_features() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in load_dev():
        paths = list(FILES.glob(f"{entry['sha256']}.*"))
        row: dict[str, Any] = {
            "id": entry["id"],
            "split": entry["split"],
            "barrier": entry["barrier"],
            "headings_label": entry["expected"]["headings"],
            "words_label": entry.get("words"),
        }
        if not paths:
            row["outcome"] = "missing"
        else:
            data = paths[0].read_bytes()
            if oc.sniff(data) != "docx":
                row["outcome"] = "not docx"
            else:
                try:
                    row.update(file_features(data))
                except Exception as exc:  # damaged as served
                    row["outcome"] = f"damaged {type(exc).__name__}"
        rows.append(row)
    (OUT / "features.json").write_text(json.dumps(rows), encoding="utf-8")
    print(len(rows), "files;", sum(r.get("outcome") == "checked" for r in rows), "checked")


# ---------------------------------------------------------------------------
# The probe family

#: Each gene: its allowed values, and the value that leaves it "off" (the
#: 946ad6f behaviour). A gene not at its off value is an active switch.
GENES: dict[str, tuple[list[Any], Any]] = {
    # A heading is a line of at most this many words.
    "max_words": ([6, 8, 10, 12, 15, 20], 12),
    # Share of a line's letters that must carry the emphasis.
    "share": ([0.6, 0.7, 0.8, 0.9, 1.0], 0.8),
    # Which kinds of emphasis make a line stand out.
    "use_bold": ([True, False], True),
    "use_underline": ([True, False], True),
    "use_caps": ([True, False], True),  # capitals, set as a font style or typed
    "use_size": ([True, False], True),
    # Larger text: at least this many half-points over the body text.
    "size_delta": ([2, 3, 4, 6, 8], 4),
    # Relative emphasis: a kind of emphasis does not count when at least this
    # share of the document's body text (lines longer than max_words) has it.
    "relative": ([None, 0.2, 0.33, 0.5, 0.67], None),
    # Lines ending in ":" are list introductions or labels, not headings.
    "colon": (["count", "skip", "skip_before_list"], "count"),
    # Lines in tables: all count / not in a marked header row / not in a data
    # table's (plain grid's) cells / not in any table.
    "tables": (["all", "not_header", "not_grid", "none"], "all"),
    # Lines in text boxes count or not.
    "boxes": ([True, False], True),
    # Words of body text a heading needs under it...
    "min_body": ([5, 10, 15, 20, 30, 40], 20),
    # ...or this share of the document's words, if smaller (short documents).
    "body_frac": ([None, 0.05, 0.1, 0.15], None),
    # ...or this many body paragraphs (a list of short items), if set.
    "min_paras": ([None, 2, 3, 4], None),
    # Other signals that make a short line stand out on their own.
    "keep_next": ([False, True], False),  # "keep with next" set
    # A short line starting with a typed section number ("2.", "IV.",
    # "Section 3"), not a Word list item, followed by a longer paragraph.
    "numbered": ([False, True], False),
    # A short line, not a list item, with at least this much space before it
    # (twentieths of a point: 120 = 6 pt, 240 = 12 pt).
    "space_before": ([None, 120, 240], None),
    # How many visual headings the document must show.
    "min_count": ([1, 2, 3, 4], 2),
    # The first line that stands out, if among the first 3 lines, is a title.
    "skip_title": ([False, True], False),
    # When more than this share of short lines stand out, emphasis marks
    # labels (a form), not headings: no visual headings.
    "label_cap": ([None, 0.5, 0.7], None),
}

#: Genes whose value is a threshold present in every probe: changing them
#: costs nothing; the rest are switches and cost a penalty when on.
THRESHOLDS = {"max_words", "share", "size_delta", "min_body", "min_count"}
PENALTY = 0.004


#: The probe frozen in office_check.py on 2026-11-20: the search's best
#: cross-validated probe, simplified (``simplify``) toward 946ad6f.
FROZEN: dict[str, Any] = {
    **{name: off for name, (_, off) in GENES.items()},
    "use_caps": False,
    "min_body": 40,
    "body_frac": 0.15,
    "min_count": 3,
}


def base_genome() -> dict[str, Any]:
    return {name: off for name, (_, off) in GENES.items()}


def active(genome: dict[str, Any]) -> list[str]:
    return [n for n, (_, off) in GENES.items() if n not in THRESHOLDS and genome[n] != off]


def visual_headings(paras: list[dict[str, Any]], g: dict[str, Any]) -> int:
    if not paras:
        return 0
    sizes: dict[int, int] = {}
    for p in paras:
        for size, n in p["sizes"]:
            sizes[size] = sizes.get(size, 0) + n
    body_size = max(sizes, key=lambda s: sizes[s]) if sizes else 20
    total_words = sum(p["words"] for p in paras)

    kinds = {"b": g["use_bold"], "u": g["use_underline"], "caps": g["use_caps"]}
    if g["relative"] is not None:
        long = [p for p in paras if p["words"] > g["max_words"]] or paras
        letters = sum(p["letters"] for p in long) or 1
        for kind in ("b", "u"):
            if sum(p[kind] * p["letters"] for p in long) / letters >= g["relative"]:
                kinds[kind] = False
        caps_share = sum((1.0 if p["upper"] else p["caps"]) * p["letters"] for p in long) / letters
        if caps_share >= g["relative"]:
            kinds["caps"] = False

    def big(p: dict[str, Any]) -> float:
        if not p["letters"]:
            return 0.0
        return sum(n for s, n in p["sizes"] if s >= body_size + g["size_delta"]) / p["letters"]

    def stands_out(i: int, p: dict[str, Any]) -> bool:
        if p["words"] > g["max_words"]:
            return False
        if not (p["first"].isalnum() or p["first"] == "("):
            return False
        if not p["letters"]:
            return False
        t = p["table"]
        if t is not None:
            if g["tables"] == "none":
                return False
            if g["tables"] == "not_header" and t["header_row"]:
                return False
            if g["tables"] == "not_grid" and (t["header_row"] or t["plain"]):
                return False
        if p["box"] and not g["boxes"]:
            return False
        if p["colon"]:
            if g["colon"] == "skip":
                return False
            if g["colon"] == "skip_before_list" and i + 1 < len(paras) and paras[i + 1]["list"]:
                return False
        s = g["share"]
        hit = (
            (kinds["b"] and p["b"] >= s)
            or (kinds["u"] and p["u"] >= s)
            or (kinds["caps"] and (p["caps"] >= s or p["upper"]))
            or (g["use_size"] and big(p) >= s)
            or (g["keep_next"] and p["keep_next"] and not p["list"])
            or (
                g["numbered"]
                and p["numbered"]
                and not p["list"]
                and i + 1 < len(paras)
                and paras[i + 1]["words"] > g["max_words"]
            )
            or (
                g["space_before"] is not None and p["before"] >= g["space_before"] and not p["list"]
            )
        )
        return bool(hit)

    flags = [stands_out(i, p) for i, p in enumerate(paras)]
    if g["label_cap"] is not None:
        short = [f for p, f in zip(paras, flags, strict=True) if p["words"] <= g["max_words"]]
        if short and sum(short) / len(short) > g["label_cap"]:
            return 0
    if g["skip_title"]:
        for i, f in enumerate(flags[:3]):
            if f:
                flags[i] = False
                break
    need = g["min_body"]
    if g["body_frac"] is not None:
        need = min(need, max(1, g["body_frac"] * total_words))
    count = 0
    words: int | None = None
    lines = 0

    def enough(words: int, lines: int) -> bool:
        return words >= need or (g["min_paras"] is not None and lines >= g["min_paras"])

    for p, f in zip(paras, flags, strict=True):
        if f:
            if words is not None and enough(words, lines):
                count += 1
            words, lines = 0, 0
        elif words is not None:
            words += p["words"]
            lines += 1
    if words is not None and enough(words, lines):
        count += 1
    return count


def predict(row: dict[str, Any], g: dict[str, Any]) -> bool:
    if row["other_counted"]:
        return True
    if row["has_heading_style"]:
        return False
    return visual_headings(row["paras"], g) >= g["min_count"]


# ---------------------------------------------------------------------------
# Scoring


def scored_rows() -> list[dict[str, Any]]:
    rows = json.loads((OUT / "features.json").read_text(encoding="utf-8"))
    return [r for r in rows if r.get("outcome") == "checked" and r["barrier"] != "disputed"]


def pr(pairs: list[tuple[bool, bool]]) -> tuple[float, float, int, int, int]:
    tp = sum(e and p for e, p in pairs)
    fp = sum(p and not e for e, p in pairs)
    fn = sum(e and not p for e, p in pairs)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return precision, recall, tp, fp, fn


def folds(rows: list[dict[str, Any]], k: int, seed: int) -> list[list[int]]:
    """Stratified by label: each fold gets its share of barriers."""
    rng = random.Random(seed)
    pos = [i for i, r in enumerate(rows) if r["barrier"] is True]
    neg = [i for i, r in enumerate(rows) if r["barrier"] is not True]
    rng.shuffle(pos)
    rng.shuffle(neg)
    out: list[list[int]] = [[] for _ in range(k)]
    for n, i in enumerate(pos + neg):
        out[n % k].append(i)
    return out


class Fitness:
    """Mean over R x K held-out folds of min(precision, recall) of the file
    verdict, minus PENALTY per active switch. The probes have no fitted
    parameters, so a fold's score is the probe's score on files in it; the
    mean over many folds rewards probes that are right on every part of the
    data rather than on the whole by a few files."""

    def __init__(
        self, rows: list[dict[str, Any]], k: int = 5, repeats: int = 10, seed: int = 0
    ) -> None:
        self.rows = rows
        self.splits = [f for r in range(repeats) for f in folds(rows, k, seed * 100 + r)]
        self.cache: dict[str, dict[str, Any]] = {}

    def __call__(self, g: dict[str, Any]) -> dict[str, Any]:
        key = json.dumps(g, sort_keys=True)
        if key in self.cache:
            return self.cache[key]
        preds = [predict(r, g) for r in self.rows]
        labels = [r["barrier"] is True for r in self.rows]
        per = []
        for fold in self.splits:
            p, rc, *_ = pr([(labels[i], preds[i]) for i in fold])
            per.append(min(p, rc))
        cv = sum(per) / len(per)
        p, rc, tp, fp, fn = pr(list(zip(labels, preds, strict=True)))
        result = {
            "cv_min_pr": round(cv, 4),
            "fitness": round(cv - PENALTY * len(active(g)), 4),
            "precision": round(p, 4),
            "recall": round(rc, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "fp_ids": [
                r["id"] for r, e, q in zip(self.rows, labels, preds, strict=True) if q and not e
            ],
            "fn_ids": [
                r["id"] for r, e, q in zip(self.rows, labels, preds, strict=True) if e and not q
            ],
        }
        self.cache[key] = result
        return result


# ---------------------------------------------------------------------------
# The genetic algorithm, checkpointed every generation


def random_genome(rng: random.Random) -> dict[str, Any]:
    return {name: rng.choice(values) for name, (values, _) in GENES.items()}


def mutate(g: dict[str, Any], rng: random.Random, rate: float = 0.15) -> dict[str, Any]:
    out = dict(g)
    for name, (values, _) in GENES.items():
        if rng.random() < rate:
            out[name] = rng.choice(values)
    return out


def crossover(a: dict[str, Any], b: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    return {name: (a if rng.random() < 0.5 else b)[name] for name in GENES}


def evolve(
    rows: list[dict[str, Any]],
    where: Path,
    generations: int,
    population: int = 150,
    seed: int = 1,
    log: bool = True,
) -> list[dict[str, Any]]:
    """Run (or resume) a search; returns the final population, best first."""
    where.mkdir(parents=True, exist_ok=True)
    fit = Fitness(rows)  # the same folds for every run; ``seed`` drives the search only
    done = sorted(where.glob("gen_*.json"))
    if done:
        state = json.loads(done[-1].read_text())
        gen = state["generation"] + 1
        pop = [m["genome"] for m in state["population"]]
        rng = random.Random()
        rng.setstate(_tuple(state["rng"]))
    else:
        gen = 0
        rng = random.Random(seed)
        pop = [base_genome()] + [random_genome(rng) for _ in range(population - 1)]
    while gen < generations:
        ranked = sorted(
            pop, key=lambda g: (-fit(g)["fitness"], -fit(g)["cv_min_pr"], len(active(g)))
        )
        elite = []
        seen: set[str] = set()
        for g in ranked:
            key = json.dumps(g, sort_keys=True)
            if key not in seen:
                seen.add(key)
                elite.append(g)
            if len(elite) == 4:
                break

        def pick(pop: list[dict[str, Any]] = pop) -> dict[str, Any]:
            return min(rng.sample(pop, 3), key=lambda member: -fit(member)["fitness"])

        children = list(elite)
        while len(children) < population:
            child = crossover(pick(), pick(), rng) if rng.random() < 0.7 else dict(pick())
            children.append(mutate(child, rng))
        pop = children
        state = {
            "generation": gen,
            "population": [
                {"genome": g, **fit(g)} for g in sorted(pop, key=lambda g: -fit(g)["fitness"])
            ],
            "rng": rng.getstate(),
        }
        (where / f"gen_{gen:03d}.json").write_text(json.dumps(state), encoding="utf-8")
        best = state["population"][0]
        line = (
            f"gen {gen:3d} best fitness {best['fitness']:.4f} cv {best['cv_min_pr']:.4f} "
            f"P {best['precision']:.3f} R {best['recall']:.3f} fp {best['fp']} fn {best['fn']} "
            f"switches {active(best['genome'])}"
        )
        with (where / "log.txt").open("a") as handle:
            handle.write(line + "\n")
        if log:
            print(line, flush=True)
        gen += 1
    return sorted(pop, key=lambda g: (-fit(g)["fitness"], len(active(g))))


def _distance(value: Any, base: Any, values: list[Any]) -> int:
    """How far ``value`` is from ``base`` in the gene's list of values."""
    order = list(values) if base in values else [base, *values]
    return abs(order.index(value) - order.index(base))


def _tuple(value: Any) -> Any:
    return tuple(_tuple(v) for v in value) if isinstance(value, list) else value


def distinct_top(pop_state: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """Best probes whose file verdicts differ (two probes that decide every
    development file the same are one probe for this data)."""
    rows = scored_rows()
    out: list[dict[str, Any]] = []
    seen: set[tuple[bool, ...]] = set()
    for member in pop_state:
        sig = tuple(predict(r, member["genome"]) for r in rows)
        key = (sig, json.dumps(member["genome"], sort_keys=True))
        if any(s == sig for s in seen):
            # same verdicts: keep only the simplest, which came first
            continue
        seen.add(sig)
        out.append(member)
        if len(out) == n:
            break
    del key
    return out


def all_members(where: Path) -> list[dict[str, Any]]:
    """Every probe evaluated in any generation, best first."""
    best: dict[str, dict[str, Any]] = {}
    for path in sorted(where.glob("**/gen_*.json")):
        for member in json.loads(path.read_text())["population"]:
            best[json.dumps(member["genome"], sort_keys=True)] = member
    return sorted(
        best.values(), key=lambda m: (-m["fitness"], -m["cv_min_pr"], len(active(m["genome"])))
    )


def nested(generations: int, k: int = 5, seed: int = 7) -> None:
    """Outer k-fold: search on k-1 parts, score the winner on the part left out."""
    rows = scored_rows()
    outer = folds(rows, k, seed)
    pairs = []
    report = []
    for f, test in enumerate(outer):
        train = [r for i, r in enumerate(rows) if i not in set(test)]
        pop = evolve(train, OUT / "nested" / f"fold_{f}", generations, seed=seed + f, log=False)
        winner = pop[0]
        got = [(rows[i]["barrier"] is True, predict(rows[i], winner)) for i in test]
        pairs += got
        p, rc, tp, fp, fn = pr(got)
        report.append(
            {"fold": f, "winner": winner, "switches": active(winner), "test": [tp, fp, fn]}
        )
        print(f"fold {f}: test tp {tp} fp {fp} fn {fn} switches {active(winner)}", flush=True)
    p, rc, tp, fp, fn = pr(pairs)
    base = [(r["barrier"] is True, predict(r, base_genome())) for r in rows]
    bp, brc, btp, bfp, bfn = pr(base)
    summary = {
        "outer_folds": report,
        "pooled": {"precision": p, "recall": rc, "tp": tp, "fp": fp, "fn": fn},
        "base_946ad6f_same_files": {
            "precision": bp,
            "recall": brc,
            "tp": btp,
            "fp": bfp,
            "fn": bfn,
        },
    }
    (OUT / "nested" / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["pooled"]), json.dumps(summary["base_946ad6f_same_files"]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=[
            *("features", "search", "nested", "report", "show"),
            *("check", "simplify", "product", "fresh2"),
        ],
    )
    parser.add_argument("genome", nargs="?")
    parser.add_argument("--generations", type=int, default=60)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    if args.command == "features":
        build_features()
    elif args.command == "fresh2":
        # Information only, after FROZEN was committed: every probe of the
        # report's top 5, the base and FROZEN on the fresh2 files.
        global FILES
        FILES = ROOT / "artifacts" / "office-fresh2" / "files"
        entries = json.loads(LABELS.read_text(encoding="utf-8"))["files"]
        rows = []
        for entry in entries:
            if entry["split"] != "fresh2":
                continue
            data = (FILES / f"{entry['sha256']}.docx").read_bytes()
            row = {"id": entry["id"], "barrier": entry["barrier"]}
            try:
                row.update(file_features(data))
            except Exception as exc:  # damaged as served
                row["outcome"] = f"damaged {type(exc).__name__}"
            rows.append(row)
        (OUT / "features_fresh2.json").write_text(json.dumps(rows), encoding="utf-8")
        rows = [r for r in rows if r.get("outcome") == "checked" and r["barrier"] != "disputed"]
        probes = {"946ad6f": base_genome(), "frozen": FROZEN}
        for n, line in enumerate((OUT / "top5.txt").read_text().splitlines()[1:], start=1):
            probes[f"top{n}"] = json.loads(line)["genome"]
        out = {}
        for name, genome in probes.items():
            labels = [r["barrier"] is True for r in rows]
            preds = [predict(r, genome) for r in rows]
            p, rc, tp, fp, fn = pr(list(zip(labels, preds, strict=True)))
            out[name] = {"precision": p, "recall": rc, "tp": tp, "fp": fp, "fn": fn, "n": len(rows)}
            print(name, json.dumps(out[name]))
        (OUT / "fresh2_probes.json").write_text(json.dumps(out, indent=1))
    elif args.command == "product":
        # The frozen probe (FROZEN) must give the product's verdict on every
        # development file: reads each file again with the current office_check.
        rows = {r["id"]: r for r in scored_rows()}
        bad = []
        for entry in load_dev():
            if entry["id"] not in rows:
                continue
            data = next(FILES.glob(f"{entry['sha256']}.*")).read_bytes()
            mostly = oc.check_office(data, "docx").status == "mostly_sure"
            if mostly != predict(rows[entry["id"]], FROZEN):
                bad.append(entry["id"])
        print(len(rows), "files; frozen probe differs from the product on:", bad)
    elif args.command == "check":
        # The base genome must reproduce the product rule on every file.
        rows = json.loads((OUT / "features.json").read_text())
        bad = [
            r["id"]
            for r in rows
            if r.get("outcome") == "checked"
            and (not r["has_heading_style"])
            and (visual_headings(r["paras"], base_genome()) >= 2) != r["product_no_headings"]
        ]
        print("base genome differs from the product on:", bad)
    elif args.command == "search":
        evolve(scored_rows(), OUT / "main" / f"seed_{args.seed}", args.generations, seed=args.seed)
    elif args.command == "nested":
        nested(args.generations)
    elif args.command == "report":
        members = all_members(OUT / "main")
        fit = Fitness(scored_rows())
        print("base (946ad6f):", json.dumps(fit(base_genome())))
        for m in distinct_top(members):
            print(json.dumps({"switches": active(m["genome"]), **m}))
    elif args.command == "simplify":
        # The winner's verdicts on the development files, with each gene moved
        # as close to 946ad6f's value as those verdicts allow (greedy, in
        # GENES order): among probes the data cannot tell apart, the one
        # that changes least.
        rows = scored_rows()
        fit = Fitness(rows)
        winner = all_members(OUT / "main")[0]["genome"]
        target = [predict(r, winner) for r in rows]
        g = dict(winner)
        base = base_genome()
        for name, (values, _off) in GENES.items():
            for value in sorted(values, key=lambda v: _distance(v, base[name], values)):
                trial = {**g, name: value}
                if [predict(r, trial) for r in rows] == target:
                    g = trial
                    break
        for name, (values, _) in GENES.items():
            same = [v for v in values if [predict(r, {**g, name: v}) for r in rows] == target]
            print(f"{name:14} chosen {g[name]!s:8} same verdicts with {same}")
        print(json.dumps({"winner": winner, "simplified": g, "switches": active(g), **fit(g)}))
    elif args.command == "show":
        g = {**base_genome(), **json.loads(args.genome)}
        print(json.dumps(Fitness(scored_rows())(g)))


if __name__ == "__main__":
    main()
