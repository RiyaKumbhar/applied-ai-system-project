"""Step 2 - Retrieval for grounded explanations (the 'R' in RAG).

Corpus = (a) one 'song card' per catalog song, (b) genre notes, (c) mood notes from
data/knowledge/. Retrieval is TF-IDF + cosine similarity (scikit-learn): fully local, no
extra API key, deterministic and easy to test. The Retriever interface is tiny, so an
embedding-based retriever (e.g. sentence-transformers + Chroma) can replace it later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"


@dataclass(frozen=True)
class Document:
    doc_id: str      # e.g. "song:12", "genre:lofi", "mood:chill"
    kind: str        # song | genre | mood
    text: str


def song_card(song: Dict) -> str:
    """Describe a song in prose so it can be retrieved semantically."""
    vocals = "instrumental" if song["instrumental"] else "with vocals"
    return (
        f"{song['title']} by {song['artist']}: a {song['mood']} {song['genre']} track "
        f"from the {song['release_decade']}s, {vocals}, energy {song['energy']:.2f}, "
        f"{song['tempo_bpm']:.0f} BPM. Tags: {', '.join(song['mood_tags'])}."
    )


def _load_notes(path: Path, kind: str) -> List[Document]:
    """Parse '# heading' + body markdown into one Document per heading."""
    docs: List[Document] = []
    if not path.exists():
        return docs
    for block in re.split(r"^# ", path.read_text(encoding="utf-8"), flags=re.M):
        block = block.strip()
        if not block:
            continue
        name, _, body = block.partition("\n")
        docs.append(Document(f"{kind}:{name.strip()}", kind, f"{name.strip()}: {body.strip()}"))
    return docs


def build_corpus(songs: Sequence[Dict], knowledge_dir: Path = KNOWLEDGE_DIR) -> List[Document]:
    corpus = [Document(f"song:{s['id']}", "song", song_card(s)) for s in songs]
    corpus += _load_notes(knowledge_dir / "genres.md", "genre")
    corpus += _load_notes(knowledge_dir / "moods.md", "mood")
    return corpus


class Retriever:
    def __init__(self, corpus: Sequence[Document]):
        self.corpus = list(corpus)
        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
        self._matrix = self._vectorizer.fit_transform(d.text for d in self.corpus)

    def search(self, query: str, k: int = 4, kinds: Sequence[str] | None = None,
               min_score: float = 0.05) -> List[Document]:
        """Top-k documents by cosine similarity, optionally restricted to some kinds."""
        if not query.strip():
            return []
        sims = cosine_similarity(self._vectorizer.transform([query]), self._matrix)[0]
        ranked = sorted(range(len(self.corpus)), key=lambda i: sims[i], reverse=True)
        hits = [self.corpus[i] for i in ranked
                if sims[i] >= min_score and (kinds is None or self.corpus[i].kind in kinds)]
        return hits[:k]


def context_for(retriever: Retriever, request: str, recommended: Sequence[Dict]) -> List[Document]:
    """Evidence for explaining a result: each recommended song's own card (exact lookup),
    plus the genre/mood notes most relevant to the user's request (semantic lookup)."""
    by_id = {d.doc_id: d for d in retriever.corpus}
    docs = [by_id[f"song:{s['id']}"] for s in recommended if f"song:{s['id']}" in by_id]
    docs += retriever.search(request, k=3, kinds=("genre", "mood"))
    return docs
