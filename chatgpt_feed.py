"""Catálogo de Kosmos Cosmética para ChatGPT.

Lee los productos publicados de Tiendanube y arma el archivo con el formato de
OpenAI (https://developers.openai.com/commerce/specs/feed): una fila por
variante con precio, stock, imagen y link a la ficha. El workflow lo publica
todos los días en https://kosmos-cosmetica.github.io/kosmos-feed/chatgpt_productos.csv, que es
el link cargado en ChatGPT Business Hub → Productos → «Usar una URL alojada».

Solo datos públicos de la vidriera. Las credenciales llegan por variables de
entorno (secrets del repo): TN_STORE_ID, TN_ACCESS_TOKEN, TN_USER_AGENT.
"""
import csv, html, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

SALIDA = Path(__file__).resolve().parent / "publicar_feed"
ARCHIVO = "chatgpt_productos.csv"
MARCA = "Kosmos Cosmética"
CATEGORIA = "Health & Beauty > Personal Care > Cosmetics > Skin Care"
MONEDA = "ARS"
API = "https://api.tiendanube.com/2025-03"
POR_PAGINA = 200
CAMPOS = ["item_id", "title", "description", "url", "brand", "seller_name",
          "image_url", "additional_image_urls", "availability", "price",
          "sale_price", "condition", "product_category", "is_eligible_search",
          "target_countries", "store_country"]


def _get(path, **params):
    e = {k: os.environ.get(k, "").strip() for k in ("TN_STORE_ID", "TN_ACCESS_TOKEN", "TN_USER_AGENT")}
    if not all(e.values()):
        raise SystemExit("Faltan TN_STORE_ID, TN_ACCESS_TOKEN o TN_USER_AGENT")
    url = "%s/%s%s?%s" % (API, e["TN_STORE_ID"], path, urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + e["TN_ACCESS_TOKEN"],
                                               "User-Agent": e["TN_USER_AGENT"]})
    for intento in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return [] if r.status == 204 else json.load(r)
        except urllib.error.HTTPError as ex:
            if ex.code == 404 and "Last page" in ex.read().decode("utf-8", "replace"):
                return []
            if ex.code not in (429, 500, 502, 503, 504) or intento == 3:
                raise SystemExit("Tiendanube respondió HTTP %s en %s" % (ex.code, path))
        except (TimeoutError, ConnectionError, urllib.error.URLError):
            if intento == 3:
                raise
        time.sleep(5 * 3 ** intento)


def _num(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n or None


def texto(v):
    """Tiendanube devuelve los textos por idioma ({"es": ...})."""
    if isinstance(v, dict):
        v = v.get("es") or next(iter(v.values()), "")
    return v or ""


def limpio(h, tope=4500):
    t = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", texto(h), flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"[ \t ]+", " ", t)
    # Una sola línea por producto: algunos lectores de CSV se traban con saltos
    # de línea dentro de un campo, aunque vayan entre comillas.
    t = re.sub(r"\s*\n\s*", " · ", t).strip(" ·")
    return t[:tope].rsplit(" ", 1)[0] + "…" if len(t) > tope else t


def monto(n):
    return "%.2f %s" % (n, MONEDA)


def productos():
    pagina, out = 1, []
    while True:
        lote = _get("/products", per_page=POR_PAGINA, page=pagina,
                       fields="id,name,description,handle,canonical_url,published,"
                              "variants,images,free_shipping")
        if not lote:
            break
        out += lote
        if len(lote) < POR_PAGINA:
            break
        pagina += 1
    return out


def filas(prods):
    for p in prods:
        if not p.get("published"):
            continue
        nombre = texto(p.get("name")).strip()
        url = p.get("canonical_url") or "https://www.kosmoscosmetica.com/productos/%s/" % texto(p.get("handle"))
        imagenes = {i.get("id"): i.get("src") for i in (p.get("images") or []) if i.get("src")}
        orden = [i.get("src") for i in sorted(p.get("images") or [], key=lambda i: i.get("position") or 0) if i.get("src")]
        desc = limpio(p.get("description")) or nombre
        variantes = p.get("variants") or []
        varias = len(variantes) > 1
        for v in variantes:
            lista = _num(v.get("price"))
            if not lista:
                continue  # sin precio o regalo: no va a ChatGPT
            promo = _num(v.get("promotional_price"))
            valores = [texto(x) for x in (v.get("values") or []) if texto(x)]
            titulo = nombre + (" - " + " / ".join(valores) if varias and valores else "")
            img = imagenes.get(v.get("image_id")) or (orden[0] if orden else "")
            if not img:
                continue  # OpenAI exige imagen
            extra = [u.replace(",", "%2C") for u in orden if u != img][:9]
            maneja_stock = v.get("stock_management")
            stock = v.get("stock")
            disponible = "out_of_stock" if (maneja_stock and stock is not None and stock <= 0) else "in_stock"
            yield {
                "item_id": str(v.get("id")),
                "title": titulo[:150],
                "description": desc,
                "url": url + ("?variant=%s" % v.get("id") if varias else ""),
                "brand": MARCA,
                "seller_name": MARCA,
                "image_url": img,
                "additional_image_urls": ",".join(extra),
                "availability": disponible,
                "price": monto(lista),
                "sale_price": monto(promo) if (promo and promo < lista) else "",
                "condition": "new",
                "product_category": CATEGORIA,
                "is_eligible_search": "true",
                # Obligatorios según la especificación de OpenAI (16/11/2026).
                "target_countries": "AR",
                "store_country": "AR",
            }


def main():
    rs = list(filas(productos()))
    if len(rs) < 20:
        # Si Tiendanube devolvió casi nada, mejor no pisar el archivo bueno.
        raise SystemExit("Solo %d productos: algo anda mal, no publico." % len(rs))
    SALIDA.mkdir(exist_ok=True)
    with open(SALIDA / ARCHIVO, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(rs)
    # Página mínima para que la raíz del sitio no dé 404.
    (SALIDA / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Kosmos Cosmética</title>'
        '<p>Catálogo para ChatGPT: <a href="%s">%s</a></p>' % (ARCHIVO, ARCHIVO), encoding="utf-8")
    # Que Google y otros buscadores no lo indexen. No bloquea a ChatGPT:
    # es un encabezado de respuesta, no un robots.txt que impida bajarlo.
    (SALIDA / "_headers").write_text("/*\n  X-Robots-Tag: noindex, nofollow\n", encoding="utf-8")
    agot = sum(r["availability"] == "out_of_stock" for r in rs)
    promo = sum(bool(r["sale_price"]) for r in rs)
    print("Feed: %d variantes (%d agotadas, %d con precio promocional) → %s"
          % (len(rs), agot, promo, SALIDA / ARCHIVO))
    if "--resumen" in sys.argv:
        for r in rs[:5]:
            print(" | ".join([r["item_id"], r["title"], r["price"], r["sale_price"], r["availability"], r["url"]]))


if __name__ == "__main__":
    main()
