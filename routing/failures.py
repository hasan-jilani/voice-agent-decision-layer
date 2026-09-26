import json
from harness import route
CORP = {json.loads(l)["id"]: json.loads(l) for l in open("corpus.jsonl")}
for arm in ["jev_whole","jev_decomposed","llm_whole","llm_decomposed"]:
    rows = json.load(open(f"results/{arm}.json"))
    bad = [r for r in rows if r["tool"] != r["label"]]
    print(f"===== {arm}: {len(bad)} misses")
    for r in bad:
        extra = ""
        if "decomposed" in arm:
            sem = {k: round(v,2) for k,v in r["sem"].items() if isinstance(v,(int,float)) and v>=.5}
            # would the ORACLE semantics have routed correctly? isolates model vs rule-engine
            extra = f"  hi={sem}"
        print(f"  {r['id']:8s} [{r['cat']:14s}] want {r['label']:22s} got {r['tool']:22s}{extra}")
