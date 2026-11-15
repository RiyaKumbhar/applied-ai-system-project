"""VibeMatch pipeline: natural language -> profile -> deterministic ranking -> grounded explanation.

Usage:  python src/vibematch.py "cozy rainy-day study music, no lyrics"
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

from explainer import explain
from nl_parser import parse_request
from rag import Retriever, build_corpus, context_for
from recommender import ARTIST_PENALTY, GENRE_PENALTY, load_songs, recommend_songs

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


class VibeMatch:
    def __init__(self, csv_path: str | Path = ROOT / "data" / "songs.csv", client=None):
        with contextlib.redirect_stdout(io.StringIO()):  # load_songs prints a count
            self.songs = load_songs(str(csv_path))
        self.retriever = Retriever(build_corpus(self.songs))
        self.client = client

    def ask(self, request: str, k: int = 5) -> VibeResult:
        prefs, parse_source = parse_request(request, self.client)
        recs = recommend_songs(prefs, self.songs, k=k,
                               artist_penalty=ARTIST_PENALTY, genre_penalty=GENRE_PENALTY) if prefs else []
        docs = context_for(self.retriever, request, [s for s, _, _ in recs])
        text, explain_source = explain(request, recs, docs, self.client)
        return VibeResult(request, prefs, parse_source, recs, text, explain_source, [d.doc_id for d in docs])


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
