#!/usr/bin/env python3
"""Pagina "dosi steering" (24/10): una riga per emozione, accanto un grafico con la curva di efficacia per dose
e la fascia Dmin-Dmax. Dati: prova-dosi-medio.jsonl + prova-dosi-fini.jsonl (vettore se', L15-L31, pensiero).
Efficacia = giudice Opus col metro dell'utente (giudizio-dosi/, emozione giusta, non rotto, dose giusta o un po' eccessiva)
dove c'e'; prima del giudizio, provvisoria, il lettore delle 8 emozioni (rango 1 a L24). Fascia da
engrammi/DOSI-EMOZIONI.md. La rigenera la route /dosi/ di notturna-web.py quando cambiano i dati.
Uscita: pagina-dosi/index.html (fissa) e pagina-dosi/dati.json (la pagina lo rilegge ogni 30 s)."""
import glob
import json
import os
import re
import time
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
OUT = f"{D}/pagina-dosi"
PROVE = [f"{D}/prova-dosi-medio.jsonl", f"{D}/prova-dosi-fini.jsonl", f"{D}/prova-dosi-giri.jsonl"]
GIUDIZIO = f"{D}/giudizio-dosi"
TABELLA = "/data/memoria-episodica-affettiva/engrammi/DOSI-EMOZIONI.md"
ORDINE = ["gioia", "fiducia", "paura", "sorpresa", "tristezza", "disgusto", "rabbia", "attesa",   # giro medio
          "estasi", "ammirazione", "terrore", "stupore", "cordoglio", "ribrezzo", "furia", "vigilanza",   # interno
          "serenità", "accettazione", "apprensione", "distrazione", "malinconia", "noia", "fastidio", "interesse"]
UTILE = ("giusta", "un po' eccessiva")


