import json, os, statistics as st, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from harness import ARMS

CORPUS = [json.loads(l) for l in open("corpus.jsonl")]
ARM_NAMES = sys.argv[1:] or list(ARMS)

def run(arm):
    fn = ARMS[arm]
    def one(sc):
        for a in range(3):
            try:
                d = fn(sc)
                return {"id": sc["id"], "cat": sc["category"], "label": sc["label"],
                        "tool": d.tool, "ms": d.latency_ms, "cost": d.cost_usd, "sem": d.sem}
            except Exception as e:
                if a == 2: return {"id": sc["id"], "cat": sc["category"], "label": sc["label"],
                                   "tool": "ERROR", "ms": 0, "cost": 0, "sem": {"err": str(e)[:120]}}
    with ThreadPoolExecutor(max_workers=8) as ex: return list(ex.map(one, CORPUS))

rows_all, summary = {}, []
for arm in ARM_NAMES:
    rows = run(arm); rows_all[arm] = rows
    json.dump(rows, open(f"results/{arm}.json","w"), indent=1)
    ok = sum(r["tool"] == r["label"] for r in rows)
    lat = sorted(r["ms"] for r in rows)
    bycat = {c: round(100*sum(r["tool"]==r["label"] for r in rows if r["cat"]==c)
                      / max(1,sum(1 for r in rows if r["cat"]==c)))
             for c in sorted({r["cat"] for r in rows})}
    s = {"arm": arm, "acc": round(100*ok/len(rows),1), "n": len(rows),
         "p50": round(lat[len(lat)//2]), "p90": round(lat[int(len(lat)*.9)]),
         "cost1k": round(1000*sum(r["cost"] for r in rows)/len(rows), 3),
         "err": sum(r["tool"]=="ERROR" for r in rows), "bycat": bycat}
    summary.append(s)
    print(f"  {arm:16s} acc {s['acc']:5.1f}%  p50 {s['p50']:5d}ms  ${s['cost1k']:.3f}/1k  {bycat}")

json.dump(summary, open("results/summary.json","w"), indent=1)
H = ["arm","acc","p50","p90","cost1k"]
print("\n| " + " | ".join(H) + " |"); print("|" + "---|"*len(H))
for s in summary: print("| " + " | ".join(str(s[h]) for h in H) + " |")
