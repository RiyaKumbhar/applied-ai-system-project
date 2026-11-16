# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agentic Workflow (SF8)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

### Challenge 1: Add advanced song features

**What task did you give the agent?**

Add 5 or more new song attributes to `data/songs.csv`, and update the scoring in `src/recommender.py` so the new attributes count. Keep the existing profiles working.

**Prompts used:**

"Introduce 5 or more complex attributes to your dataset that are not currently present in the baseline data, such as Song Popularity (0-100), Release Decade, or Detailed Mood Tags (e.g., 'nostalgic,' 'aggressive,' 'euphoric'). Update both `data/songs.csv` and the scoring logic in `src/recommender.py` so scoring accounts for the new attributes. In `ai_interactions.md`, document the agentic workflow: the example prompt(s) you used, a summary of the changes the AI generated, and your manual verification notes."

**What did the agent generate or change?**

- `data/songs.csv`: added six columns to all 42 songs: `popularity` (0-100), `release_decade`, `mood_tags` (three tags per song, separated by `|`), `language`, `explicit` and `instrumental`. The original ten columns were not touched.
- `src/recommender.py`:
  - `Song` has six new fields, all with defaults, so the existing tests still work.
  - `load_songs` converts the new columns: ints, bools and the tag list.
  - `score_song` has six new scoring rules (below). Each one only runs if the user profile asks for that feature.
  - New `max_score(user_prefs)` works out the best possible score for the features a profile asked for.
- `src/main.py`: five new profiles (`ADVANCED_PROFILES`) and the printed "/ max" now comes from `max_score`.

| New feature | How it scores | Max points |
|---|---|---|
| `tags` (list of wanted mood tags) | share of wanted tags the song has | 1.0 |
| `decade` | full points for the same decade, loses one third per decade apart | 0.5 |
| `popularity` (0-100) | closeness to the target | 0.5 |
| `language` | exact match | 0.5 |
| `instrumental` (True/False) | match | 0.5 |
| `explicit` (True/False) | match | 0.5 |

**What did you verify or fix manually?**

- **Old behavior unchanged.** I saved the output of the nine earlier profiles before the change and diffed it afterward. All songs, scores and rankings are identical. The only difference is the Empty Profile: it now prints `/ 0.00` instead of `/ 4.50`. That is correct under the new rule, since an empty profile asks for no features.
- **Data checks.** 42 rows, 16 columns, no blank cells. Popularity runs 30–90. Decades run 1960–2020. Every song has exactly 3 tags (48 distinct tags). The original ten columns match the old file exactly.
- **Hand-checked one score.** *Fuego Nights* for "Mainstream Latin Party" should be 2.0 (genre) + 1.0 (mood) + 1.5 (energy, exact) + 1.0 (both tags) + 0.5 (decade) + 0.5 (popularity, exact) + 0.5 (language) = 7.0. The program printed 7.00 / 7.00.
- **Tests.** `pytest` passes (2 passed).
- **Important caveat.** The new values (popularity, decade, tags, language, explicit, instrumental) were written by the AI. They are made up to be plausible. They are not real chart data and I did not look them up. The songs are fictional, so they could not be looked up anyway.
- **A weakness I found by reading the results.** The "Clean Gym Playlist (no explicit)" profile still ranks *Block Party* first, and it is explicit. Genre, mood and tag points (about 4.5) easily beat the 0.5 "clean" bonus. So `explicit` acts as a nudge, not a filter. If a user really wants no explicit songs, it should be a hard filter. I did not change this; it is listed under future work in the model card.
- **A smaller oddity.** In "Retro Jazz Purist", *Study Hall Static* is the #5 result only because it is instrumental and has a close energy. It is not jazz. The scorer rewards weak matches when the list runs out of real ones.

---

## Challenge 3: Diversity penalty

**Prompt used:**

"Add a diversity penalty to `recommend_songs`. If a candidate song's artist is already in the top recommendations list, subtract points from its score. Do the same, with a smaller penalty, for a repeated genre. The first pick must not change, each penalty must appear in the song's reasons, and the default behavior must stay the same."

