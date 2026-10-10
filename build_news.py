"""Recolecta noticias de RSS, las reescribe con IA y genera data/news.json.

Uso:
    ANTHROPIC_API_KEY=... python scripts/build_news.py

Sin API key el script igual corre: guarda solo el titular y el enlace de cada
nota, sin resumen. Nunca copia el texto de los medios.
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "scripts" / "sources.json"
OUT = ROOT / "data" / "news.json"

MAX_PER_SECTION = int(os.getenv("MAX_PER_SECTION", "8"))
MAX_AGE_HOURS = int(os.getenv("MAX_AGE_HOURS", "72"))
MODEL = os.getenv("NEWS_MODEL", "claude-haiku-5-5")
USER_AGENT = "Mozilla/5.0 (compatible; ElPulsoBot/1.0)"

SYSTEM_PROMPT = """Eres redactor de un periódico digital en español dominicano neutro.
Recibes el titular, el medio y un fragmento de una nota publicada por otro medio.
Devuelve SOLO un JSON con dos campos:
- "titular": un titular nuevo, claro y sin sensacionalismo (máximo 14 palabras).
- "resumen": 2 o 3 oraciones con tus propias palabras (máximo 60 palabras).
Reglas: usa únicamente lo que está en el texto recibido; no inventes cifras, nombres
ni declaraciones; no copies frases textuales del original; si el fragmento es muy
corto, escribe un resumen corto en vez de rellenar."""


def limpiar(texto: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", unescape(texto)).strip()


def item_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def cargar_previo() -> dict:
    if not OUT.exists():
        return {}
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if data.get("demo"):
        return {}
    return {it["id"]: it for sec in data.get("sections", []) for it in sec["items"]}


def leer_feed(feed: dict, limite: datetime) -> list[dict]:
    try:
        parsed = feedparser.parse(feed["url"], agent=USER_AGENT)
    except Exception as exc:  # red caída, XML roto, etc.
        print(f"[aviso] {feed['name']}: {exc}", file=sys.stderr)
        return []
    if not parsed.entries:
        print(f"[aviso] {feed['name']}: sin notas ({feed['url']})", file=sys.stderr)
        return []
    notas = []
    for e in parsed.entries:
        url = e.get("link")
        titulo = limpiar(e.get("title", ""))
        if not url or not titulo:
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        fecha = datetime(*t[:6], tzinfo=timezone.utc) if t else datetime.now(timezone.utc)
        if fecha < limite:
            continue
        notas.append({
            "id": item_id(url),
            "source": feed["name"],
            "url": url,
            "original_title": titulo,
            "snippet": limpiar(e.get("summary", ""))[:600],
            "published": fecha.isoformat(),
        })
    return notas


def intercalar(listas: list[list[dict]]) -> list[dict]:
    """Alterna entre medios para que una sola fuente no domine la pestaña."""
    resultado, vistos = [], set()
    listas = [sorted(l, key=lambda n: n["published"], reverse=True) for l in listas]
    for i in range(max((len(l) for l in listas), default=0)):
        for l in listas:
            if i < len(l) and l[i]["id"] not in vistos:
                vistos.add(l[i]["id"])
                resultado.append(l[i])
    return resultado


def reescribir(cliente, nota: dict) -> dict:
    """Pide a Claude un titular y resumen propios. Si falla, deja solo el enlace."""
    if cliente is None:
        return {"title": nota["original_title"], "summary": ""}
    contenido = (
        f"Medio: {nota['source']}\n"
        f"Titular original: {nota['original_title']}\n"
        f"Fragmento: {nota['snippet'] or '(sin fragmento)'}"
    )
    try:
        r = cliente.messages.create(
            model=MODEL,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": contenido}],
        )
        texto = "".join(b.text for b in r.content if b.type == "text")
        datos = json.loads(re.search(r"\{.*\}", texto, re.S).group(0))
        return {"title": datos["titular"].strip(), "summary": datos["resumen"].strip()}
    except Exception as exc:
        print(f"[aviso] no se pudo reescribir '{nota['original_title'][:40]}': {exc}", file=sys.stderr)
        return {"title": nota["original_title"], "summary": ""}


def main() -> None:
    config = json.loads(SOURCES.read_text(encoding="utf-8"))
    previo = cargar_previo()
    limite = datetime.now(timezone.utc) - timedelta(hours=MAX_AGE_HOURS)

    cliente = None
    if os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        cliente = anthropic.Anthropic()
    else:
        print("[aviso] Sin ANTHROPIC_API_KEY: se guardan solo titulares y enlaces.", file=sys.stderr)

    secciones = []
    for sec in config["sections"]:
        candidatas = intercalar([leer_feed(f, limite) for f in sec["feeds"]])[:MAX_PER_SECTION]
        items = []
        for nota in candidatas:
            if nota["id"] in previo and previo[nota["id"]].get("summary"):
                items.append(previo[nota["id"]])  # ya reescrita antes, no se paga otra vez
                continue
            nueva = reescribir(cliente, nota)
            items.append({
                "id": nota["id"],
                "section": sec["id"],
                "title": nueva["title"],
                "summary": nueva["summary"],
                "source": nota["source"],
                "url": nota["url"],
                "published": nota["published"],
            })
        if not items:  # si todos los feeds fallaron, conserva lo anterior
            items = [it for it in previo.values() if it.get("section") == sec["id"]]
        secciones.append({"id": sec["id"], "name": sec["name"], "items": items})
        print(f"{sec['name']}: {len(items)} notas")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"updated": datetime.now(timezone.utc).isoformat(), "demo": False, "sections": secciones},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
