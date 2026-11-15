# Explainer variants: before / after

Prompts used: 6 of 6 (skipped: 0). Live LLM, same recommendations for all variants.

| Variant | answers | unsupported_terms | concrete_rate | words_per_line | filler_rate | citations_valid | coverage |
|---|---|---|---|---|---|---|---|
| A: no retrieval, generic | 6 | 0.32 | 1 | 22.4 | 0.38 | n/a | 1.0 |
| B: retrieval, generic | 6 | 0.03 | 1 | 16.9 | 0.31 | 1 | 1.0 |
| C: retrieval + VibeMatch voice | 6 | 0.07 | 1 | 12.9 | 0 | 1 | 1.0 |

Lower is better for `unsupported_terms`, `words_per_line` and `filler_rate`; higher is better for the rest.

## Example: `high energy gym workout music`

**A: no retrieval, generic**

```text
Here are some high-energy tracks to help you crush your next workout:

1. **Block Party by Lyric Vandal:** This track brings an incredible surge of energy that is perfect for keeping your heart rate up during intense sets.
2. **Candy Static by Neon Echo:** You’ll love the driving, pumped-up rhythm of this song, which is designed to keep you moving at full speed.
3. **Highway Static by Voltline:** This track features a relentless, driving beat that will help you power through even the toughest parts of your training.
4. **Fuego Nights by Luna Cortez:** With its high-octane energy, this song is a fantastic choice for maintaining your momentum from start to finish.
5. **Neon Pulse by Circuit Bloom:** This track hits hard with an intense, pulse-pounding sound that is sure to get you feeling motivated and ready to lift.
```

**B: retrieval, generic**

```text
Here are some high-energy tracks for your workout:

* Block Party by Lyric Vandal is an energetic hip-hop track that is perfect for getting you pumped up [song:31].
* Candy Static by Neon Echo is a bright and energetic pop song that will keep you feeling good during your exercise [song:22].
* Highway Static by Voltline offers a driving rock rhythm that provides an intense, rebellious energy for your gym session [song:23].
* Fuego Nights by Luna Cortez is a fiery and energetic latin track that brings a euphoric vibe to your workout [song:20].
* Neon Pulse by Circuit Bloom is a high-energy EDM track that is sure to keep you pumped with its euphoric sound [song:17].
```

**C: retrieval + VibeMatch voice**

```text
Block Party: This energetic hip-hop track features a pumped tag and 0.89 energy. [song:31]
Candy Static: Features a pumped tag and 126 BPM to keep your workout moving. [song:22]
Highway Static: This energetic rock track has a driving tag and 140 BPM. [song:23]
Fuego Nights: An energetic latin track with 0.85 energy for your gym session. [song:20]
Neon Pulse: High 0.95 energy and a pumped tag make this track intense. [song:17]
```

