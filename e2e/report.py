import json, statistics as st
from collections import defaultdict
rows = json.load(open("results.json"))
by = defaultdict(list)
for r in rows: by[r["arm"]].append(r)
p = lambda v,q: sorted(v)[min(len(v)-1,int(len(v)*q))]

print(f"{'arm':18s} {'n':>3s} {'route p50':>10s} {'1st audio p50':>14s} {'p90':>7s} {'correct':>8s}")
print("-"*70)
base = None
for arm in ["llm_route","jev_route","jev_speculative"]:
    rs = by.get(arm) or []
    if not rs: continue
    fa = [r["first_audio_ms"] for r in rs]; rt = [r["route_ms"] for r in rs]
    ok = sum(r["correct"] for r in rs)
    if arm == "llm_route": base = st.median(fa)
    print(f"{arm:18s} {len(rs):3d} {st.median(rt):9.0f}ms {st.median(fa):13.0f}ms {p(fa,.9):6.0f}ms "
          f"{ok:4d}/{len(rs)}")
print()
if base:
    for arm in ["jev_route","jev_speculative"]:
        rs = by.get(arm) or []
        if not rs: continue
        d = base - st.median([r["first_audio_ms"] for r in rs])
        print(f"  {arm:18s} {d:+6.0f}ms vs llm_route at the median "
              f"({100*d/base:+.0f}% of time-to-first-audio)")
print("\nper-scenario first-audio (ms):")
ids = sorted({r["id"] for r in rows})
print(f"  {'scenario':10s} " + "".join(f"{a:>17s}" for a in ["llm_route","jev_route","jev_speculative"]))
for i in ids:
    line = f"  {i:10s} "
    for a in ["llm_route","jev_route","jev_speculative"]:
        m = next((r for r in by[a] if r["id"]==i), None)
        cell = f"{m['first_audio_ms']:.0f}" if m else "-"
        line += f"{cell:>17s}"
    print(line)
