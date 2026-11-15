import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from explainer import cited_ids, explain  # noqa: E402
from nl_parser import ParsedRequest, keyword_parse, parse_request, validate_profile  # noqa: E402
from vibematch import VibeMatch  # noqa: E402


class FakeClient:
    """Stands in for anthropic.Anthropic: parse() returns a ParsedRequest, create() returns text."""

    def __init__(self, parsed=None, text="", fail=False):
        self.parsed, self.text, self.fail = parsed, text, fail
        self.messages = self

    def parse(self, **kwargs):
        if self.fail:
            raise RuntimeError("api down")
        return SimpleNamespace(stop_reason="end_turn", parsed_output=self.parsed)

    def create(self, **kwargs):
        if self.fail:
            raise RuntimeError("api down")
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.text)])


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
    good = FakeClient(text=f"Nice. [{docs[0].doc_id}]")
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