**What the AI proposed and generated:**

- First it checked the data: Chill Lofi returned LoRoom three times and lofi five times, so the problem was real.
- **Option A:** drop duplicates after sorting. Simple, but it throws songs away and loses the score explanation.
- **Option B (chosen):** pick songs one at a time and re-score the rest each round, so a song loses 1.0 point per song by the same artist already picked and 0.5 per song of the same genre. This is the same idea as MMR re-ranking.
- Changes: `recommend_songs()` in `src/recommender.py` has new `artist_penalty` and `genre_penalty` arguments (both 0 by default); `--diverse` in `src/main.py`; three new tests in `tests/test_recommender.py`.

**What I verified manually:**

- Default output is identical to before (diffed against the saved run).
- Hand-checked: Midnight Coding scored 4.39 and shows 3.89 after the 0.50 lofi penalty.
- I ran all 14 profiles: the #1 song never changed, and distinct artists in the top 5 went up in every profile that had repeats (Chill Lofi: 2 → 5).
- My first test failed because my penalty (2.0) was too small. The numbers were my mistake, not a code bug. I changed the test to 3.0.
- **Trade-off:** a lofi fan now gets only 2 lofi songs of 5. The penalty sizes are my guesses and I have not tuned them.

---

## Challenge 4: Visual summary table

**Prompt used:**

"Suggest a way to use a library like `tabulate` or simple ASCII formatting to display the top recommendations as a table. The table must include the reasons for each score."

**What the AI proposed and generated:**

- It suggested two ways: `tabulate`, or plain ASCII. It checked first: `tabulate` is not installed and not in `requirements.txt`. So I chose plain ASCII with the standard library. No new dependency.
- New file `src/report.py` has `format_table()`. Columns: rank, title, artist, genre, score out of the max, and a "Why (reasons)" column. Each reason is on its own line, and long reasons wrap.
- `--format table` in `src/main.py` switches to it. The default output is unchanged.

**What I verified manually:**

- Every row of every table has the same width (a test checks this).
- A test checks that genre, mood and energy reasons all appear in the table.
- All flag combinations work together (`--mode`, `--diverse`, `--format`, `--compare`).
- The empty profile shows "(no preferences given)" instead of a blank cell.
- Limit: long titles and artist names wrap onto several lines. Very wide terminals are fine, but the table is about 115 characters wide, so it may wrap in a narrow window.

---

## Design Pattern (SF10)

> Document how AI helped you choose or implement a design pattern.

**Which design pattern did you use?**

A simple **Strategy pattern**. A `RankingStrategy` object holds the weights for one ranking mode. `score_song()` and `recommend_songs()` take a strategy as an argument. Three modes exist: **Genre-First** (genre 2.0, mood 1.0, energy 1.5, the original recipe), **Mood-First** (genre 1.0, mood 2.5, energy 1.5) and **Energy-Focused** (genre 0.5, mood 0.5, energy 3.0). You switch with `python3 src/main.py --mode mood-first`, or compare all three with `--compare`.

**Prompt used:**

"Build two or more different ranking strategies (e.g., 'Genre-First,' 'Mood-First,' or 'Energy-Focused') so a user can switch between modes in main.py. Attach recommender.py and brainstorm a design pattern (like a simple 'Strategy' pattern) that keeps your code modular."

**How did AI help you brainstorm or implement it?**

The AI read `recommender.py` and laid out four options before writing any code:

1. **An `if mode == ...` flag inside `score_song`.** Quickest, but every new mode adds more branches to one function. Rejected.
2. **One class per strategy** with a `score()` method (the textbook Strategy pattern). Flexible, but our modes differ only in their numbers. Three near-identical classes would be boilerplate. Rejected for now.
3. **A dict of scoring functions.** Light, but the weights would be buried inside each function and hard to compare.
4. **A frozen dataclass of weights plus a registry dict.** This is what I picked. Modes become data, so a new mode is one new line in `STRATEGIES`. The scoring code stays in one place, and a reader can see all weights side by side.

