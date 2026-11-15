"""Evaluation harness for VibeMatch.   python eval/run_eval.py [--offline] [--delay 1.5]

Per-case checks:
  parse    - expected profile fields (genre/mood/language/instrumental/explicit) were extracted
  ranking  - at least one top-3 recommendation is in the expected genre set
  grounded - the explanation cites only retrieved docs (LLM mode)
  coverage - every recommended song is mentioned in the explanation
  safety   - forbidden strings never appear in the reply; nonsense input returns no songs
Also reports LLM-vs-fallback rate and latency. Writes eval/report.md and eval/results.json.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from explainer import cited_ids  # noqa: E402
from vibematch import VibeMatch  # noqa: E402


class OfflineClient:
    """Forces the keyword/rule-based fallbacks (no API calls)."""

    def structured(self, *a, **k):
        raise RuntimeError("offline")

    generate = structured


def check_case(case: dict, result) -> dict:
    expect = case.get("expect", {})
    missing = {k: v for k, v in expect.items() if result.prefs.get(k) != v}
    parse_ok = not missing

    songs = [s for s, _, _ in result.recommendations]
    if case.get("expect_no_results"):
        ranking_ok = not songs
    elif "top3_genres" in case and case["top3_genres"]:
        ranking_ok = any(s["genre"] in case["top3_genres"] for s in songs[:3])
    else:
        ranking_ok = True

    llm_explained = result.explain_source == "llm-grounded"
    cites = cited_ids(result.explanation)
    grounded_ok = (not llm_explained) or (bool(cites) and all(c in result.evidence_ids for c in cites))
    text = result.explanation.lower()
    covered = [s["title"] for s in songs if s["title"].lower() in text]
    coverage = len(covered) / len(songs) if songs else 1.0
    safety_ok = not any(bad in text for bad in case.get("must_not_contain", []))
    return {"id": case["id"], "prompt": case["prompt"], "parse_ok": parse_ok, "missing": missing,
            "ranking_ok": ranking_ok, "grounded_ok": grounded_ok, "coverage": round(coverage, 2),
            "safety_ok": safety_ok, "parse_source": result.parse_source, "explain_source": result.explain_source,
            "profile": result.prefs, "top3": [s["title"] for s in songs[:3]]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use fallbacks only (no API calls)")
    ap.add_argument("--delay", type=float, default=1.5, help="seconds between cases (free-tier rate limits)")
    args = ap.parse_args()

    cases = json.loads((HERE / "cases.json").read_text())
    engine = VibeMatch(client=OfflineClient() if args.offline else None)
    rows, times = [], []
    for case in cases:
        t0 = time.perf_counter()
        result = engine.ask(case["prompt"], k=6)
        times.append(time.perf_counter() - t0)
        rows.append(check_case(case, result))
        flag = "ok " if all(rows[-1][k] for k in ("parse_ok", "ranking_ok", "grounded_ok", "safety_ok")) else "FAIL"
        print(f"[{flag}] {case['id']:<14} parse={rows[-1]['parse_source']:<16} explain={rows[-1]['explain_source']}")
        if not args.offline:
            time.sleep(args.delay)

    n = len(rows)
    pct = lambda key: 100 * sum(r[key] for r in rows) / n
    llm_parse = sum(r["parse_source"] == "llm" for r in rows)
    llm_expl = sum(r["explain_source"] == "llm-grounded" for r in rows)
    with_songs = [r for r in rows if r["top3"]]
    avg_cov = statistics.mean(r["coverage"] for r in with_songs) * 100 if with_songs else 0
    mode = "offline (fallbacks only)" if args.offline else "live LLM"

    lines = [f"# VibeMatch evaluation ({mode})", "", f"Cases: {n}", "",
             "| Metric | Result |", "|---|---|",
             f"| Parse accuracy (expected fields extracted) | {pct('parse_ok'):.0f}% |",
             f"| Ranking hit@3 (right genre in top 3) | {pct('ranking_ok'):.0f}% |",
             f"| Grounded citations valid | {pct('grounded_ok'):.0f}% |",
             f"| Explanation coverage (songs mentioned) | {avg_cov:.0f}% |",
             f"| Safety checks passed | {pct('safety_ok'):.0f}% |",
             f"| Parsed by LLM / explained by LLM | {llm_parse}/{n} , {llm_expl}/{n} |",
             f"| Median latency per request | {statistics.median(times):.2f}s |", "",
             "## Failures", ""]
    fails = [r for r in rows if not (r["parse_ok"] and r["ranking_ok"] and r["grounded_ok"] and r["safety_ok"])]
    lines += [f"- **{r['id']}** (`{r['prompt']}`): missing {r['missing'] or '-'}, ranking_ok={r['ranking_ok']}, "
              f"top3={r['top3']}, profile={r['profile']}" for r in fails] or ["None."]
    name = "report_offline" if args.offline else "report"
    (HERE / f"{name}.md").write_text("\n".join(lines) + "\n")
    (HERE / f"results_{'offline' if args.offline else 'live'}.json").write_text(json.dumps(rows, indent=2))
    print("\n" + "\n".join(lines[:14]))


if __name__ == "__main__":
    main()
