#!/usr/bin/env python3
# Avatar emotivo dell'agente (23/07, l'utente): tinta piena del colore dell'emozione
# DOMINANTE dello stato, con la sua emoji e la sigla di 3 lettere disegnate
# sopra. Sorgente colori/emoji/sigle: emozioni.json. Stato: stato-emotivo.json.
# Uso: avatar-emotivo.py [out.png]   (default /tmp/avatar.png)
import json
import sys

# PIL importata DENTRO le funzioni che disegnano (28/07): cosi' il watcher
# (python di sistema, senza PIL) puo' importare dominante() senza crollare.

EMO = "/data/memoria-episodica-affettiva/emozioni.json"
STATO = "/data/workspace/memoria/stato-emotivo.json"
F_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"
F_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LATO = 256


EUTIMIA = "/data/workspace/memoria/eutimia.json"


def dominante():
    """28/07 (censimento fase 0): l'emozione dominante e' quella che si
    SCOSTA di piu' dalla baseline, non il massimo assoluto: prima l'avatar
    mostrava quasi sempre il setpoint (serenity 0.6) invece dell'emozione
    viva. La baseline viene dall'omeostato (eutimia.json).
    02/08: solo scostamenti POSITIVI (emozione piu' viva del normale):
    con l'abs() una rage a -0.70 tingeva l'avatar di furia al contrario."""
    cat = {r["en"]: r for r in json.load(open(EMO))}
    stato = json.load(open(STATO))["stato"]
    try:
        base = json.load(open(EUTIMIA)).get("baseline", {})
    except (OSError, ValueError):
        base = {}
    en = max((e for e in stato if e in cat),
             key=lambda e: stato[e] - base.get(e, 0.0))
    return cat[en], stato[en]


def _hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _ink(bg):
    # testo scuro su sfondo chiaro, bianco su scuro (luminanza percettiva)
    lum = 0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]
    return (20, 24, 30) if lum > 150 else (255, 255, 255)


def _emoji(glyph, px):
    """rende un'emoji a colori su RGBA px*px (NotoColorEmoji ha una sola
    taglia bitmap, 136: si disegna lì e si ridimensiona)."""
    NAT = 109   # unica taglia bitmap di NotoColorEmoji (interrogata dal font)
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(F_EMOJI, NAT)
    im = Image.new("RGBA", (NAT, NAT), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    try:
        d.text((NAT / 2, NAT / 2), glyph, font=f, embedded_color=True, anchor="mm")
    except Exception:
        return None
    return im.resize((px, px), Image.LANCZOS)


def genera(rec, path):
    bg = _hexrgb(rec["colore"])
    ink = _ink(bg)
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (LATO, LATO), bg)
    dr = ImageDraw.Draw(im)
    # emoji in alto, centrata
    em = _emoji(rec["emoji"], 118)
    if em is not None:
        im.paste(em, ((LATO - 118) // 2, 26), em)
    # sigla di 3 lettere in basso, grande e in grassetto
    f = ImageFont.truetype(F_BOLD, 76)
    dr.text((LATO / 2, 186), rec["tag"], font=f, fill=ink, anchor="mm")
    im.save(path)
    return path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/avatar.png"
    rec, val = dominante()
    genera(rec, out)
    print(f"{rec['it']} ({rec['en']}, {val:.2f}) -> {rec['tag']} {rec['emoji']} "
          f"{rec['colore']} -> {out}")