The AI wrote the first version of the dataclass, the registry and the `--mode` / `--compare` flags. I made the final choice of option 4 and the weight values.

**How does the pattern appear in your final code?**

- `RankingStrategy` and `STRATEGIES` in `src/recommender.py`. `score_song(user_prefs, song, strategy)` and `recommend_songs(..., strategy)` use whatever strategy they are given. The default is `GENRE_FIRST`, so older calls still work.
- `show_ranking()`, `compare_modes()` and the `--mode` / `--compare` flags in `src/main.py`.

**What did you verify or fix manually?**

- **Branch workflow.** I built this on `experiment/mood-first`, so `main` stayed untouched until it worked. I merged it back once it did.
- **Old behavior unchanged.** The default mode (`genre-first`) prints exactly the same output as before the refactor, except for a new "Mode:" line. I diffed the two runs.
- **Hand-checked one score.** Mood-First, *Sunrise City* for High-Energy Pop: 1.0 (genre) + 2.5 (mood) + 1.38 (energy) = 4.88 / 5.00. The program printed 4.88.
- **Bad input.** `--mode bogus` gives a clear error that lists the valid modes. `pytest` still passes (2 passed).
- **A limit of this pattern.** These strategies differ only in numbers. If I wanted a mode that works differently, such as a hard filter that removes explicit songs, the dataclass would not be enough. That would need a class or a function per strategy.

---

<!-- agent-traces:start -->

## Applied AI project: VibeMatch agent reasoning traces

The agent ([src/agent.py](src/agent.py)) runs plan, act (tools), check, decide, revise. The LLM never ranks songs: it parses the request and, only when a check fails, chooses one revision from a fixed menu (`filter_violations`, `broaden`, `accept`). If the LLM is unavailable a deterministic policy makes the same choice. Machine-readable log: [docs/agent_traces.json](docs/agent_traces.json). Regenerate with `python eval/agent_demo.py`.

### Request: "instrumental heavy metal"

Result: 5 songs, confidence **medium**, explanation source `llm-grounded`, 93.3s.

| # | Kind | Step | Reasoning | Output |
|---|---|---|---|---|
| 1 | tool | `parse_request` | Turn the free-text request into a structured profile. | `{"profile": {"genre": "metal", "instrumental": true}, "source": "llm"}` |
| 2 | plan | `plan` | Treat instrumental/clean/language as hard constraints and the rest as soft preferences. | `{"hard_constraints": {"instrumental": true}, "soft_preferences": {"genre": "metal"}}` |
| 3 | tool | `search_songs` | Rank the catalog with the deterministic scorer. | `{"top": ["Iron Requiem", "Midnight Coding", "Spacewalk Thoughts", "Night Drive Loop", "Quiet Cathedral"]}` |
| 4 | check | `check_playlist` | Verify hard constraints, result count and match quality. | `{"passed": false, "issues": [{"type": "constraint_violation", "constraints": {"instrumental": true}, "titles": ["Iron Requiem"]}]}` |
| 5 | decision | `decide_revision` | The song Iron Requiem was flagged for violating the instrumental constraint, so I must filter the results to ensure only instrumental tracks remain. | `{"action": "filter_violations", "drop_field": null, "decided_by": "llm"}` |
| 6 | tool | `apply_revision` | Applied 'filter_violations' and re-searched. | `{"profile": {"genre": "metal", "instrumental": true}, "top": ["Midnight Coding", "Spacewalk Thoughts", "Night Drive Loop", "Quiet Cathedral", "Blue Note Lounge"]}` |
| 7 | check | `check_playlist` | Re-check after the revision. | `{"passed": false, "issues": [{"type": "weak_match", "best_ratio": 0.2}]}` |
| 8 | decision | `decide_revision` | Too few or weak matches, so drop the 'genre' preference. | `{"action": "broaden", "drop_field": "genre", "decided_by": "default-policy"}` |
| 9 | tool | `apply_revision` | Applied 'broaden' (drop genre) and re-searched. | `{"profile": {"instrumental": true}, "top": ["Midnight Coding", "Spacewalk Thoughts", "Night Drive Loop", "Quiet Cathedral", "Blue Note Lounge"]}` |
| 10 | check | `check_playlist` | Re-check after the revision. | `{"passed": true, "issues": []}` |
| 11 | result | `finish` | Finished after 2 revision(s) with medium confidence. | `{"rounds": 2, "confidence": "medium", "songs": 5}` |
| 12 | tool | `retrieve_context` | Fetch song cards and genre/mood notes to ground the explanation. | `{"documents": ["song:2", "song:6", "song:8", "song:12", "song:29", "genre:metal", "mood:intense", "mood:angry"]}` |
| 13 | tool | `explain` | Write one grounded, cited reason per song and verify it. | `{"source": "llm-grounded"}` |

