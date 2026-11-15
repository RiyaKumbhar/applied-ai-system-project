import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from explainer import cited_ids, explain  # noqa: E402
from nl_parser import ParsedRequest, keyword_parse, parse_request, validate_profile  # noqa: E402
from vibematch import VibeMatch  # noqa: E402


class FakeClient:
    """Stands in for an llm.py backend."""

    def __init__(self, parsed=None, text="", fail=False):
        self.parsed, self.text, self.fail = parsed, text, fail

    def structured(self, system, user, schema):
        if self.fail:
            raise RuntimeError("api down")
        return self.parsed

    def generate(self, system, user):
        if self.fail:
            raise RuntimeError("api down")
        return self.text


def test_validate_drops_out_of_vocabulary_and_clamps():
    p = ParsedRequest(genre="vaporwave", mood="Chill", energy=3.0, tags=["cozy", "bogus"], explicit=True)
    prefs = validate_profile(p)
    assert prefs == {"mood": "chill", "energy": 1.0, "tags": ["cozy"]}  # explicit=True never inferred


def test_parse_uses_llm_result():
    client = FakeClient(parsed=ParsedRequest(genre="lofi", mood="focused", energy=0.35, instrumental=True))
    prefs, source = parse_request("quiet study music", client)
    assert source == "llm" and prefs["genre"] == "lofi" and prefs["instrumental"] is True


def test_parse_falls_back_when_api_fails():
    prefs, source = parse_request("chill lofi for studying, no lyrics", FakeClient(fail=True))
    assert source == "keyword-fallback" and prefs["genre"] == "lofi" and prefs["instrumental"] is True


def test_empty_and_long_input():
    assert parse_request("   ")[0] == {}
    assert keyword_parse("x" * 10000) == {}


def test_explainer_requires_valid_citations():
    vm = VibeMatch(client=FakeClient(fail=True))
    recs = vm.ask("chill lofi study").recommendations
    docs = [vm.retriever.corpus[0]]
    names = " ".join(f"{song['title']}." for song, _, _ in recs)
    good = FakeClient(text=f"{names} [{docs[0].doc_id}]")
    assert explain("q", recs, docs, good)[1] == "llm-grounded"
    assert explain("q", recs, docs, FakeClient(text="Nice. [song:99999]"))[1] == "rule-based-fallback"
    assert explain("q", recs, docs, FakeClient(text="No citation"))[1] == "rule-based-fallback"


def test_cited_ids():
    assert cited_ids("a [song:12] b [genre:indie pop] c [mood:chill]") == ["song:12", "genre:indie pop", "mood:chill"]


def test_end_to_end_with_fallbacks_only():
    result = VibeMatch(client=FakeClient(fail=True)).ask("aggressive metal, intense")
    assert result.recommendations and result.recommendations[0][0]["genre"] == "metal"
    assert result.parse_source == "keyword-fallback" and result.explain_source == "rule-based-fallback"


def test_retrieval_finds_relevant_genre_note():
    vm = VibeMatch(client=FakeClient(fail=True))
    ids = [d.doc_id for d in vm.retriever.search("dusty mellow beats for studying", k=3, kinds=("genre",))]
    assert "genre:lofi" in ids


def test_zero_score_songs_are_dropped():
    result = VibeMatch(client=FakeClient(fail=True)).ask("i am angry", k=12)
    assert result.recommendations
    assert all(score > 0.05 for _, score, _ in result.recommendations)


class SeqClient(FakeClient):
    """generate() returns successive texts, to test the retry-on-incomplete path."""

    def __init__(self, texts):
        super().__init__()
        self.texts, self.calls = list(texts), 0

    def generate(self, system, user):
        self.calls += 1
        return self.texts.pop(0)


def _two_recs():
    vm = VibeMatch(client=FakeClient(fail=True))
    recs = vm.ask("chill lofi study", k=2).recommendations
    return vm, recs


def test_incomplete_explanation_is_retried_then_complete():
    vm, recs = _two_recs()
    (a, _, _), (b, _, _) = recs
    docs = vm.retriever.corpus
    client = SeqClient([f"{a['title']} fits. [song:{a['id']}]",
                        f"{a['title']} fits. [song:{a['id']}] {b['title']} too. [song:{b['id']}]"])
    text, source = explain("q", recs, docs, client)
    assert source == "llm-grounded" and client.calls == 2 and b["title"] in text


def test_still_incomplete_is_patched_with_rule_based_line():
    vm, recs = _two_recs()
    (a, _, _), (b, _, _) = recs
    only_a = f"{a['title']} fits. [song:{a['id']}]"
    text, source = explain("q", recs, vm.retriever.corpus, SeqClient([only_a, only_a]))
    assert source == "llm-partial" and b["title"] in text


def test_brief_fallback_is_short_and_skips_penalties():
    from explainer import brief_fallback
    out = brief_fallback("genre match: lofi (+2.0); mood match: chill (+1.0); "
                         "energy 0.42 is 0.07 from target 0.35 (+1.4); diversity penalty: lofi already in list (-0.50)")
    assert out == "Matches your request: lofi genre, chill mood, energy close to your target."


def test_reasons_by_id_parses_lines_and_fills_gaps():
    from explainer import reasons_by_id
    vm, recs = _two_recs()
    (a, _, _), (b, _, _) = recs
    text = f"{a['title']}: Slow and instrumental, great for focus. [song:{a['id']}]"
    reasons = reasons_by_id(text, recs)
    assert reasons[a["id"]] == "Slow and instrumental, great for focus."  # title prefix and citation stripped
    assert reasons[b["id"]].startswith("Matches your request")            # missing song gets a rule-based reason
    assert set(reasons) == {a["id"], b["id"]}


def test_voice_style_is_default_and_generic_is_available():
    from explainer import GENERIC_PROMPT, STYLES, VOICE_PROMPT
    assert STYLES["voice"] is VOICE_PROMPT and STYLES["generic"] is GENERIC_PROMPT
    vm, recs = _two_recs()
    names = " ".join(f"{s['title']}." for s, _, _ in recs)
    text, source = explain("q", recs, vm.retriever.corpus, FakeClient(text=f"{names} [song:{recs[0][0]['id']}]"),
                           style="generic")
    assert source == "llm-grounded"


def test_every_result_song_has_a_reason():
    result = VibeMatch(client=FakeClient(fail=True)).ask("aggressive metal")
    assert result.recommendations and all(result.reasons[s["id"]] for s, _, _ in result.recommendations)


def test_wrong_citation_id_is_repaired_and_reason_goes_to_right_song():
    from explainer import reasons_by_id, repair_attribution
    vm, recs = _two_recs()
    (a, _, _), (b, _, _) = recs
    # model cites b's id on a's line (a real id, but the wrong song)
    text = (f"{a['title']}: Calm and instrumental. [song:{b['id']}]\n"
            f"{b['title']}: Cozy study tags match. [song:{b['id']}]")
    fixed_text, n = repair_attribution(text, recs)
    assert n == 1 and f"[song:{a['id']}]" in fixed_text.splitlines()[0]
    reasons = reasons_by_id(text, recs)  # even unrepaired, titles decide
    assert reasons[a["id"]] == "Calm and instrumental." and reasons[b["id"]] == "Cozy study tags match."
