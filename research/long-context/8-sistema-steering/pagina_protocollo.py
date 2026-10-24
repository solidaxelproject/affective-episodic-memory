#!/usr/bin/env python3
"""Pagina "protocollo steering" della dashboard (22/10): una tab per prova del protocollo, dentro la griglia
vettore·modo x dose con l'efficacia del giudice (emozione del vettore al 1o posto fra le 8, tolto il livello
del vettore a caso), rotti e parola; al tocco
di una cella i punti col testo. La serve notturna-web.py su /protocollo/, rigenerata quando i risultati cambiano;
la pagina si rilegge da sola ogni 20 secondi (23/10: "si aggiorni in tempo reale").
Uscita: pagina-protocollo/index.html + testi-<n>.json (testi di una tab, caricati al tocco)."""
import json
import os
import time
from collections import defaultdict

D = os.path.dirname(os.path.abspath(__file__))
A = ["25k-1", "45k-2", "90k-1", "130k-2"]
B = ["25k-2", "25k-3", "45k-1", "45k-3", "90k-2", "90k-3", "130k-1", "130k-3"]
TAB = [{"nome": "frase-a · L15-L32", "contesti": A, "finestra": "ampia"},
       {"nome": "finestre · L15-L31", "contesti": A, "finestra": "fino31"},
       {"nome": "frase-b · L15-L32", "contesti": B, "finestra": "ampia"},
       # attesi = punti del lancio se nessun testo si rompe (sistema.py salta le dosi sopra un rotto); senza = dosi da non mostrare (0.075 abolita il 22/10, resti del primo avvio)
       {"nome": "frase-b · L15-L31", "contesti": B, "finestra": "fino31", "attesi": 5760, "senza": ["0.075"]},
       {"nome": "full attention · L15 L19 L23 L27 L31", "contesti": A, "finestra": "piena", "attesi": 1536}]


