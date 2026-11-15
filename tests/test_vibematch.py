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
