"""Run the agent on sample requests and save its reasoning traces.

  python eval/agent_demo.py [--delay 4]

Writes docs/agent_traces.json (machine-readable log) and embeds a readable version in
ai_interactions.md between the agent-traces markers (re-running replaces the section).
Uses the live LLM for parsing, revision decisions and explanations.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))

from vibematch import VibeMatch  # noqa: E402

PROMPTS = ["instrumental heavy metal", "clean explicit-free hip-hop for the gym",
           "romantic jazz instrumental from the 1960s", "i am angry"]
START, END = "<!-- agent-traces:start -->", "<!-- agent-traces:end -->"


def short(obj, limit: int = 170) -> str:
    text = json.dumps(obj, ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def render(runs: list) -> str:
    out = [START, "", "## Applied AI project: VibeMatch agent reasoning traces", "",
           "The agent ([src/agent.py](src/agent.py)) runs plan, act (tools), check, decide, revise. The LLM never ranks songs: "
           "it parses the request and, only when a check fails, chooses one revision from a fixed menu "
           "(`filter_violations`, `broaden`, `accept`). If the LLM is unavailable a deterministic policy makes the same choice. "
           "Machine-readable log: [docs/agent_traces.json](docs/agent_traces.json). Regenerate with `python eval/agent_demo.py`.", ""]
    for run in runs:
        out += [f"### Request: \"{run['request']}\"", "",
                f"Result: {len(run['songs'])} songs, confidence **{run['confidence']}**, explanation source `{run['explain_source']}`, "
                f"{run['seconds']:.1f}s.", "", "| # | Kind | Step | Reasoning | Output |", "|---|---|---|---|---|"]
        for s in run["trace"]:
            out.append(f"| {s['step']} | {s['kind']} | `{s['name']}` | {s['thought'].replace('|', '/')} | "
                       f"`{short(s['output']).replace('|', '/')}` |")
        out += ["", "Final songs: " + "; ".join(f"{t}" for t in run["songs"]), ""]
    out += [END]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=4.0)
    args = ap.parse_args()

    vm = VibeMatch()
    runs = []
    for prompt in PROMPTS:
        t0 = time.perf_counter()
        r = vm.ask(prompt, k=5)
        runs.append({"request": prompt, "confidence": r.confidence, "explain_source": r.explain_source,
                     "seconds": time.perf_counter() - t0, "profile": r.prefs,
                     "songs": [f"{s['title']} ({s['genre']}, instrumental={s['instrumental']}, explicit={s['explicit']})"
                               for s, _, _ in r.recommendations],
                     "trace": r.trace})
        print(f"done {prompt!r}: confidence={r.confidence}, steps={len(r.trace)}")
        time.sleep(args.delay)

    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "agent_traces.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False) + "\n")
    md = ROOT / "ai_interactions.md"
    text = md.read_text()
    block = render(runs)
    if START in text and END in text:
        text = text[: text.index(START)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip() + "\n\n---\n\n" + block + "\n"
    md.write_text(text)
    print("wrote docs/agent_traces.json and ai_interactions.md")


if __name__ == "__main__":
    main()
