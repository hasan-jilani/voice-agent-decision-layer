"""End-to-end voice agent turn, measured from end of caller speech to first TTS audio.

Pipeline: Flux STT (/v2/listen) -> route -> tool -> LLM generation -> Flux TTS (/v2/speak)

Three arms, identical except for how the tool gets chosen:
  llm_route        LLM picks the tool via function calling, then a second LLM call speaks.
  jev_route        Jev picks the tool at EndOfTurn, one LLM call speaks.
  jev_speculative  Jev picks the tool at EagerEndOfTurn, discarded on TurnResumed.
"""
import asyncio, json, os, sys, time, wave, websockets, openai
sys.path.insert(0, os.path.abspath("../routing"))
from harness import TOOLS, TOOL_CRITERIA, SPEC, render as render_route

KEY = os.environ["DEEPGRAM_API_KEY"]; SR = 16000
CHUNK = int(SR*0.08)*2
LLM = "gpt-4.1-mini"
TOOL_MS = 150                     # mock backend call, identical in every arm
MAN = json.load(open("manifest.json"))
OA = openai.AsyncOpenAI()

LISTEN = ("wss://api.deepgram.com/v2/listen?model=flux-general-en"
          f"&encoding=linear16&sample_rate={SR}"
          "&eager_eot_threshold=0.5&eot_threshold=0.7&eot_timeout_ms=5000")
SPEAK = f"wss://api.deepgram.com/v2/speak?model=flux-haley-en&encoding=linear16&sample_rate={SR}"

def pcm_of(p):
    with wave.open(p,"rb") as w: return w.readframes(w.getnframes())

async def mock_tool(name):
    await asyncio.sleep(TOOL_MS/1000)
    return {"tool": name, "result": "ok", "data": "account in good standing, no outage on record"}

# ---------------- routing implementations
OA_TOOLS = [{"type":"function","function":{"name":t,"description":TOOL_CRITERIA[t],
             "parameters":{"type":"object","properties":{}}}} for t in TOOLS]

async def route_llm(state_txt):
    r = await OA.chat.completions.create(model=LLM, temperature=0, tools=OA_TOOLS,
        tool_choice="required", max_completion_tokens=100,
        messages=[{"role":"system","content":"You route a telecom voice agent.\n\n"+SPEC},
                  {"role":"user","content":state_txt}])
    tc = r.choices[0].message.tool_calls
    return tc[0].function.name if tc else "transfer_to_human"

_ts = None
def _typesafe():
    global _ts
    if _ts is None:
        from typesafe_sdk import AsyncTypeSafeClient; _ts = AsyncTypeSafeClient()
    return _ts

async def route_jev(state_txt):
    from typesafe_sdk import Choice
    r = await _typesafe().system_one(state="ROUTING SPEC\n"+SPEC+"\n\n"+state_txt,
        questions={"tool": Choice(instructions="Apply the routing rules in order and pick the next tool.",
                                  criteria=TOOL_CRITERIA)})
    return r.answers["tool"].choice

# ---------------- generation streamed straight into Flux TTS
async def speak_response(tool_result, caller_text, t_eot):
    """Stream LLM tokens into /v2/speak; return ms from EndOfTurn to first audio frame."""
    async with websockets.connect(SPEAK, additional_headers={"Authorization": f"Token {KEY}"},
                                  max_size=None) as ws:
        first_audio = asyncio.Event(); t_first = {}
        async def reader():
            while not first_audio.is_set():
                m = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(m,(bytes,bytearray)) and len(m) > 0:
                    t_first["t"] = time.perf_counter(); first_audio.set(); return
        rtask = asyncio.create_task(reader())
        stream = await OA.chat.completions.create(model=LLM, temperature=0, stream=True,
            max_completion_tokens=60,
            messages=[{"role":"system","content":"You are a telecom voice agent. Reply in one short spoken sentence."},
                      {"role":"user","content":f"Caller said: {caller_text}\nTool {tool_result['tool']} returned: {tool_result['data']}"}])
        t_tok = None; buf = ""
        async for ch in stream:
            d = ch.choices[0].delta.content or ""
            if d:
                if t_tok is None: t_tok = time.perf_counter()
                buf += d
                if len(buf) > 18:
                    await ws.send(json.dumps({"type":"Speak","text":buf})); buf = ""
        if buf: await ws.send(json.dumps({"type":"Speak","text":buf}))
        await ws.send(json.dumps({"type":"Flush"}))
        await asyncio.wait_for(first_audio.wait(), timeout=30)
        rtask.cancel()
        try: await ws.send(json.dumps({"type":"Close"}))
        except Exception: pass
    return (t_first["t"]-t_eot)*1000, (t_tok-t_eot)*1000 if t_tok else None