Final songs: Midnight Coding (lofi, instrumental=True, explicit=False); Spacewalk Thoughts (ambient, instrumental=True, explicit=False); Night Drive Loop (synthwave, instrumental=True, explicit=False); Quiet Cathedral (classical, instrumental=True, explicit=False); Blue Note Lounge (jazz, instrumental=True, explicit=False)

### Request: "clean explicit-free hip-hop for the gym"

Result: 5 songs, confidence **medium**, explanation source `llm-grounded`, 4.4s.

| # | Kind | Step | Reasoning | Output |
|---|---|---|---|---|
| 1 | tool | `parse_request` | Turn the free-text request into a structured profile. | `{"profile": {"genre": "hip-hop", "tags": ["pumped", "motivational"], "explicit": false}, "source": "llm"}` |
| 2 | plan | `plan` | Treat instrumental/clean/language as hard constraints and the rest as soft preferences. | `{"hard_constraints": {"explicit": false}, "soft_preferences": {"genre": "hip-hop", "tags": ["pumped", "motivational"]}}` |
| 3 | tool | `search_songs` | Rank the catalog with the deterministic scorer. | `{"top": ["Block Party", "Gym Hero", "Neon Pulse", "Midnight Coding", "Storm Runner"]}` |
| 4 | check | `check_playlist` | Verify hard constraints, result count and match quality. | `{"passed": false, "issues": [{"type": "constraint_violation", "constraints": {"explicit": false}, "titles": ["Block Party"]}]}` |
| 5 | decision | `decide_revision` | The song 'Block Party' violates the explicit-free constraint, so it must be removed and replaced with a clean alternative. | `{"action": "filter_violations", "drop_field": null, "decided_by": "llm"}` |
| 6 | tool | `apply_revision` | Applied 'filter_violations' and re-searched. | `{"profile": {"genre": "hip-hop", "tags": ["pumped", "motivational"], "explicit": false}, "top": ["Gym Hero", "Neon Pulse", "Midnight Coding", "Storm Runner", "Spacewal...` |
| 7 | check | `check_playlist` | Re-check after the revision. | `{"passed": true, "issues": []}` |
| 8 | result | `finish` | Finished after 1 revision(s) with medium confidence. | `{"rounds": 1, "confidence": "medium", "songs": 5}` |
| 9 | tool | `retrieve_context` | Fetch song cards and genre/mood notes to ground the explanation. | `{"documents": ["song:5", "song:17", "song:2", "song:3", "song:6", "mood:confident", "genre:hip-hop"]}` |
| 10 | tool | `explain` | Write one grounded, cited reason per song and verify it. | `{"source": "llm-grounded"}` |

Final songs: Gym Hero (pop, instrumental=False, explicit=False); Neon Pulse (edm, instrumental=False, explicit=False); Midnight Coding (lofi, instrumental=True, explicit=False); Storm Runner (rock, instrumental=False, explicit=False); Spacewalk Thoughts (ambient, instrumental=True, explicit=False)

### Request: "romantic jazz instrumental from the 1960s"

Result: 5 songs, confidence **medium**, explanation source `llm-grounded`, 4.0s.

