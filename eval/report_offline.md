# VibeMatch evaluation (offline (fallbacks only))

Cases: 17

| Metric | Result |
|---|---|
| Parse accuracy (expected fields extracted) | 88% |
| Ranking hit@3 (right genre in top 3) | 100% |
| Grounded citations valid | 100% |
| Explanation coverage (songs mentioned) | 100% |
| Safety checks passed | 100% |
| Parsed by LLM / explained by LLM | 0/17 , 0/17 |
| Median latency per request | 0.00s |

## Failures

- **gym** (`high energy gym workout music`): missing {'mood': 'energetic'}, ranking_ok=True, top3=['Fuego Nights', 'Highway Static', 'Neon Alley'], profile={'energy': 0.85}
- **latin_party** (`upbeat latin party music in spanish`): missing {'language': 'es'}, ranking_ok=True, top3=['Fuego Nights', 'Verano Eterno', 'Block Party'], profile={'genre': 'latin', 'energy': 0.85, 'tags': ['party']}
