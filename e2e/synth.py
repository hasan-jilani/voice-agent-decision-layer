"""Flux TTS renders the caller's line for a subset of routing scenarios."""
import asyncio, json, os, wave, websockets
KEY = os.environ["DEEPGRAM_API_KEY"]; SR = 16000
PICK = ["STR-01","STR-08","AUT-01","AUT-04","KEY-01","KEY-07","KEY-10",
        "SEQ-01","FRD-01","SWI-01","SWI-03","ESC-03"]
VOICES = ["flux-haley-en","flux-marcus-en","flux-elise-en","flux-donovan-en",
          "flux-priya-en","flux-wade-en"]
CORP = {json.loads(l)["id"]: json.loads(l) for l in open("../routing/corpus.jsonl")}

async def main():
    man = []
    for i, sid in enumerate(PICK):
        sc = CORP[sid]
        text = [t["text"] for t in sc["transcript"] if t["role"] == "customer"][-1]
        voice = VOICES[i % len(VOICES)]
        path = f"audio/{sid}.wav"
        url = f"wss://api.deepgram.com/v2/speak?model={voice}&encoding=linear16&sample_rate={SR}"
        async with websockets.connect(url, additional_headers={"Authorization": f"Token {KEY}"},
                                      max_size=None) as ws:
            await ws.send(json.dumps({"type":"Speak","text":text}))
            await ws.send(json.dumps({"type":"Flush"}))
            pcm = bytearray()
            while True:
                m = await asyncio.wait_for(ws.recv(), timeout=45)
                if isinstance(m,(bytes,bytearray)): pcm += m
                elif json.loads(m).get("type") == "SpeechMetadata": break
            await ws.send(json.dumps({"type":"Close"}))
        with wave.open(path,"wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(pcm))
        man.append({"id": sid, "text": text, "wav": path, "voice": voice,
                    "label": sc["label"], "account": sc["account"]})
        print(f"  {sid:8s} {voice:18s} {len(pcm)/2/SR:.2f}s")
    json.dump(man, open("manifest.json","w"), indent=1)
    print(f"{len(man)} caller utterances")
asyncio.run(main())
