import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import MAX_ROUNDS, Revision, check_playlist, default_revision, hard_constraints, run_agent, search_songs, violations  # noqa: E402
from nl_parser import ParsedRequest  # noqa: E402
from test_vibematch import FakeClient  # noqa: E402
from vibematch import VibeMatch  # noqa: E402

SONGS = VibeMatch(client=FakeClient(fail=True)).songs
OFFLINE = FakeClient(fail=True)


class DecidingClient(FakeClient):
    """parse -> ParsedRequest; decide -> the given Revision (dispatch on the schema asked for)."""

    def __init__(self, parsed, revision):
        super().__init__(parsed=parsed)
        self.revision, self.decide_calls = revision, 0

    def structured(self, system, user, schema):
        if schema is Revision:
            self.decide_calls += 1
            return self.revision
        return self.parsed


def names(result):
    return [s["name"] for s in result.trace]


def test_ordinary_request_needs_no_revision_and_is_high_confidence():
    r = run_agent("aggressive heavy metal", SONGS, OFFLINE)
    assert r.rounds == 0 and r.confidence == "high"
    assert names(r)[:3] == ["parse_request", "plan", "search_songs"] and "decide_revision" not in names(r)


def test_trace_steps_are_numbered_and_complete():
    r = run_agent("instrumental heavy metal", SONGS, OFFLINE)
    assert [s["step"] for s in r.trace] == list(range(1, len(r.trace) + 1))
    assert all({"kind", "name", "thought", "input", "output"} <= s.keys() for s in r.trace)
    assert r.trace[-1]["name"] == "finish"


def test_constraint_violation_is_detected_then_filtered():
    prefs = {"genre": "metal", "instrumental": True}
    recs = search_songs(SONGS, prefs, 5)
    check = check_playlist(prefs, recs, 5)
    assert not check["passed"] and check["issues"][0]["type"] == "constraint_violation"
    r = run_agent("instrumental heavy metal", SONGS, OFFLINE)
    hard = hard_constraints(r.prefs)
    assert hard == {"instrumental": True}
    assert all(not violations(s, hard) for s, _, _ in r.recs)       # final list keeps the promise
    assert "decide_revision" in names(r) and r.confidence in ("medium", "high")


def test_revision_never_empties_results():
    r = run_agent("i am angry", SONGS, OFFLINE)   # only one matching song in the catalog
    assert len(r.recs) >= 1 and r.confidence == "low"


def test_empty_profile_returns_no_songs_without_searching():
    r = run_agent("zzzz qqqq", SONGS, OFFLINE)
    assert r.recs == [] and "search_songs" not in names(r)


def test_default_policy_choices():
    bad = {"issues": [{"type": "constraint_violation"}]}
    assert default_revision({"genre": "metal", "instrumental": True}, bad).action == "filter_violations"
    weak = {"issues": [{"type": "weak_match"}]}
    rev = default_revision({"genre": "metal", "mood": "angry"}, weak)
    assert rev.action == "broaden" and rev.drop_field == "genre"
    assert default_revision({"mood": "angry"}, weak).action == "accept"   # never drop the only preference


def test_valid_llm_decision_is_used():
    client = DecidingClient(ParsedRequest(genre="metal", instrumental=True),
                            Revision(thought="Filter them.", action="filter_violations"))
    r = run_agent("instrumental heavy metal", SONGS, client)
    assert client.decide_calls >= 1
    decided = [s for s in r.trace if s["name"] == "decide_revision"][0]
    assert decided["output"]["decided_by"] == "llm" and decided["thought"] == "Filter them."


def test_invalid_llm_decision_falls_back_to_default_policy():
    bad = Revision(thought="Drop a field that is not there.", action="broaden", drop_field="decade")
    client = DecidingClient(ParsedRequest(genre="metal", instrumental=True), bad)
    r = run_agent("instrumental heavy metal", SONGS, client)
    decided = [s for s in r.trace if s["name"] == "decide_revision"][0]
    assert decided["output"]["decided_by"] == "default-policy"


def test_loop_is_bounded():
    r = run_agent("instrumental heavy metal", SONGS, OFFLINE)
    assert r.rounds <= MAX_ROUNDS


def test_pipeline_exposes_trace_and_confidence():
    result = VibeMatch(client=OFFLINE).ask("instrumental heavy metal")
    assert result.confidence in ("high", "medium", "low")
    assert names_of(result)[-2:] == ["retrieve_context", "explain"]


def names_of(result):
    return [s["name"] for s in result.trace]


def test_user_gets_a_note_when_the_agent_relaxes_something():
    r = run_agent("instrumental heavy metal", SONGS, OFFLINE)
    assert r.notes and any("Left out" in n or "Relaxed" in n for n in r.notes)
    assert run_agent("aggressive heavy metal", SONGS, OFFLINE).notes == []
