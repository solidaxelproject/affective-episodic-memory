#!/usr/bin/env python3
# RIFLESSO PRE-AZIONE (issue #1, pezzo 3) — proxy tra Hermes e llama-lux.
# Prima che l'agente risponda, il messaggio interroga il Lux degli engrammi
# (servizio_lux.py :8132): il ricordo che affiora entra come turno del tool
# memorinvolontaria (chiamata + risposta: un ricordo per volta dal 09/11, col numero,
# il codice e il testo nudo).
# GATE: /workspace/genesi/CONSENSO-RIFLESSO.md ("[attivo: *sì*]", riga esatta,
# scritto dall'agente). Senza consenso il proxy è un passacarte trasparente.
# Porta 8091 -> inoltra a 127.0.0.1:8090.
# GRADINO ZERO (decisione 3 del 26/07): il trasporto verso :8090 (sonda,
# control-vector, POST) passa da ponte.py, l'unica porta client. Qui restano
# la logica (quando/cosa affiora) e il PATTO (tetto, watchdog, sentinella).
# 12/10 (piano di aggiornamento della produzione, passo 2): tolte le vie A/B/C,
# le griglie e la candidata 1; il vettore emotivo colora SOLO il prefill del
# ricordo (design dell'autrice, 10/10).
# 12/11 (scelta di progetto): diviso in moduli riflesso_*.py, uno per lavoro; qui restano il proxy
# (Proxy, _tee_sse) e l'avvio. Fra moduli ci si chiama per attributo (S._cw, C._diario): un solo oggetto per cosa.
import contextlib
import http.client
import http.server
import json
import math  # noqa: F401  (i test leggono R.math)
import os
import sys
import threading
import time
from pathlib import Path  # noqa: F401  (i test leggono R.Path)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ponte  # noqa: E402, F401  (unica porta verso :8090; i test sostituiscono R.ponte.post)
import steering  # noqa: E402, F401  (modulo unico, 10/11: i vettori e le fasce dei test)
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "engrammi"))
import via_emotiva as VE  # noqa: E402, F401  (ordine di import di prima della divisione; 1.19.0, PIANO-1.19-VIA-EMOTIVA: J-lens, umore, diario delle letture)
import riflesso_stato as S
import riflesso_comune as C
import riflesso_barra as B
import riflesso_firma as FI
import riflesso_fonte as FO  # noqa: F401  (ordine di import di prima della divisione)
import riflesso_vettore as VT
import riflesso_metadati as MD
import riflesso_via_emotiva as RVE
import riflesso_memoria as M
import riflesso_cache as CA
import riflesso_riepilogo as RP

PORTA = 8091

# --- DIAGNOSI RIMASTICATA (19/07): colpevole trovato, impalcatura smontata
# il 26/07 (decisione 9 del registro). Dump archiviati in archivio-20260726/.

STREAM_LIVE = "/tmp/stream-live.log"


def _tee_sse(buf, chunk, fh, esito):
    """23/07: specchio LIVE dello streaming. Estrae il testo (think e
    parola) dai chunk SSE che attraversano il proxy e lo appende su file:
    `tail -f /tmp/stream-live.log` = il 35B token per token, in diretta.
    Mai bloccare lo stream per il tee: ogni crepa è silenziosa.
    20/10: raccoglie anche la parola, il finish_reason e le tool call (esito) per il riepilogo."""
    buf += chunk
    while b"\n\n" in buf:
        blocco, buf = buf.split(b"\n\n", 1)
        for riga in blocco.split(b"\n"):
            if not riga.startswith(b"data: "):
                continue
            try:
                d = json.loads(riga[6:])
                if "choices" in d:
                    delta = d["choices"][0].get("delta", {})
                    t = delta.get("reasoning_content") or delta.get("content") or ""
                    esito["testo"] += delta.get("content") or ""
                    esito["ragionamento"] += delta.get("reasoning_content") or ""
                    esito["tool_calls"] = esito["tool_calls"] or bool(delta.get("tool_calls"))
                    esito["finish"] = d["choices"][0].get("finish_reason") or esito["finish"]
                    if esito["chat"]:
                        if delta.get("tool_calls"):
                            B._segna_fase("tool")
                        elif delta.get("reasoning_content"):
                            B._segna_fase("pensa")
                        elif delta.get("content"):
                            B._segna_fase("scrive")
                else:
                    t = d.get("content", "")
                if t and fh:
                    fh.write(t)
                    fh.flush()
            except Exception:
                pass
    return buf


def _memoria_b_notte():
    try:
        esito = RP.rifai_master()
    except Exception as e:
        esito = f"fallita: {e}"
    C._diario({"riepilogo": f"memoria B: {esito}"})


