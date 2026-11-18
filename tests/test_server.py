import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from nl_parser import ParsedRequest  # noqa: E402
from test_vibematch import FakeClient  # noqa: E402
from vibematch import VibeMatch  # noqa: E402


def make_client(**fake):
    engine = VibeMatch(client=FakeClient(**fake))
    return TestClient(server.create_app(engine))


def test_health_and_static_index():
    c = make_client(fail=True)
    assert c.get("/api/health").json() == {"status": "ok"}
    assert "VibeMatch" in c.get("/").text


def test_chat_shape_with_llm():
    c = make_client(parsed=ParsedRequest(genre="lofi", mood="chill", energy=0.35),
                    text="Great picks. [song:2]")
    r = c.post("/api/chat", json={"message": "chill lofi"})
    body = r.json()
    assert r.status_code == 200
    assert body["parse_source"] == "llm" and body["songs"]
    top = body["songs"][0]
    assert {"title", "artist", "genre", "mood", "energy", "match", "why"} <= top.keys()
    assert 0 <= top["match"] <= 100


def test_chat_fallback_without_llm():
    body = make_client(fail=True).post("/api/chat", json={"message": "aggressive metal"}).json()
    assert body["songs"][0]["genre"] == "metal"
    assert body["explain_source"] == "rule-based-fallback"


def test_unrecognised_request_gets_friendly_reply():
    body = make_client(fail=True).post("/api/chat", json={"message": "zzzz qqqq"}).json()
    assert body["songs"] == [] and "couldn't pick out" in body["reply"]


def test_validation_errors():
    c = make_client(fail=True)
    assert c.post("/api/chat", json={"message": "   "}).status_code == 422
    assert c.post("/api/chat", json={"message": "x" * 501}).status_code == 422
    assert c.post("/api/chat", json={}).status_code == 422


def test_rate_limit():
    c = make_client(fail=True)
    codes = [c.post("/api/chat", json={"message": "chill"}).status_code for _ in range(server.RATE_LIMIT + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_catalog():
    songs = make_client(fail=True).get("/api/songs").json()["songs"]
    assert len(songs) == 42 and "match" not in songs[0]


def test_chat_songs_include_brief_reason():
    songs = make_client(fail=True).post("/api/chat", json={"message": "chill lofi"}).json()["songs"]
    assert songs and all(s["reason"] and isinstance(s["why"], list) for s in songs)


def test_chat_returns_agent_steps_and_confidence():
    body = make_client(fail=True).post("/api/chat", json={"message": "instrumental heavy metal"}).json()
    assert body["confidence"] in ("high", "medium", "low")
    assert body["steps"] and {"kind", "name", "thought"} <= body["steps"][0].keys()


class EchoClient(FakeClient):
    """LLM stand-in that always produces a complete, correctly cited explanation."""

    def __init__(self, parsed):
        super().__init__(parsed=parsed)
        self.generate_calls = 0

    def generate(self, system, user):
        import re
        self.generate_calls += 1
        return "\n".join(f"{t}: Fits your request. [song:{i}]" for i, t in re.findall(r"\[song:(\d+)\] (.+?) - ", user))


def test_identical_requests_are_served_from_cache():
    client = EchoClient(ParsedRequest(genre="lofi", mood="chill"))
    c = TestClient(server.create_app(VibeMatch(client=client)))
    first = c.post("/api/chat", json={"message": "Chill   Lofi"}).json()
    second = c.post("/api/chat", json={"message": "chill lofi"}).json()   # same request, different spacing/case
    assert not first.get("cached") and second["cached"] is True
    assert client.generate_calls == 1 and second["songs"] == first["songs"]


def test_fallback_answers_are_never_cached():
    c = make_client(fail=True)
    c.post("/api/chat", json={"message": "chill lofi"})
    assert c.post("/api/chat", json={"message": "chill lofi"}).json().get("cached") is None
