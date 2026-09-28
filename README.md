# The decision layer in a voice agent

A voice agent makes dozens of decisions per turn and one of them is: **which tool do I call
next?** Today that decision is usually folded into a general LLM call, alongside reasoning and
generating the reply.

This repo measures what happens when you pull that decision out and give it to a model built
for bounded decisions instead. Two experiments, both run live against real APIs:

- **[`routing/`](routing/RESULTS.md)**: the routing decision on its own. 48 caller scenarios,
  a 12-tool catalog, 8 ordered routing rules, five different routers.
- **[`e2e/`](e2e/RESULTS.md)**: a full turn end to end. Deepgram Flux STT → route → tool →
  gpt-4.1-mini streaming into Deepgram Flux TTS, timed from end of caller speech to first
  audio out.

**▶ [Watch the routing race in your browser](https://hasan-jilani.github.io/voice-agent-decision-layer/)**,
a replay of all 48 decisions at their actually measured latency and cost.

![routing race](docs/img/tool_routing_wide.gif)

## The component result

48 routing decisions, mean of 3 runs:

| Router | Accuracy | p50 latency | Cost / 1k |
|---|---|---|---|
| `keyword_rules` | 37.5% | 0ms | $0 |
| `llm_decomposed` (gpt-4.1-mini) | 75.0% | 956ms | $0.294 |
| `jev_decomposed` (jev-1.13.0) | 83–88% | 204ms | $0.065 |
| `llm_whole` (gpt-4.1-mini) | 89.6% | 688ms | $0.365 |
| **`jev_whole`** (jev-1.13.0) | **93.8%** | **215ms** | **$0.077** |

**3.2x faster, 4.7x cheaper, and slightly more accurate** than handing the same job to an LLM
with the same routing spec in context.

## The end-to-end result

12 scenarios, measured from `EndOfTurn` to the first audio frame out of TTS, the gap a caller
experiences as silence:

| Arm | Route p50 | Time to first audio | Correct tool |
|---|---|---|---|
| `llm_route` | 660ms | 1695ms | 11/12 |
| `jev_route` | 317ms | 1422ms | 12/12 |
| `jev_speculative` | 124ms | **1172ms** | 12/12 |

**Swapping the router saves 273ms (16%). Firing it inside Flux's speculative window saves
523ms (31%),** and beat the baseline on all 12 scenarios individually.

`jev_speculative` starts routing at `EagerEndOfTurn` rather than waiting for the turn to be
confirmed, so most of the routing cost lands in a pause the pipeline already takes. Median
routing cost drops to 124ms and in the best cases to 30ms.

Of the 1172ms that remains, roughly 900ms is the LLM writing the sentence and TTS starting to
speak it. That is the ceiling on this approach, and it is the LLM doing the job it is actually
good at.

## Three things worth knowing

**Keyword routing is not a real option.** 37.5%, and it fails worst exactly where routing
matters: 12% on authenticate-first, 17% on fraud, 17% on sequencing. It only handles the cases
where the obvious word happens to be the right answer.

**Decomposition made it worse.** Splitting routing into 7 yes/no questions plus an intent, then
reassembling with rules in code, dropped Jev from 93.8% to 85.4%. Routing is one irreducible
12-way choice, so decomposing it forces a lossy intermediate representation. Match the
representation to the shape of the decision rather than decomposing by reflex.

**The remaining latency is generation.** The decision layer removes nearly all of what it can.
Anything past that is language work.

## Caveats, up front

- **I wrote both the scenarios and the correct answers.** That is a real bias. Read the
  accuracy column as "comparable quality" rather than as a score, and open an issue if you
  think a label is wrong. That is the most useful thing anyone could do with this.
- **Latency and cost do not depend on those labels.** Those are measured.
- The LLM arms are nondeterministic. Re-running gives slightly different numbers; accuracy held
  stable across 3 runs, latency varies with network.
- Latency is end-to-end API time from one machine in the US, not model inference time.
- `e2e` uses a mock tool with a fixed 150ms delay, identical across arms.
- 48 scenarios and one routing spec, both of my own design. A different spec produces different
  traps.

## Reproduce

Needs `TYPESAFE_API_KEY`, `OPENAI_API_KEY`, and for `e2e`, `DEEPGRAM_API_KEY`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

cd routing
../.venv/bin/python build_corpus.py   # regenerate corpus.jsonl
../.venv/bin/python score.py          # all five routers
../.venv/bin/python failures.py       # every miss, itemized

cd ../e2e
../.venv/bin/python synth.py          # Flux TTS renders the caller lines
../.venv/bin/python agent.py          # all three arms, live, ~6 min
../.venv/bin/python report.py
```

## What is not here

A fine-tuned classifier or a local model. Both would also fit the latency budget, possibly for
less, and neither was tested. The honest limit of this work is that it compares a hosted
general LLM against a hosted decision model; it does not establish that you need this
particular decision model.