| # | Kind | Step | Reasoning | Output |
|---|---|---|---|---|
| 1 | tool | `parse_request` | Turn the free-text request into a structured profile. | `{"profile": {"genre": "jazz", "mood": "romantic", "tags": ["romantic"], "decade": 1960, "instrumental": true}, "source": "llm"}` |
| 2 | plan | `plan` | Treat instrumental/clean/language as hard constraints and the rest as soft preferences. | `{"hard_constraints": {"instrumental": true}, "soft_preferences": {"genre": "jazz", "mood": "romantic", "tags": ["romantic"], "decade": 1960}}` |
| 3 | tool | `search_songs` | Rank the catalog with the deterministic scorer. | `{"top": ["Blue Note Lounge", "Late Night Bebop", "Velvet Hours", "Midnight Coding", "Spacewalk Thoughts"]}` |
| 4 | check | `check_playlist` | Verify hard constraints, result count and match quality. | `{"passed": false, "issues": [{"type": "constraint_violation", "constraints": {"instrumental": true}, "titles": ["Velvet Hours"]}]}` |
| 5 | decision | `decide_revision` | The song Velvet Hours was flagged for violating the instrumental constraint, so I must filter it out and find a replacement that strictly adheres to the user's requirements. | `{"action": "filter_violations", "drop_field": null, "decided_by": "llm"}` |
| 6 | tool | `apply_revision` | Applied 'filter_violations' and re-searched. | `{"profile": {"genre": "jazz", "mood": "romantic", "tags": ["romantic"], "decade": 1960, "instrumental": true}, "top": ["Blue Note Lounge", "Late Night Bebop", "Midnigh...` |
| 7 | check | `check_playlist` | Re-check after the revision. | `{"passed": true, "issues": []}` |
| 8 | result | `finish` | Finished after 1 revision(s) with medium confidence. | `{"rounds": 1, "confidence": "medium", "songs": 5}` |
| 9 | tool | `retrieve_context` | Fetch song cards and genre/mood notes to ground the explanation. | `{"documents": ["song:29", "song:30", "song:2", "song:6", "song:8", "mood:romantic", "genre:jazz", "mood:chill"]}` |
| 10 | tool | `explain` | Write one grounded, cited reason per song and verify it. | `{"source": "llm-grounded"}` |

Final songs: Blue Note Lounge (jazz, instrumental=True, explicit=False); Late Night Bebop (jazz, instrumental=True, explicit=False); Midnight Coding (lofi, instrumental=True, explicit=False); Spacewalk Thoughts (ambient, instrumental=True, explicit=False); Night Drive Loop (synthwave, instrumental=True, explicit=False)

### Request: "i am angry"

Result: 4 songs, confidence **high**, explanation source `llm-grounded`, 2.1s.

| # | Kind | Step | Reasoning | Output |
|---|---|---|---|---|
| 1 | tool | `parse_request` | Turn the free-text request into a structured profile. | `{"profile": {"mood": "angry", "tags": ["aggressive"]}, "source": "llm"}` |
| 2 | plan | `plan` | Treat instrumental/clean/language as hard constraints and the rest as soft preferences. | `{"hard_constraints": {}, "soft_preferences": {"mood": "angry", "tags": ["aggressive"]}}` |
| 3 | tool | `search_songs` | Rank the catalog with the deterministic scorer. | `{"top": ["Iron Requiem", "Storm Runner", "Gym Hero", "Bass Cathedral"]}` |
| 4 | check | `check_playlist` | Verify hard constraints, result count and match quality. | `{"passed": true, "issues": []}` |
| 5 | result | `finish` | Finished after 0 revision(s) with high confidence. | `{"rounds": 0, "confidence": "high", "songs": 4}` |
| 6 | tool | `retrieve_context` | Fetch song cards and genre/mood notes to ground the explanation. | `{"documents": ["song:14", "song:3", "song:5", "song:38", "mood:angry"]}` |
| 7 | tool | `explain` | Write one grounded, cited reason per song and verify it. | `{"source": "llm-grounded"}` |

Final songs: Iron Requiem (metal, instrumental=False, explicit=False); Storm Runner (rock, instrumental=False, explicit=False); Gym Hero (pop, instrumental=False, explicit=False); Bass Cathedral (edm, instrumental=True, explicit=False)

<!-- agent-traces:end -->
