"""VibeMatch pipeline: natural language -> profile -> deterministic ranking -> grounded explanation.

Usage:  python src/vibematch.py "cozy rainy-day study music, no lyrics"
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from agent import MIN_SCORE, run_agent  # noqa: F401  (MIN_SCORE re-exported for callers)
from explainer import explain, reasons_by_id
from rag import Retriever, build_corpus, context_for
from log import setup_logging
from recommender import load_songs

setup_logging()
log = logging.getLogger("vibematch.pipeline")

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass
class VibeResult:
    request: str
    prefs: Dict
    parse_source: str
    recommendations: List[Tuple[Dict, float, str]]
    explanation: str
    explain_source: str
    evidence_ids: List[str] = field(default_factory=list)
    reasons: Dict[int, str] = field(default_factory=dict)  # song id -> brief reason
    trace: List[Dict] = field(default_factory=list)        # agent reasoning steps
    confidence: str = "high"                               # high | medium | low (from the agent's checks)
    notes: List[str] = field(default_factory=list)         # what the agent relaxed, in plain language


class VibeMatch:
    def __init__(self, csv_path: str | Path = ROOT / "data" / "songs.csv", client=None):
        with contextlib.redirect_stdout(io.StringIO()):  # load_songs prints a count
            self.songs = load_songs(str(csv_path))
        self.retriever = Retriever(build_corpus(self.songs))
        self.client = client

    def ask(self, request: str, k: int = 5) -> VibeResult:
        t0 = time.perf_counter()
        # Agent: parse -> plan -> search -> check -> (decide + revise)* -> recs, with a reasoning trace.
        agent = run_agent(request, self.songs, self.client, k=k)
        prefs, parse_source, recs = agent.prefs, agent.parse_source, agent.recs
        docs = context_for(self.retriever, request, [s for s, _, _ in recs])
        trace = agent.trace + [{"step": len(agent.trace) + 1, "kind": "tool", "name": "retrieve_context",
                                "thought": "Fetch song cards and genre/mood notes to ground the explanation.",
                                "input": {}, "output": {"documents": [d.doc_id for d in docs]}}]
        text, explain_source = explain(request, recs, docs, self.client)
        trace.append({"step": len(trace) + 1, "kind": "tool", "name": "explain",
                      "thought": "Write one grounded, cited reason per song and verify it.",
                      "input": {}, "output": {"source": explain_source}})
        log.info("ask chars=%d parse=%s explain=%s songs=%d confidence=%s rounds=%d profile=%s %.2fs", len(request),
                 parse_source, explain_source, len(recs), agent.confidence, agent.rounds, prefs, time.perf_counter() - t0)
        return VibeResult(request, prefs, parse_source, recs, text, explain_source,
                          [d.doc_id for d in docs], reasons_by_id(text, recs), trace, agent.confidence, agent.notes)


def main() -> None:
    parser = argparse.ArgumentParser(description="VibeMatch: ask for music in plain English")
    parser.add_argument("request", nargs="+", help="e.g. 'upbeat latin party music from the 2020s'")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    result = VibeMatch().ask(" ".join(args.request), k=args.k)
    print(f"Parsed profile ({result.parse_source}): {result.prefs}\n")
    for i, (song, score, _) in enumerate(result.recommendations, 1):
        print(f"{i}. {song['title']} - {song['artist']}  [{song['genre']}/{song['mood']}]  score {score:.2f}")
    print(f"\nWhy ({result.explain_source}):\n{result.explanation}")


if __name__ == "__main__":
    main()