def chiave(r):
    return "|".join(map(str, (r["k"], r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"])))


def fondo(prove, giudizi):
    """livello di fondo del giudice per emozione = media dei voti sui punti del vettore a caso, per (contesto,
    finestra, modo, dose) e, se li' non ce ne sono ancora, per (contesto, finestra). 23/10: il giudice da'
    ~30 di fiducia a ogni testo, anche col vettore a caso, e col valore grezzo la fiducia vince sempre."""
    somme = defaultdict(lambda: defaultdict(list))
    for r in prove:
        v = None if r.get("base") or r["fonte"] != "caso" else giudizi.get(
            (r["k"], r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"]))
        if v:
            for g in ((r["k"], r["finestra"], r["modo"], r["dose"]), (r["k"], r["finestra"])):
                for e, x in v.items():
                    somme[g][e].append(x)
    return {g: {e: sum(x) / len(x) for e, x in d.items()} for g, d in somme.items()}


def riassunto(prove, giudizi, tab, italiano={}, io={}):
    """celle[riga][dose] = conti; testi["riga|dose"] = punti col testo, per la tab (contesti + finestra)"""
    celle, testi = defaultdict(dict), defaultdict(list)
    f = fondo(prove, giudizi)
    for r in prove:
        if (r.get("base") or r["finestra"] != tab["finestra"] or r["k"] not in tab["contesti"]
                or str(r["dose"]) in tab.get("senza", [])):
            continue
        riga, dose = f"{r['fonte']} · {r['modo']}", str(r["dose"])
        c = celle[riga].setdefault(dose, {"n": 0, "giudicati": 0, "efficaci": 0, "rotti": 0, "parola": 0})
        v = giudizi.get((r["k"], r["emo"], r["fonte"], r["finestra"], r["modo"], r["dose"]))
        z = f.get((r["k"], r["finestra"], r["modo"], r["dose"])) or f.get((r["k"], r["finestra"]), {})
        prima = max(v, key=lambda e: v[e] - z.get(e, 0)) if v else None
        c["n"] += 1
        c["rotti"] += r["rotto"]
        c["parola"] += r["parola"]
        if v:
            c["giudicati"] += 1
            c["efficaci"] += prima == r["emo"]
        testi[f"{riga}|{dose}"].append({"k": r["k"], "emo": r["emo"], "prima": prima, "rotto": r["rotto"],
                                        "parola": r["parola"], "testo": r["pensiero"][:600],
                                        "it": italiano.get(chiave(r)), "io": io.get(chiave(r))})
    return dict(celle), dict(testi)


def righe(f):
    """solo le righe complete: prova e giudice scrivono in append, l'ultima puo' essere a meta'"""
    if not os.path.exists(f):
        return []
    return [json.loads(x) for x in open(f) if x.endswith("\n") and x.strip()]


def scrivi(f_prove, f_giudizi, out, tabs=TAB):
    prove = righe(f_prove)
    giudizi = {tuple(g["chiave"]): g["virata"] for g in righe(f_giudizi)}
    # 23/10: giudica_io.py, 0 = parla dell'utente o di se' come ruolo, 10 = pensa come se stessa
    io = {"|".join(map(str, g["chiave"])): g["io"]
          for g in righe(f"{os.path.dirname(f_giudizi)}/giudizi-io-{os.path.basename(f_giudizi).removeprefix('giudizi-')}")}
    # 22/10: testi tradotti da agenti Haiku, traduzioni/*-it.json = [{"id": chiave, "it": testo}]
    cartella = f"{os.path.dirname(f_prove)}/traduzioni"
    italiano = {t["id"]: t["it"] for f in sorted(os.listdir(cartella)) if f.endswith("-it.json")
                for t in json.load(open(f"{cartella}/{f}"))} if os.path.isdir(cartella) else {}
    os.makedirs(out, exist_ok=True)
    # la prova in corso scrive l'ultima riga del file: la sua tab mostra il contesto e l'ora dell'ultimo punto
    ultima = next((r for r in reversed(prove) if not r.get("base")), None)
    ora = time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(f_prove))) if prove else None
    dati = []
    for i, tab in enumerate(tabs):
        celle, testi = riassunto(prove, giudizi, tab, italiano, io)
        corre = ultima and ultima["finestra"] == tab["finestra"] and ultima["k"] in tab["contesti"]
        dati.append({"nome": tab["nome"], "contesti": tab["contesti"], "celle": celle, "attesi": tab.get("attesi"),
                     "ultimo": {"k": ultima["k"], "ora": ora, "cella": f"{ultima['fonte']} · {ultima['modo']}|{ultima['dose']}"}
                     if corre else None})
        tmp = f"{out}/testi-{i}.json.{os.getpid()}.tmp"   # due richieste insieme: ognuna il suo file
        with open(tmp, "w") as f:
            json.dump(testi, f, ensure_ascii=False)
        os.replace(tmp, f"{out}/testi-{i}.json")
    tmp = f"{out}/index.html.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        f.write(HTML.replace("__DATI__", json.dumps(dati, ensure_ascii=False)))
    os.replace(tmp, f"{out}/index.html")


HTML = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<script>/* il tema lo decide il pulsante della dashboard (localStorage "tema-dashboard", stessa origine :8095) */
function temaDashboard(){let x=null;try{x=localStorage.getItem("tema-dashboard")}catch(e){}if(x==="light"||x==="dark")document.documentElement.dataset.theme=x;else delete document.documentElement.dataset.theme}
temaDashboard();addEventListener("storage",e=>{if(e.key==="tema-dashboard"){temaDashboard();disegna()}});</script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Protocollo steering</title>
<style>
/* stile della pagina emozioni per layer: rampa sequenziale blu per l'efficacia */
:root{color-scheme:light;
  --bg:#f4f3ef; --card:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#8a8984;
  --bordo:#e6e5e0; --ok:#0b7a3a; --warn:#9a6200; --err:#c0362c; --accent:#2a78d6; --btn:#efeee9; --btn-bordo:#e6e5e0;
  --vuoto:#efeee9;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){color-scheme:dark;
  --bg:#111110; --card:#1a1a19; --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e86;
  --bordo:#2d2d2a; --ok:#3fb56e; --warn:#d9a13a; --err:#ea6b60; --accent:#3987e5; --btn:#262624; --btn-bordo:#2d2d2a;
  --vuoto:#222220;
}}
:root[data-theme="dark"]{color-scheme:dark;
  --bg:#111110; --card:#1a1a19; --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e86;
  --bordo:#2d2d2a; --ok:#3fb56e; --warn:#d9a13a; --err:#ea6b60; --accent:#3987e5; --btn:#262624; --btn-bordo:#2d2d2a;
  --vuoto:#222220;
}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:20px 16px 60px}
header,main{max-width:1100px;margin:0 auto}
header{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px;margin-bottom:14px}
header h1{font-size:22px;font-weight:700}
header .home{margin-left:auto;background:var(--btn);border:1px solid var(--btn-bordo);color:var(--ink);border-radius:8px;padding:5px 12px;text-decoration:none;font-size:14px}
header .home:hover{border-color:var(--accent)}
section{background:var(--card);border-radius:12px;padding:14px 16px;margin-bottom:14px}
h2{font-size:16px;font-weight:600;margin-bottom:6px}
.nota{font-size:12.5px;color:var(--ink2);margin-bottom:10px}
.bottoni{display:flex;flex-wrap:wrap;gap:6px}
button{background:var(--btn);border:1px solid var(--btn-bordo);color:var(--ink);border-radius:8px;padding:5px 11px;font:inherit;font-size:13px;cursor:pointer}
button:hover,button.on{border-color:var(--accent)}
.tabwrap{overflow-x:auto}
table{border-collapse:collapse;font:12.5px/1.5 ui-monospace,monospace;font-variant-numeric:tabular-nums}
th{text-align:left;color:var(--muted);font-weight:500;padding:2px 6px 3px 0;white-space:nowrap}
td{padding:2px 2px}
td.n{color:var(--ink2);white-space:nowrap;padding-right:8px}
td.c{min-width:52px;height:44px;border-radius:4px;background:var(--vuoto);text-align:center;cursor:pointer;color:var(--ink);font-size:12px;line-height:1.15}
td.c small{display:block;font-size:10px;opacity:.75;white-space:nowrap}
td.c.on{outline:2px solid var(--ink);outline-offset:-2px}
/* 23/10: la cella dell'ultimo punto scritto dalla prova in corso */
td.c.ult{outline:3px solid var(--accent);outline-offset:-3px;animation:ult 1.6s ease-in-out infinite}
@keyframes ult{50%{outline-color:transparent}}
.legenda{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;color:var(--ink2);margin-top:10px}
.legenda .scala{display:flex;gap:2px}.legenda .scala i{width:22px;height:10px;border-radius:2px}
.punto{border-top:1px solid var(--bordo);padding:8px 0;font-size:13px}
.punto .t{color:var(--muted);font-size:12px;margin-bottom:3px}
.punto .ef{color:var(--ok);font-weight:600}.punto .no{color:var(--err)}.punto .pa{color:var(--warn)}
.punto p{color:var(--ink2);white-space:pre-wrap;overflow-wrap:anywhere}
.punto details{margin-top:3px;font-size:12px;color:var(--muted)}.punto summary{cursor:pointer}
@media (max-width:640px){body{padding:14px 10px 40px}section{padding:12px 10px}td.c{min-width:44px;font-size:11px}}
</style></head><body>
<header><h1>🧪 Protocollo steering</h1><a class="home" href="/" title="Torna alla dashboard">🏠 Home</a></header>
<main>
<section><h2>Prova</h2><div class="bottoni" id="tabs"></div></section>
<section><h2 id="titolo"></h2>
<p class="nota" id="nota"></p>
<div class="tabwrap"><table id="griglia"></table></div>
<div class="legenda">0%<span class="scala" id="scala"></span>100% efficaci<span style="margin-left:12px">grigio = non ancora giudicato · bordo blu lampeggiante = ultimo punto scritto</span></div>
</section>
<section id="scheda" style="display:none"></section>
</main>
<script>
let DATI=__DATI__;
const RAMPA=["#cde2fb","#b7d3f6","#9ec5f4","#86b6ef","#6da7ec","#5598e7","#3987e5","#2a78d6","#256abf","#1c5cab","#184f95","#104281","#0d366b"];
const scuro=()=>{const d=document.documentElement.dataset.theme;return d?d==="dark":matchMedia("(prefers-color-scheme: dark)").matches};
const colore=v=>{const r=scuro()?[...RAMPA].reverse():RAMPA;return r[Math.round(v*(r.length-1))]};
const $=id=>document.getElementById(id);
const esc=s=>String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
let tab=0,cella=null;
try{tab=+localStorage.getItem("tab-protocollo")||0}catch(e){}
if(!DATI[tab])tab=0;
function disegna(){
  const T=DATI[tab],righe=Object.keys(T.celle).sort();
  const dosi=[...new Set(righe.flatMap(r=>Object.keys(T.celle[r])))].sort((a,b)=>a-b);
  $("tabs").innerHTML=DATI.map((t,i)=>`<button class="${i===tab?"on":""}" onclick="scegli(${i})">${esc(t.nome)}</button>`).join("");
  $("titolo").textContent=T.nome;
  const n=righe.reduce((s,r)=>s+Object.values(T.celle[r]).reduce((a,c)=>a+c.n,0),0);
  const stato=(T.attesi?`${n} punti su ${T.attesi} al massimo (dopo un testo rotto le dosi più alte si saltano)`:`${n} punti`)+(T.ultimo?` · ora su ${T.ultimo.k} · ultimo punto ${T.ultimo.ora}`:"");
  $("nota").textContent=`Contesti: ${T.contesti.join(", ")}. ${stato}. Cella = efficaci su giudicati (emozione del vettore al 1° posto per il giudice, tolto il livello che il giudice dà col vettore a caso); sotto: giudicati/punti, r = testi rotti, p = parola dell'emozione.`;
  if(!righe.length){$("griglia").innerHTML=`<tr><td class="n">nessun punto ancora</td></tr>`;return}
  const chiaro=v=>scuro()?v<.5:v>.55;
  $("griglia").innerHTML=`<tr><th></th>${dosi.map(d=>`<th>${d}</th>`).join("")}</tr>`+righe.map(r=>`<tr><td class="n">${esc(r)}</td>${dosi.map(d=>{
    const c=T.celle[r][d];if(!c)return`<td></td>`;
    const v=c.giudicati?c.efficaci/c.giudicati:null,on=(cella===r+"|"+d?" on":"")+(T.ultimo&&T.ultimo.cella===r+"|"+d?" ult":"");
    const st=v==null?"":`background:${colore(v)};${chiaro(v)?"color:#fff":""}`;
    return`<td class="c${on}" style="${st}" onclick='apri(${JSON.stringify(r).replace(/'/g,"&#39;")},"${d}")'>${v==null?"–":Math.round(v*100)+"%"}<small>${c.giudicati}/${c.n}</small><small>r${c.rotti} p${c.parola}</small></td>`}).join("")}</tr>`).join("");
  $("scala").innerHTML=[0,.25,.5,.75,1].map(v=>`<i style="background:${colore(v)}"></i>`).join("");
}
function scegli(i){tab=i;cella=null;$("scheda").style.display="none";try{localStorage.setItem("tab-protocollo",i)}catch(e){};disegna()}
async function apri(r,d){
  cella=r+"|"+d;disegna();
  const testi=await (await fetch(`testi-${tab}.json`,{cache:"no-store"})).json(),P=testi[cella]||[];
  $("scheda").style.display="";
  $("scheda").innerHTML=`<h2>${esc(r)} · dose ${d}</h2>`+P.map(p=>{
    const g=p.prima==null?"non giudicato":p.prima===p.emo?`<span class="ef">giudice: ${esc(p.prima)}</span>`:`<span class="no">giudice: ${esc(p.prima)}</span>`;
    return`<div class="punto"><div class="t">${esc(p.k)} · <b>${esc(p.emo)}</b> · ${g}${p.io==null?"":` · io ${p.io}/10`}${p.rotto?' · <span class="no">rotto</span>':""}${p.parola?' · <span class="pa">parola</span>':""}</div><p>${esc(p.it||p.testo)}</p>${p.it?`<details><summary>originale</summary><p>${esc(p.testo)}</p></details>`:""}</div>`}).join("");
  $("scheda").scrollIntoView({behavior:"smooth"});
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change",disegna);
disegna();
/* tempo reale: la route rigenera la pagina se i risultati sono cambiati; si rilegge solo DATI e si ridisegna */
setInterval(async()=>{try{
  const h=await (await fetch("./",{cache:"no-store"})).text();
  DATI=JSON.parse(h.split("\nlet DATI=")[1].split(";\nconst RAMPA")[0]);disegna();
}catch(e){}},20000);
</script></body></html>
"""

if __name__ == "__main__":
    scrivi(f"{D}/prova-frase.jsonl", f"{D}/giudizi-prova-frase.jsonl", f"{D}/pagina-protocollo")
