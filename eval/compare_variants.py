"""Before/after comparison of explainer variants on identical recommendations.

  A  no retrieval, generic prompt      (baseline for the RAG enhancement)
  B  retrieval,    generic prompt      (RAG enhancement alone)
  C  retrieval,    VibeMatch voice     (RAG + specialization = what the app ships)

Metrics (per song line, then averaged):
  unsupported_terms  share of catalog-vocabulary words (genres, moods, vibe tags) in the line that are
                     NOT among that song's real genre/mood/tags  -> measures invented descriptors
  concrete_rate      share of lines that state at least one real fact (a true tag/genre/mood, or a number)
  words_per_line     brevity
  filler_rate        share of lines using filler words (perfect, ideal, vibe, ...)
  citations_valid    share of answers whose citations are all real retrieved docs (A cannot cite)
  coverage           share of recommended songs that the answer mentions

Usage: python eval/compare_variants.py [--delay 3]     (uses the live LLM; writes eval/comparison_report.md)
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from explainer import baseline_explain, cited_ids, explain  # noqa: E402
from llm import get_client  # noqa: E402
from nl_parser import GENRES, MOODS, TAGS, parse_request  # noqa: E402
from rag import context_for  # noqa: E402
from recommender import ARTIST_PENALTY, GENRE_PENALTY, recommend_songs  # noqa: E402
from vibematch import MIN_SCORE, VibeMatch  # noqa: E402

PROMPTS = ["high energy gym workout music", "cozy rainy-day study music, no lyrics", "i am angry and need something loud",
           "sad heartbroken songs for a rainy night", "smooth romantic jazz for a dinner date",
           "upbeat latin party music in spanish"]
VOCAB = sorted(set(GENRES + MOODS + TAGS), key=len, reverse=True)
FILLER = ("perfect", "ideal", "amazing", "awesome", "great choice", "vibe")


def song_line(text: str, song: dict) -> str | None:
    for line in text.splitlines():
        if song["title"].lower() in line.lower():
            return line
    return None


def line_metrics(line: str, song: dict) -> dict:
    clean = re.sub(r"\[[^\]]+\]", "", line)
    for name in (song["title"], song["artist"]):  # titles/artists contain words like "Neon"
        clean = re.sub(re.escape(name), " ", clean, flags=re.I)
    low = clean.lower()
    facts = {song["genre"], song["mood"], *song["mood_tags"]}
    terms = [t for t in VOCAB if re.search(rf"\b{re.escape(t)}\b", low)]
    supported = [t for t in terms if t in facts]
    return {"terms": len(terms), "unsupported": len(terms) - len(supported),
            "concrete": bool(supported) or bool(re.search(r"\d", low)),
            "words": len(low.split()), "filler": any(f in low for f in FILLER)}


def summarise(samples: list) -> dict:
    lines = [m for s in samples for m in s["lines"]]
    terms = sum(m["terms"] for m in lines)
    return {
        "answers": len(samples),
        "unsupported_terms": round(sum(m["unsupported"] for m in lines) / terms, 2) if terms else 0.0,
        "concrete_rate": round(statistics.mean(m["concrete"] for m in lines), 2) if lines else 0.0,
        "words_per_line": round(statistics.mean(m["words"] for m in lines), 1) if lines else 0.0,
        "filler_rate": round(statistics.mean(m["filler"] for m in lines), 2) if lines else 0.0,
        "citations_valid": (round(statistics.mean(s["cites_ok"] for s in samples), 2)
                            if samples and samples[0]["can_cite"] else None),
        "coverage": round(statistics.mean(s["coverage"] for s in samples), 2) if samples else 0.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()

    vm, client = VibeMatch(), get_client()
    variants = {"A: no retrieval, generic": [], "B: retrieval, generic": [], "C: retrieval + VibeMatch voice": []}
    examples, raw, skipped = {}, {}, 0
    for prompt in PROMPTS:
        prefs, src = parse_request(prompt, client)
        recs = [r for r in recommend_songs(prefs, vm.songs, k=5, artist_penalty=ARTIST_PENALTY,
                                           genre_penalty=GENRE_PENALTY) if r[1] > MIN_SCORE]
        docs = context_for(vm.retriever, prompt, [s for s, _, _ in recs])
        valid = {d.doc_id for d in docs}
        outputs = {}
        try:
            outputs["A: no retrieval, generic"] = (baseline_explain(prompt, recs, client), "llm", False)
            time.sleep(args.delay)
            for key, style in (("B: retrieval, generic", "generic"), ("C: retrieval + VibeMatch voice", "voice")):
                text, source = explain(prompt, recs, docs, client, style=style)
                outputs[key] = (text, source, True)
                time.sleep(args.delay)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {prompt!r}: {type(exc).__name__}")
            skipped += 1
            continue
        if any(not src_.startswith("llm") for _, src_, _ in outputs.values()):
            print(f"skip {prompt!r}: a variant fell back to rule-based (quota/outage), excluded for fairness")
            skipped += 1
            continue
        for key, (text, _, can_cite) in outputs.items():
            lines = [line_metrics(l, s) for s, _, _ in recs if (l := song_line(text, s))]
            cites = cited_ids(text)
            variants[key].append({"lines": lines, "can_cite": can_cite,
                                  "cites_ok": bool(cites) and all(c in valid for c in cites),
                                  "coverage": 1 - len([s for s, _, _ in recs if not song_line(text, s)]) / len(recs)})
        examples.setdefault(prompt, outputs)
        raw[prompt] = {k: text for k, (text, _, _) in outputs.items()}  # saved immediately: never lose LLM output
        (HERE / "comparison_raw.json").write_text(json.dumps(raw, indent=2))
        print(f"done {prompt!r}")
        time.sleep(args.delay)

    table = {k: summarise(v) for k, v in variants.items() if v}
    cols = ["unsupported_terms", "concrete_rate", "words_per_line", "filler_rate", "citations_valid", "coverage"]
    lines = ["# Explainer variants: before / after", "",
             f"Prompts used: {len(PROMPTS) - skipped} of {len(PROMPTS)} (skipped: {skipped}). Live LLM, same recommendations for all variants.", "",
             "| Variant | answers | " + " | ".join(cols) + " |", "|---|---|" + "---|" * len(cols)]
    for k, m in table.items():
        lines.append(f"| {k} | {m['answers']} | " + " | ".join("n/a" if m[c] is None else str(m[c]) for c in cols) + " |")
    lines += ["", "Lower is better for `unsupported_terms`, `words_per_line` and `filler_rate`; higher is better for the rest.", ""]
    if examples:
        prompt, outs = next(iter(examples.items()))
        lines += [f"## Example: `{prompt}`", ""]
        for k, (text, _, _) in outs.items():
            lines += [f"**{k}**", "", "```text", text.strip(), "```", ""]
    (HERE / "comparison_report.md").write_text("\n".join(lines) + "\n")
    (HERE / "comparison_results.json").write_text(json.dumps(table, indent=2))
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
