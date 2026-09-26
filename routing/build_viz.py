"""Pack measured routing runs into the replay dataset."""
import json
CORP = {json.loads(l)["id"]: json.loads(l) for l in open("corpus.jsonl")}
ARMS = {"jev": "jev_whole", "llm": "llm_whole"}
runs = {k: {r["id"]: r for r in json.load(open(f"results/{v}.json"))} for k, v in ARMS.items()}
order = [json.loads(l)["id"] for l in open("corpus.jsonl")]

items = []
for sid in order:
    sc = CORP[sid]
    say = [t["text"] for t in sc["transcript"] if t["role"] == "customer"][-1]
    row = {"id": sid, "cat": sc["category"], "truth": sc["label"],
           "say": say if len(say) <= 96 else say[:93] + "...",
           "arms": {}}
    ok = True
    for a in ARMS:
        r = runs[a].get(sid)
        if not r: ok = False; break
        row["arms"][a] = {"v": r["tool"], "ms": round(r["ms"]), "c": r["cost"]}
    if ok: items.append(row)

meta = {"models": {"jev": "jev-1.13.0", "llm": "gpt-4.1-mini"}, "n": len(items)}
json.dump({"meta": meta, "items": items}, open("viz_data.json","w"), separators=(",",":"))
print(f"{len(items)} rows -> viz_data.json ({len(open('viz_data.json').read())/1024:.1f} KB)")
for a in ARMS:
    tot = sum(i["arms"][a]["ms"] for i in items)
    cost = sum(i["arms"][a]["c"] for i in items)
    ok = sum(i["arms"][a]["v"] == i["truth"] for i in items)
    print(f"  {a:4s} total {tot/1000:6.2f}s  ${cost:.5f}  per-decision {tot/len(items):.0f}ms  correct {ok}/{len(items)}")