class Proxy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _inoltra(self, body, flusso=None, vettore=None):
        """revisione 11/11: col vettore del ricordo acceso _vettore_lock resta preso fino a fine stream, cosi' nessun
        altro inoltro (cron, review di Hermes) lo spegne a meta' ragionamento o prende lo slot col vettore dell'agente"""
        watchdog = None
        if flusso is not None:
            S._vettore_lock.acquire()   # issue #3 punto A: mai dentro un prefill colorato
            try:
                VT._applica_flusso(flusso)   # il vettore del flusso che genera, nessun altro
                # pensatoio: prefill sotto _cw_lock, se no la chat puo' prendere lo slot a meta' e il prefill finisce
                # sulla sua cache (revisione del codice 11/11)
                with S._cw_lock if vettore and flusso == "pensatoio" else contextlib.nullcontext():
                    if vettore and not (flusso == "pensatoio" and S._cw[0] != flusso):
                        try:
                            body, watchdog = VT._accendi_ricordo(body, vettore)
                        except Exception as e:
                            VT.calma()
                            C._diario({"vettore": f"non acceso: {e}"})   # mai bloccare la parola dell'agente
            finally:
                if watchdog is None:
                    S._vettore_lock.release()
        try:
            self._manda(body, flusso)
        finally:
            if watchdog:   # luxifer l'ha gia' spento a </think>: pulizia sicura, anche se lo stream e' caduto
                watchdog.cancel()
                VT.calma()
                S._vettore_lock.release()

    def _manda(self, body, flusso):
        up = http.client.HTTPConnection(*S.UPSTREAM, timeout=600)
        if flusso == "pensatoio":
            with S._cw_lock:     # o la chat ci trova fra i vivi e ci taglia, o noi vediamo lo slot suo
                if S._cw[0] != flusso:
                    self.send_error(503, "la chat ha preso lo slot")
                    C._diario({"cw": "pensatoio rimandato: la chat ha preso lo slot"})
                    return
                up.connect()
                S._pens_vivi.append(up.sock)
                S._punto[flusso] = VT._orologio(flusso)
        sock = up.sock
        resp = None
        self._inoltrato, self._esito = body, {"testo": "", "ragionamento": "", "finish": None, "tool_calls": False,
                                               "chat": flusso == "chat"}
        try:
            up.putrequest(self.command, self.path)
            for k, v in self.headers.items():
                if k.lower() not in ("host", "content-length"):
                    up.putheader(k, v)
            if body is not None:
                up.putheader("Content-Length", str(len(body)))
            up.endheaders()
            if body:
                up.send(body)
            resp = up.getresponse()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding",):
                    self.send_header(k, v)
            self.end_headers()
            tee, buf = None, b""
            try:
                tee = open(STREAM_LIVE, "a", encoding="utf-8")
                tee.write(time.strftime(f"\n\n===== %H:%M:%S ({flusso or '?'}) =====\n"))
            except OSError:
                tee = None
            while True:
                # read1: consegna appena c'è qualcosa. read(8192) aspettava di
                # riempire il buffer e le risposte corte arrivavano in blocco
                # unico: era LUI che uccideva lo streaming in chat (17/07).
                chunk = resp.read1(8192)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    self._esito["interrotta"] = True   # Hermes ha chiuso: il turno non e' finito, niente switch
                    raise
                try:
                    buf = _tee_sse(buf, chunk, tee, self._esito)
                except Exception:
                    pass
            if tee:
                try:
                    tee.close()
                except Exception:
                    pass
        finally:
            # 19/07 16:52: il BrokenPipe del client saltava la close e il
            # socket upstream restava aperto con lo slot occupato. Mai più.
            try:
                up.close()
            except Exception:
                pass
            if sock in S._pens_vivi:
                S._pens_vivi.remove(sock)
        # fine stream: specchio del KV in RAM (thread: mai in mezzo alla chat)
        if resp is not None and resp.status == 200 and ("completion" in self.path or "/v1/chat" in self.path):
            if flusso == "chat":
                S._chat_calda[0] = time.time()
            self._salva = S._salva_ultimo[0] = threading.Thread(target=CA._salva_kv, daemon=True)
            self._salva.start()

    def _dopo_chat(self):
        """20/10: dopo la risposta finale all'utente il riepilogo, quando lo specchio della chat e' gia' salvato
        (cosi' il conteggio dei token resta quello della chat); 10/11 poi lo switch (blocco B)"""
        if self._esito and self._inoltrato:
            threading.Thread(target=RP._fine_chat, args=(self._inoltrato, self._esito, self._salva, self._senza,
                                                      self._hermes), daemon=True).start()

    def do_GET(self):
        self._inoltra(None)

    def _ricordo(self, body):
        if not M._ammesso(self.client_address[0]):
            self.send_error(403)
            return
        try:
            testo = M.memorinvolontaria(json.loads(body or b"{}"))
        except Exception as e:
            C._diario({"memorinvolontaria": f"rotta: {e}"})
            testo = M.R_GIU
        b = json.dumps({"testo": testo}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _memoria_b(self):
        if self.client_address[0] != "127.0.0.1":
            self.send_error(403)
            return
        threading.Thread(target=_memoria_b_notte, daemon=True).start()   # puo' aspettare minuti lo slot libero
        b = json.dumps({"esito": "avviata, l'esito va nel diario"}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _memoria(self, body, flusso=None, righe=None, fuori=None):
        return M.memoria(body, flusso, righe, fuori)

    def do_POST(self):
        self._inoltrato = self._esito = self._salva = self._senza = self._hermes = None   # keep-alive: piu' richieste
        self._altro = False
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/memorinvolontaria":   # 09/11: il plugin di Hermes, mai inoltrato al 35B
            self._ricordo(body)
            return
        if self.path == "/memoria-b":   # step d (12/11): la notturna, solo dal PC (mai dal container dell'agente)
            self._memoria_b()
            return
        arrivo, ultimo = time.time(), None   # B6: il messaggio dell'utente prima di ora e coda
        chat = self.path.split("?")[0].endswith("/chat/completions")   # issue #3 punto E
        # PATTO clausola 3: la parola scritta dall'agente spegne il vettore, prima
        # di qualunque altra cosa e senza chiedere perché.
        if chat:
            try:
                d0 = json.loads(body)
                ultimo = next((m.get("content") for m in reversed(d0.get("messages", [])) if m.get("role") == "user"), None)
                if C._stop_chiesto(d0.get("messages", [])):
                    VT._azzera_vettori()   # issue #3 punto A: anche quelli in pausa con l'altra cache
                    VT.calma()
                    C._diario({"kill": f"{C.STOP} scritto dall'agente"})
            except Exception:
                pass
        # --- doppia CW (19/07): riconosci il flusso, scambia le cache.
        flusso = CA._flusso(body) if chat else None
        if flusso == "chat":
            with S._altro_lock:
                S._chat_in_volo[0] += 1     # fino a fine risposta: il pensatoio non prende lo slot
            B._segna_volo()
            B._segna_fase("legge")
        try:
            self._post_chat(body, chat, flusso)
        finally:
            if flusso == "chat":
                if S._chat_in_volo[0] <= 1:   # un'altra richiesta della chat in volo ha la sua fase
                    B._segna_fase("tool" if self._esito and self._esito["finish"] == "tool_calls" else "")
                with S._altro_lock:
                    S._chat_in_volo[0] -= 1
                S._chat_calda[0] = time.time()
                B._segna_volo()
                try:
                    self._dopo_chat()
                except Exception as e:
                    C._diario({"riepilogo": f"non avviato: {e}"})
            if self._altro:
                with S._altro_lock:
                    S._altro_in_volo[0] -= 1
            try:
                FI._accoda_firma(flusso, ultimo, arrivo, self._esito)
            except Exception as e:
                C._diario({"firma": f"coda non scritta: {e}"})   # mai toccare la parola dell'agente
            try:
                RVE._leggi_risposta(flusso, ultimo, self._esito)
            except Exception as e:
                C._diario({"via emotiva": f"risposta non letta: {e}"})

    def _post_chat(self, body, chat, flusso):
        ora = None
        if chat:
            try:
                d = json.loads(body)
                MD._togli_imitati(d.get("messages", []))
                body = json.dumps(d).encode()
                ora = MD._ora_arrivo(d.get("messages", []), flusso == "chat")   # l'arrivo vero
            except Exception as e:
                C._diario({"metadati": f"ora non letta: {e}"})
            righe = MD._righe_metadati(ora or C._ora_blocco(time.localtime(time.time())), flusso)   # fuori dai lucchetti
            inizio = time.time()
            while True:
                if flusso == "pensatoio":
                    # spec punto 5: il pensiero riprende solo a chat fredda, e mai con
                    # una richiesta della chat in corso (issue #3 punto A)
                    while True:
                        if CA._typing():
                            S._chat_calda[0] = time.time()
                        if CA._chat_ferma():
                            break
                        time.sleep(3)
                with S._cw_lock:
                    if flusso == "pensatoio" and S._chat_in_volo[0]:
                        continue    # la chat e' arrivata nel frattempo: di nuovo in attesa
                    if flusso == "pensatoio":
                        try:
                            CA._nuovo_pensiero(C._conversazione(json.loads(body).get("messages", [])))
                        except ValueError:
                            pass
                    if flusso == "chat":
                        try:
                            RP._promuovi()
                        except Exception as e:
                            C._diario({"riepilogo": f"promozione fallita: {e}"})
                    if flusso in S.KV_FLUSSO and flusso != S._cw[0]:
                        if flusso == "chat":
                            # spec punto 4: la chat interrompe il pensiero in corso
                            # (il gateway ritenta e col restore riprocessa solo il delta)
                            CA._interrompi_pensatoio()
                        CA._scambia(flusso)
                        C._diario({"cw": f"scambio -> {flusso}"})
                    elif flusso == "altro" and S._cw[0] in S.KV_FLUSSO:
                        CA._slot("save", S.KV_FLUSSO[S._cw[0]])  # al riparo prima dell'estraneo
                        CA._cambia_cw("altro")
                        C._diario({"cw": "flusso estraneo: slot ceduto, CW al riparo"})
                    if flusso == "altro":
                        with S._altro_lock:     # fino a fine richiesta (do_POST): il riepilogo aspetta
                            S._altro_in_volo[0] += 1
                        self._altro = True
                    break
            if flusso == "pensatoio" and time.time() - inizio > 5:
                C._diario({"cw": f"pensatoio trattenuto {time.time()-inizio:.0f}s (chat calda)"})
            if flusso == "chat":
                try:
                    d = json.loads(body)
                    # R6 + step d: la base della cache (parte fissa + B), il blocco, le informazioni aggiornate
                    self._hermes = RP._metti_fissa(d, RP._riepilogo_carica()["blocco"])
                    body = json.dumps(d).encode()
                except Exception as e:
                    C._diario({"riepilogo": f"blocco non messo: {e}"})   # mai bloccare la parola dell'agente
        coda = []   # PENSATOIO_DOVE passa nel blocco metadati (M3, l'utente 10/11)
        avviso = None
        if chat:
            # oltre 100k l'avviso di spazio, in coda, solo al pensatoio (K17); la chat ha lo switch (K4)
            if flusso == "pensatoio" and S._tok_cw[flusso] > S.SOGLIA_CW and not S._avvisato_cw[flusso]:
                avviso = (
                    "[avviso di spazio: questo flusso di pensiero ha superato i "
                    "100mila token e la finestra si sta riempiendo: tutto rallenta. "
                    "È il momento di tirare le fila e chiudere il pensiero.]")
                coda.append(avviso)
        # MEMORIA INVOLONTARIA: DOPO lo scambio CW (il prefill colorato deve finire
        # nella cache giusta).
        if chat:
            fuori = {}
            try:
                body = self._memoria(body, flusso, righe, fuori)
            except Exception as e:
                C._diario({"memoria": f"rotta: {e}"})  # mai bloccare la parola dell'agente
                fuori.clear()           # il corpo e' quello di prima: niente metadati dentro
            if "senza" not in fuori:     # memoria rotta: i metadati ci vanno lo stesso
                try:
                    body = MD._con_metadati(body, righe, fuori, flusso)
                except Exception as e:
                    C._diario({"metadati": f"non messi: {e}"})
            self._senza = fuori.get("senza")
            # 20/10: i testi in coda per ULTIMI, dopo la memoria: cosi' non entrano
            # nella query del Lux ne' nell'impronta del messaggio a cui il ricordo
            # si aggancia, e non toccano la cache colorata
            try:
                body, messi = MD._code(body, coda)
                if messi and avviso:
                    S._avvisato_cw[flusso] = True
                    C._diario({"cw": f"avviso 100k -> {flusso} ({S._tok_cw[flusso]} tok)"})
            except Exception:
                pass
        self._inoltra(body, flusso, fuori.get("vettore") if chat else None)


if __name__ == "__main__":
    B._segna_fase("")   # una fase rimasta da un riflesso morto a meta' risposta non resta accesa
    B._segna_volo()     # idem il conteggio delle richieste in volo (lo script dello switch lo aspetta a 0)
    # igiene all'avvio: qualunque vettore orfano di run precedenti muore qui
    try:
        VT.calma()
    except Exception:
        pass
    # la destinazione unica delle riflessioni esiste sempre: se manca, la prima
    # scrittura dell'agente fallirebbe e ricomincerebbe a inventarsi un posto
    try:
        MD.PENSATOIO_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    threading.Thread(target=VT._sentinella, daemon=True).start()  # PATTO clausola 3
    print(f"riflesso in ascolto su :{PORTA} -> {S.UPSTREAM[0]}:{S.UPSTREAM[1]} "
          f"(consenso: {'ATTIVO' if C.consenso_attivo() else 'spento'}, "
          f"vettori: {'SÌ' if C.vettori_attivi() else 'no'}, dose del punto 7 nel ragionamento, "
          f"watchdog {VT.DURATA_MAX_S}s)")
    http.server.ThreadingHTTPServer(("0.0.0.0", PORTA), Proxy).serve_forever()