# ---------------- one full turn
async def run_turn(item, arm):
    pcm = pcm_of(item["wav"]); sc = {"transcript": [], "account": item["account"]}
    marks = {}
    async with websockets.connect(LISTEN, additional_headers={"Authorization": f"Token {KEY}"}) as ws:
        eot = asyncio.Event(); eager_task = {"t": None}; state = {"transcript": ""}
        async def send():
            for o in range(0, len(pcm), CHUNK):
                await ws.send(pcm[o:o+CHUNK]); await asyncio.sleep(0.08)
            for _ in range(40):
                if eot.is_set(): return
                await ws.send(b"\x00"*CHUNK); await asyncio.sleep(0.08)
        async def recv():
            while True:
                try: m = json.loads(await asyncio.wait_for(ws.recv(), timeout=12))
                except (asyncio.TimeoutError, websockets.ConnectionClosed): eot.set(); return
                ev = m.get("event")
                if ev == "EagerEndOfTurn" and arm == "jev_speculative" and eager_task["t"] is None:
                    sc["transcript"] = [{"role":"customer","text":m.get("transcript","")}]
                    eager_task["t"] = asyncio.create_task(route_jev(render_route(sc)))
                    marks["eager_started"] = time.perf_counter()
                elif ev == "TurnResumed" and eager_task["t"]:
                    eager_task["t"].cancel(); eager_task["t"] = None
                elif ev == "EndOfTurn":
                    state["transcript"] = m.get("transcript",""); marks["eot"] = time.perf_counter()
                    eot.set(); return
        await asyncio.gather(send(), recv())

    t_eot = marks.get("eot", time.perf_counter())
    sc["transcript"] = [{"role":"customer","text":state["transcript"]}]
    st = render_route(sc)

    if arm == "llm_route":
        tool = await route_llm(st)
    elif arm == "jev_route":
        tool = await route_jev(st)
    else:
        tool = await eager_task["t"] if eager_task["t"] else await route_jev(st)
    marks["routed"] = time.perf_counter()
    res = await mock_tool(tool)
    marks["tooled"] = time.perf_counter()
    ttfa, ttft = await speak_response(res, state["transcript"], t_eot)

    return {"id": item["id"], "arm": arm, "tool": tool, "label": item["label"],
            "correct": tool == item["label"],
            "route_ms": (marks["routed"]-t_eot)*1000,
            "tool_done_ms": (marks["tooled"]-t_eot)*1000,
            "llm_first_token_ms": ttft, "first_audio_ms": ttfa,
            "transcript": state["transcript"]}

async def main():
    arms = sys.argv[1:] or ["llm_route","jev_route","jev_speculative"]
    out = []
    for arm in arms:
        for it in MAN:
            try:
                r = await run_turn(it, arm); out.append(r)
                print(f"  {arm:16s} {r['id']:8s} route {r['route_ms']:6.0f}ms  "
                      f"first-audio {r['first_audio_ms']:6.0f}ms  {'ok ' if r['correct'] else 'MISS'} {r['tool']}")
            except Exception as e:
                print(f"  {arm:16s} {it['id']:8s} ERROR {str(e)[:90]}")
    json.dump(out, open("results.json","w"), indent=1)
asyncio.run(main())
