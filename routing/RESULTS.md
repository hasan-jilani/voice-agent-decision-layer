# Tool routing benchmark, v0.1 results

**Question:** given the conversation so far, which of 12 tools should a telecom voice
agent run next?

**Why this decision:** routing is the most universal bounded decision in a voice agent.
Every agent with tools makes it on nearly every turn. It has an objectively gradeable
answer, and unlike turn-taking it needs no audio, so a text-in decision model competes
fairly.

**Corpus:** 48 scenarios against a 12-tool catalog and 8 ordered routing rules
(`tools.md`). Categories: straightforward, authenticate-first, keyword traps (the obvious
word points at the wrong tool), sequencing (the right tool depends on what already
happened), fraud-versus-billing, mid-turn intent switches, escalation.

## Arms

| Arm | Architecture |
|---|---|
| `keyword_rules` | Regex over the transcript. The "just write a router" control. |
| `llm_whole` | Catalog + rules + conversation → tool name, one call. |
| `llm_decomposed` | LLM answers 7 yes/no questions + an intent → routing rules in code. |
| `jev_whole` | Jev, one Choice question over the 12-tool catalog. |
| `jev_decomposed` | Jev answers the same 7 questions + intent → same routing rules in code. |

## Results

| Arm | Accuracy | p50 | p90 | Cost /1k |
|---|---|---|---|---|
| `keyword_rules` | 37.5% | 0ms | 0ms | $0 |
| `llm_decomposed` | 75.0% | 956ms | 1060ms | $0.294 |
| `jev_decomposed` | 83.3–87.5% | 204ms | 210ms | $0.065 |
| `llm_whole` | 89.6% | 688ms | 1692ms | $0.365 |
| **`jev_whole`** | **93.8%** | **215ms** | **305ms** | **$0.077** |

Three runs. `jev_whole` and `llm_whole` returned identical accuracy every time;
`jev_decomposed` varied 83.3–87.5%.

## What this shows

**1. Keyword routing is not a real option.** 37.5%, and it fails worst exactly where
routing matters: 12% on authenticate-first, 17% on fraud, 17% on sequencing. It only
handles the cases where the obvious word happens to be the right answer.

**2. `jev_whole` wins on all three axes at once.** Against `llm_whole`: better accuracy
(93.8% vs 89.6%), 3.2x faster, 4.7x cheaper. Routing is a Choice over a bounded set,
which is the shape Jev is built for, and it shows.

**3. Decomposition made it worse, which is worth knowing before you try it.** Breaking the
routing decision into 7 yes/no questions plus an intent, then reassembling it with rules in
code, moved `jev_whole` from 93.8% down to 85.4% and `llm_whole` from 89.6% down to 75.0%.

The reason is the shape of the decision. Routing is a single irreducible 12-way
classification. There is no natural set of sub-facts to decompose it into, so you have to
invent an intermediate representation and hand-write a state machine that reassembles it,
and every step of that is lossy.

That matters because "break the decision into narrow questions" is common advice and it does
work for some decisions, specifically the ones whose policy really is a conjunction of
independently checkable facts. A single N-way choice is not one of those. Match the
representation to the shape of the decision rather than decomposing by reflex.

## Honest attribution of the decomposed failures

A meaningful share of the decomposed arms' errors are **my rule engine, not the models**:

- `SEQ-04` ("you said there's an outage, when will it be fixed?"): my engine has no way
  to express "asking about the status of a known outage," so it advances to diagnostics.
- `SEQ-05` (outage checked, diagnostics run, technician visit failed): my R6 chain has
  no terminal state, so it returns `schedule_technician` forever.
- `KEY-01`: my `charge_identified` question says "named or surfaced in this
  conversation." The caller did say "forty dollar charge," so the models answered
  correctly and my rule then routed wrong. That is a question-wording bug.

Roughly 3 of `jev_decomposed`'s 7 misses trace to the engine rather than the model. So
the honest claim is **"my decomposition was worse than the models' native handling,"**
not "decomposition is worse in principle." A better-written state machine would close
part of the gap. That it took real effort to write and still has bugs is itself part of
the finding.

## Caveats

- 48 scenarios, and the same author wrote both the scenarios and the correct answers. That
  is a real bias, and the accuracy column should be read as "comparable quality" rather than
  as a score. Latency and cost do not depend on the labels.
- The routing spec is mine. A different spec would produce different traps.
- `keyword_rules` is a deliberately naive control, not a serious production router.
  A hand-tuned router with 200 rules would do better and take weeks to maintain.

## Reproduce

```bash
../.venv/bin/python build_corpus.py
../.venv/bin/python score.py
../.venv/bin/python failures.py
ROUTE_LLM_MODEL=gpt-4.1 ../.venv/bin/python score.py llm_whole llm_decomposed
```
