"""VibeMatch web server.   Run:  uvicorn server:app --reload   then open http://localhost:8000"""

from __future__ import annotations

import logging
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from recommender import max_score
from vibematch import VibeMatch

log = logging.getLogger("vibematch.server")
WEB_DIR = Path(__file__).resolve().parent / "web"
MAX_MESSAGE_CHARS = 500
RATE_LIMIT = 20          # requests ...
RATE_WINDOW_SECONDS = 60  # ... per IP per window
CACHE_TTL_SECONDS = 3600  # identical requests are answered instantly, but only for LLM-quality answers
CACHE_MAX = 64

EMPTY_REPLY = ("I couldn't pick out a mood or genre from that. Try something like "
               "\"chill lofi for studying\" or \"upbeat latin party music\".")


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=MAX_MESSAGE_CHARS)
    k: int = Field(6, ge=1, le=12)


def song_json(song: dict, score: float = None, why: str = "", ceiling: float = 0.0, reason: str = "") -> dict:
    out = {
        "id": song["id"], "title": song["title"], "artist": song["artist"],
        "genre": song["genre"], "mood": song["mood"], "energy": song["energy"],
        "tempo": round(song["tempo_bpm"]), "decade": song["release_decade"],
        "tags": song["mood_tags"], "instrumental": song["instrumental"],
        "explicit": song["explicit"],
    }
    if score is not None:
        out["match"] = round(max(0.0, min(1.0, score / ceiling)) * 100) if ceiling else 0
        out["why"] = [r for r in why.split("; ") if r]  # score breakdown
        out["reason"] = reason  # brief human-readable reason shown on the card
    return out


def create_app(engine: VibeMatch | None = None) -> FastAPI:
    app = FastAPI(title="VibeMatch", docs_url="/api/docs", openapi_url="/api/openapi.json")
    state = {"engine": engine}
    hits: dict[str, deque] = defaultdict(deque)
    cache: dict[tuple, tuple[float, dict]] = {}

    def get_engine() -> VibeMatch:
        if state["engine"] is None:  # built lazily so importing the module stays cheap
            state["engine"] = VibeMatch()
        return state["engine"]

    def check_rate_limit(ip: str) -> None:
        now, window = time.monotonic(), hits[ip]
        while window and now - window[0] > RATE_WINDOW_SECONDS:
            window.popleft()
        if len(window) >= RATE_LIMIT:
            log.warning("rate limit hit ip=%s", ip)
            raise HTTPException(429, "Too many requests - please wait a moment.")
        window.append(now)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/songs")
    def songs():
        return {"songs": [song_json(s) for s in get_engine().songs]}

    # Plain `def` so FastAPI runs the blocking LLM calls in its threadpool.
    @app.post("/api/chat")
    def chat(body: ChatRequest, request: Request):
        check_rate_limit(request.client.host if request.client else "unknown")
        message = body.message.strip()
        if not message:
            raise HTTPException(422, "Message is empty.")
        key = (" ".join(message.lower().split()), body.k)
        hit = cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_TTL_SECONDS:
            log.info("cache hit chars=%d", len(message))
            return {**hit[1], "cached": True}
        result = get_engine().ask(message, k=body.k)
        if not result.recommendations:
            return {"reply": EMPTY_REPLY, "profile": result.prefs, "songs": [],
                    "parse_source": result.parse_source, "explain_source": result.explain_source}
        ceiling = max_score(result.prefs)
        response = {
            "reply": result.explanation,
            "profile": result.prefs,
            "songs": [song_json(s, sc, why, ceiling, result.reasons.get(s["id"], "")) for s, sc, why in result.recommendations],
            "parse_source": result.parse_source,
            "explain_source": result.explain_source,
            "confidence": result.confidence,
            "notes": result.notes,
            "steps": [{"kind": t["kind"], "name": t["name"], "thought": t["thought"]} for t in result.trace],
        }
        if result.parse_source == "llm" and result.explain_source == "llm-grounded":
            if len(cache) >= CACHE_MAX:
                cache.pop(next(iter(cache)))  # drop the oldest entry
            cache[key] = (time.monotonic(), response)
        return response

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):  # never leak internals to the browser
        log.exception("unhandled error on %s", _.url.path)
        return JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
