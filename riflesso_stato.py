# riflesso_stato.py: parte di riflesso.py, spostata con manutenzione/sposta_riflesso.py (PIANO-DIVISIONE-RIFLESSO.md).
import threading
import time


UPSTREAM = ("127.0.0.1", 8090)


_vettore_vivo = [False]
# issue #3, punto A: il vettore è unico per tutto il server. Chi lo
# accende tiene questo lock fino a calma(), e ogni inoltro aspetta che sia libero:
# nessun'altra richiesta passa mentre il ricordo si colora.
_vettore_lock = threading.Lock()
_vettore_di = [None]   # 11/11: il watchdog dell'ultimo vettore di un ricordo (quello rimandato non spegne il successivo)


_vettori = {"chat": [], "pensatoio": []}   # flusso -> [{emo, dose, nato, durata}]
_vissuto = {"chat": 0.0, "pensatoio": 0.0}  # secondi passati con la cache nello slot
_caricato = [time.time()]                   # quando la cache di _cw[0] e' entrata nello slot
# 18/10: se la chat interrompe il pensatoio, il gateway rifa' il giro dall'ultima
# risposta di un tool, quindi il vettore torna alla dose di quel momento, non a
# quella della pausa. E un pensiero nuovo ricomincia la cache del pensatoio: i suoi
# vettori tornano allo stato di default.
_punto = {}             # flusso -> orologio all'inizio della richiesta in corso (fine dell'ultimo tool)
_interrotto = set()     # flussi tagliati a meta' generazione
_pens_conv = [None]     # pensiero in corso nel pensatoio (impronta del primo messaggio)


CONSEGNE_MAX = 50       # conversazioni ricordate (le più recenti)


# --- doppia CW con hot-swap (19/07, design di progetto: DESIGN-DOPPIA-CW.md).
# Due cache persistenti, mai attive insieme: chat.kv vive per sempre,
# pensatoio.kv si ricicla a ogni pensiero. Il flusso si riconosce dal primo
# messaggio user: "[mittente] " = sessione Matrix (chat), preambolo cron con
# skill blocco-appunti = pensatoio, tutto il resto (Thornhill, rassegne) =
# estraneo e passa trasparente: lo slot si sporca, i file .kv mai.
# Misurato 19/07 su 797MB/35k token: save 185ms, restore 122ms.
KV_FLUSSO = {"chat": "chat.kv", "pensatoio": "pensatoio.kv"}
SOGLIA_CW = 100_000     # chat: oltre, switch di CW a fine turno (K4); pensatoio: avviso di spazio in coda (K17)
SOGLIA_AVVISO = 90_000  # K4 (10/11): fra 90k e 100k l'avviso nella chiamata del riepilogo


_cw = ["chat"]          # cosa c'è nello slot adesso (al deploy corrente->chat)
_cw_lock = threading.Lock()
_pens_vivi = []         # socket del pensatoio verso :8090: la chat li taglia
_chat_calda = [0.0]     # ultima attività chat (fine risposta o typing visto)
_chat_in_volo = [0]     # richieste della chat in corso (issue #3 punto A): il pensatoio aspetta
_altro_in_volo = [0]    # 10/11: richieste estranee (cron, servizi di Hermes) che usano lo slot: il riepilogo aspetta


_altro_lock = threading.Lock()   # anche per _chat_in_volo (revisione 3.5.3, punto 4: due thread)
_salva_ultimo = [None]   # il salvataggio della chat piu' recente: il riepilogo lo aspetta (revisione 3.5.3, punto 2)
_tok_cw = {"chat": 0, "pensatoio": 0}
_avvisato_cw = {"chat": False, "pensatoio": False}
_fonte_utente = [False]   # 1.24.0 (PIANO-1.24-FONTI.md): l'ultima richiesta della chat viene da un messaggio dell'utente
