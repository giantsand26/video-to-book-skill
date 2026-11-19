import json, sys
segs = json.load(open(sys.argv[1], encoding="utf-8"))
def ts(s):
    s=int(s); m,ss=divmod(s,60)
    return f"{m:02d}:{ss:02d}"
paras=[]; cur=[]; chars=0
for seg in segs:
    t=seg["text"].strip()
    if not t: continue
    cur.append((seg["start"], t)); chars+=len(t)
    if t[-1] in "。！？" and chars>=80:
        paras.append(cur); cur=[]; chars=0
    elif chars>=220:
        paras.append(cur); cur=[]; chars=0
if cur: paras.append(cur)
lines=[f"[{ts(p[0][0])}] "+"".join(t for _,t in p) for p in paras]
open(sys.argv[2],"w",encoding="utf-8").write("\n\n".join(lines))
print(sys.argv[1], "段数:", len(paras))
