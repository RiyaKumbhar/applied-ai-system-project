"""Streamlit UI:  streamlit run app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st

from vibematch import VibeMatch


@st.cache_resource
def get_engine() -> VibeMatch:
    return VibeMatch()


st.title("VibeMatch")
st.caption("Describe the music you want in plain English.")
request = st.text_input("Your request", placeholder="cozy rainy-day study music, no lyrics")
if request:
    result = get_engine().ask(request)
    st.subheader("Understood as")
    st.json(result.prefs)
    st.caption(f"parser: {result.parse_source}")
    st.subheader("Recommendations")
    for i, (song, score, _) in enumerate(result.recommendations, 1):
        st.write(f"**{i}. {song['title']}** - {song['artist']}  ({song['genre']}, {song['mood']})  `score {score:.2f}`")
    st.subheader("Why")
    st.write(result.explanation)
    st.caption(f"explainer: {result.explain_source} | evidence: {', '.join(result.evidence_ids)}")