def chiave(r):
    return "|".join(map(str, (r["k"], r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"])))


def righe(f):
    if not os.path.exists(f):
        return []
    return [json.loads(x) for x in open(f) if x.endswith("\n") and x.strip()]


def giudizi():
    """{chiave: giudizio} dalle uscite del giudice Opus (n -> chiave in mappa.json)"""
    if not os.path.exists(f"{GIUDIZIO}/mappa.json"):
        return {}
    m = json.load(open(f"{GIUDIZIO}/mappa.json"))
    return {m[str(g["n"])]: g for f in glob.glob(f"{GIUDIZIO}/uscite/*.jsonl") for g in righe(f) if str(g["n"]) in m}


def fasce():
    """{emozione: [Dmin, Dmax]} dalla tabella, solo le righe riempite"""
    out = {}
    if os.path.exists(TABELLA):
        for x in open(TABELLA):
            c = [s.strip() for s in x.strip().strip("|").split("|")]
            if len(c) >= 3 and re.fullmatch(r"0\.\d+", c[1]) and re.fullmatch(r"0\.\d+", c[2]):
                out[c[0]] = [float(c[1]), float(c[2])]
    return out


def conti(prove, G):
    """per emozione e dose: punti, rotti, utili e giudicati (Opus), lettore; per il caso solo l'efficacia"""
    c = defaultdict(lambda: defaultdict(lambda: dict(n=0, rotti=0, giudicati=0, utili=0, letti=0, lettore=0)))
    for r in prove:
        if r.get("base"):
            continue
        x = c[r["emo"] if r["fonte"] != "caso" else r["emo"] + "|caso"][r["dose"]]
        x["n"] += 1
        g = G.get(chiave(r))
        if not r["cambiato"]:   # testo uguale alla base: per il giudice conta come non utile (lo aggiunge dati())
            x["uguali"] = x.get("uguali", 0) + 1
        if g:
            x["giudicati"] += 1
            x["rotti"] += g["rotto"]
            x["utili"] += g["emozione"] == r["emo"] and not g["rotto"] and g["dose"] in UTILE
        else:
            x["rotti"] += r["rotto"]
        if "rango8" in r and not r["rotto"]:
            x["letti"] += 1
            x["lettore"] += r["rango8"].get("24") == 1
    return c


def dati():
    prove = [r for f in PROVE for r in righe(f)]
    G, F = giudizi(), fasce()
    c = conti(prove, G)
    emozioni = []
    for e in ORDINE + sorted({k for k in c if "|" not in k} - set(ORDINE)):
        if e not in c and e not in F:
            continue
        punti = [dict(dose=d, **x) for d, x in sorted(c[e].items())]
        caso = [dict(dose=d, **x) for d, x in sorted(c.get(e + "|caso", {}).items())]
        for lista in (punti, caso):   # a giudizio iniziato i testi uguali alla base entrano come non utili
            if any(q["giudicati"] for q in lista):
                for q in lista:
                    q["giudicati"] += q.get("uguali", 0)
        emozioni.append({"emo": e, "punti": punti, "caso": caso, "fascia": F.get(e)})
    ultimo = next((r for r in reversed(prove) if not r.get("base")), None)
    return {"ora": time.strftime("%d/%m %H:%M"), "emozioni": emozioni,
            "ultimo": ultimo and f"{ultimo['emo']} {ultimo['dose']} su {ultimo['k']}",
            "giudicati": len(G), "punti": sum(1 for r in prove if not r.get("base"))}


PAGINA = r"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Dosi steering</title>
<script>/* il tema lo decide il pulsante della dashboard (localStorage "tema-dashboard", stessa origine :8095) */
function temaDashboard(){let x=null;try{x=localStorage.getItem("tema-dashboard")}catch(e){}if(x==="light"||x==="dark")document.documentElement.dataset.theme=x;else delete document.documentElement.dataset.theme}
temaDashboard();addEventListener("storage",e=>{if(e.key==="tema-dashboard"){temaDashboard();disegna()}});</script>
<style>
:root{color-scheme:light;--bg:#f4f3ef;--card:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--bordo:#e6e5e0;
  --err:#c0362c;--accent:#2a78d6;--fascia:rgba(42,120,214,.13);--btn:#efeee9}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#111110;--card:#1a1a19;
  --ink:#f4f4f2;--ink2:#c3c2b7;--muted:#8f8e86;--bordo:#2d2d2a;--err:#ea6b60;--accent:#3987e5;--fascia:rgba(57,135,229,.2);--btn:#262624}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#111110;--card:#1a1a19;--ink:#f4f4f2;--ink2:#c3c2b7;--muted:#8f8e86;
  --bordo:#2d2d2a;--err:#ea6b60;--accent:#3987e5;--fascia:rgba(57,135,229,.2);--btn:#262624}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:20px 16px 60px}
header,main{max-width:1100px;margin:0 auto}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin-bottom:10px}
header h1{font-size:22px;font-weight:700}
.home{margin-left:auto;background:var(--btn);border:1px solid var(--bordo);color:var(--ink);border-radius:8px;padding:5px 12px;text-decoration:none}
.nota{color:var(--ink2);max-width:1100px;margin:0 auto 14px}
.leg{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--ink2);font-size:13px;max-width:1100px;margin:0 auto 14px}
.leg i{display:inline-block;width:18px;height:0;border-top:2px solid;vertical-align:middle;margin-right:6px}
.riga{background:var(--card);border-radius:12px;padding:12px 16px;margin-bottom:10px;display:grid;grid-template-columns:150px 1fr;gap:12px;align-items:center}
.nome{font-size:16px;font-weight:600}.nome small{display:block;font-weight:400;color:var(--ink2);font-size:13px}
svg{width:100%;height:150px;display:block}
svg text{fill:var(--muted);font-size:11px}
@media (max-width:640px){.riga{grid-template-columns:1fr}}
</style></head><body>
<header><h1>Dosi steering</h1><span id="stato" style="color:var(--ink2)"></span><a class="home" href="/">← dashboard</a></header>
<p class="nota">Vettore sé, finestra L15-L31, modo pensiero, 12 contesti. Per ogni dose: quota di testi utili (emozione giusta,
non rotto, dose giusta o un po' eccessiva) secondo il giudice Opus col metro dell'utente. Finché il giudice non ha letto i
testi, la curva è quella provvisoria del lettore interno. La fascia è l'intervallo Dmin-Dmax di DOSI-EMOZIONI.md.</p>
<div class="leg"><span><i style="border-color:var(--accent)"></i>giudice Opus</span>
<span><i style="border-color:var(--muted);border-top-style:dashed"></i>lettore (provvisorio)</span>
<span><i style="border-color:var(--ink2);border-top-style:dotted"></i>vettore a caso</span>
<span><i style="border-color:var(--err);border-top-width:6px"></i>testi rotti</span></div>
<main id="m"></main>
<script>
let DATI=/*DATI*/null;
const css=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function media(p,campo,base){ /* curva liscia: media su 5 dosi vicine, pesata per i casi */
  return p.map((_,i)=>{let a=0,b=0;for(let j=Math.max(0,i-2);j<=Math.min(p.length-1,i+2);j++){a+=p[j][campo];b+=p[j][base]}return b?100*a/b:null})}
function linea(xs,ys,X,Y){let d="",su=false;xs.forEach((x,i)=>{if(ys[i]==null){su=false;return}d+=(su?"L":"M")+X(x).toFixed(1)+","+Y(ys[i]).toFixed(1);su=true});return d}
function grafico(e,x0,x1){
  const W=900,H=150,l=34,r=8,t=8,b=22,X=x=>l+(W-l-r)*(x-x0)/((x1-x0)||1),Y=y=>t+(H-t-b)*(1-y/100);
  const p=e.punti,xs=p.map(q=>q.dose);let s=`<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  if(e.fascia)s+=`<rect x="${X(e.fascia[0])}" y="${t}" width="${X(e.fascia[1])-X(e.fascia[0])}" height="${H-t-b}" fill="${css('--fascia')}"/>`;
  for(const y of [0,50,100])s+=`<line x1="${l}" x2="${W-r}" y1="${Y(y)}" y2="${Y(y)}" stroke="${css('--bordo')}"/><text x="${l-4}" y="${Y(y)+4}" text-anchor="end">${y}%</text>`;
  const passo=(x1-x0)>0.03?0.01:0.005;for(let x=Math.ceil(x0/passo)*passo;x<=x1+1e-9;x+=passo)s+=`<text x="${X(x)}" y="${H-6}" text-anchor="middle">${x.toFixed(3)}</text>`;
  p.forEach(q=>{if(q.rotti){const h=(H-t-b)*Math.min(1,q.rotti/q.n);s+=`<rect x="${X(q.dose)-2}" y="${H-b-h}" width="4" height="${h}" fill="${css('--err')}" opacity=".7"><title>${q.dose}: ${q.rotti} rotti su ${q.n}</title></rect>`}});
  if(e.caso.length){const c=e.caso.reduce((a,q)=>a+(q.giudicati?q.utili:0),0),n=e.caso.reduce((a,q)=>a+q.giudicati,0);
    if(n)s+=`<line x1="${l}" x2="${W-r}" y1="${Y(100*c/n)}" y2="${Y(100*c/n)}" stroke="${css('--ink2')}" stroke-dasharray="2 4"/>`}
  const lett=media(p,"lettore","letti");s+=`<path d="${linea(xs,lett,X,Y)}" fill="none" stroke="${css('--muted')}" stroke-width="1.5" stroke-dasharray="5 4"/>`;
  if(p.some(q=>q.giudicati)){const op=media(p,"utili","giudicati");s+=`<path d="${linea(xs,op,X,Y)}" fill="none" stroke="${css('--accent')}" stroke-width="2.5"/>`;
    p.forEach(q=>{if(q.giudicati)s+=`<circle cx="${X(q.dose)}" cy="${Y(100*q.utili/q.giudicati)}" r="2.5" fill="${css('--accent')}"><title>${q.dose}: ${q.utili} utili su ${q.giudicati}</title></circle>`})}
  return s+"</svg>"}
function disegna(){if(!DATI)return;
  const tutte=DATI.emozioni.flatMap(e=>e.punti.map(q=>q.dose).concat(e.fascia||[]));const x0=Math.min(...tutte),x1=Math.max(...tutte);
  document.getElementById("stato").textContent=`${DATI.punti} punti, ${DATI.giudicati} giudicati${DATI.ultimo?" · ultimo: "+DATI.ultimo:""} · ${DATI.ora}`;
  document.getElementById("m").innerHTML=DATI.emozioni.map(e=>{const n=e.punti.reduce((a,q)=>a+q.n,0);
    return`<div class="riga"><div class="nome">${e.emo}<small>${e.fascia?"Dmin "+e.fascia[0]+" · Dmax "+e.fascia[1]:"in taratura"}</small><small>${n} punti</small></div>${grafico(e,x0,x1)}</div>`}).join("")}
async function carica(){try{DATI=await (await fetch("dati.json",{cache:"no-store"})).json();disegna()}catch(e){}}
disegna();setInterval(carica,30000);
</script></body></html>"""


def scrivi():
    os.makedirs(OUT, exist_ok=True)
    tmp = f"{OUT}/dati.json.tmp"
    json.dump(dati(), open(tmp, "w"), ensure_ascii=False)
    os.replace(tmp, f"{OUT}/dati.json")
    # i dati entrano anche nella pagina: si vede subito, poi si aggiorna da dati.json ogni 30 s
    open(f"{OUT}/index.html.tmp", "w").write(PAGINA.replace("/*DATI*/null", open(f"{OUT}/dati.json").read()))
    os.replace(f"{OUT}/index.html.tmp", f"{OUT}/index.html")


def sorgenti():
    return PROVE + [TABELLA] + glob.glob(f"{GIUDIZIO}/uscite/*.jsonl")


if __name__ == "__main__":
    scrivi()
