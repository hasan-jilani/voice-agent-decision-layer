# End-to-end turn latency, measured

**Question:** does replacing LLM tool-routing with a decision layer make a difference a
caller would actually notice?

Measured from **EndOfTurn** (Flux confirms the caller stopped speaking) to **first audio
frame out of Flux TTS**. That is the gap the caller experiences as silence.

## Pipeline

```
caller audio -> Flux STT /v2/listen -> route -> tool (mock, 150ms) ->
   gpt-4.1-mini generation, streamed token by token into ->
   Flux TTS /v2/speak -> first audio frame
```

12 scenarios drawn from `../routing/corpus.jsonl`, caller lines spoken by Flux TTS in six
voices, streamed through Flux STT in real time at 80ms chunks. Everything is identical
across arms except how the tool is chosen.

| Arm | Routing |
|---|---|
| `llm_route` | gpt-4.1-mini function calling at EndOfTurn, then a second call to generate. |
| `jev_route` | Jev Choice at EndOfTurn, then one call to generate. |
| `jev_speculative` | Jev Choice fired at **EagerEndOfTurn**, cancelled on TurnResumed. |

## Results

| Arm | Route p50 | First audio p50 | p90 | Correct tool |
|---|---|---|---|---|
| `llm_route` | 660ms | **1695ms** | 1844ms | 11/12 |
| `jev_route` | 317ms | **1422ms** | 1529ms | 12/12 |
| `jev_speculative` | 124ms | **1172ms** | 1399ms | 12/12 |

**`jev_route` saves 273ms, or 16% of time-to-first-audio.**
**`jev_speculative` saves 523ms, or 31%.**

The speculative arm wins twice over. It uses the faster router, and it starts that router
before the turn is confirmed, so most of the routing cost lands inside Flux's eager
window and never reaches the caller. Median routing cost drops to 124ms and in the best
cases to 30ms, meaning the decision was essentially complete by the time the turn ended.

Per-scenario, `jev_speculative` beat `llm_route` on all 12.

## What is left

In the best arm, 1172ms breaks down as roughly 124ms routing, 150ms tool, and about
900ms of generation plus TTS first byte. So **77% of the remaining latency is the LLM
writing the sentence and the TTS starting to speak it.**

That is the honest ceiling on this approach. The decision layer removes nearly all of
what it can remove. What remains is the language work, which is the LLM's actual job and
is not what you would want to take away from it.

## Caveats

- 12 scenarios, one run per arm. Enough to establish the direction, not the exact figure.
- The tool is a mock with a fixed 150ms delay. A real backend varies, and that variance
  would sit on top of every arm equally.
- Absolute numbers include network latency from one machine in the US. The deltas between
  arms are the durable part.
- `llm_route` makes two LLM calls (route, then generate); the Jev arms make one Jev call
  and one LLM call. That is the fair comparison of the two architectures, but it does mean
  the arms differ in call count as well as model.
- 11/12 vs 12/12 on tool accuracy is too small a sample to claim a quality difference.
  See `../routing/RESULTS.md` for the 48-scenario version.

## Reproduce

```bash
../.venv/bin/python synth.py     # Flux TTS renders the caller lines
../.venv/bin/python agent.py     # all three arms, live, ~6 min
../.venv/bin/python report.py
```
