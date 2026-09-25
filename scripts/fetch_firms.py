#!/usr/bin/env python3
"""
Scarica i punti di calore NASA FIRMS (tempo quasi reale) SOLO sul riquadro della Puglia,
tiene quelli che cadono nei comuni pugliesi e li salva in data/firms_puglia.json.

Uso:
    FIRMS_MAP_KEY=la-tua-chiave python scripts/fetch_firms.py

Solo libreria standard di Python: nessun pacchetto da installare.
"""
import csv
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

QUI = Path(__file__).resolve().parent
OUT = QUI.parent / "data" / "firms_puglia.json"
COMUNI_FILE = QUI / "puglia_comuni.json"

# Riquadro geografico richiesto a FIRMS: ovest, sud, est, nord (solo la Puglia, non il mondo)
BBOX = (14.9, 39.75, 18.55, 42.25)
# Giorni UTC richiesti: 3 = oggi e i due giorni precedenti (copre almeno le ultime 48 ore)
DAY_RANGE = 3
FONTI = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"]
API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{src}/{bbox}/{days}"
# Punti appena fuori dalla costa o dal confine: assegnati al comune piu' vicino entro questa distanza
TOLLERANZA_KM = 2.0
# Anche se non cambia nulla, riscrive il file almeno ogni N ore (cosi' la pagina sa che il controllo funziona)
BATTITO_ORE = 2


# ------------------------------------------------------------------ geometria
def carica_comuni(path=COMUNI_FILE):
    fc = json.loads(Path(path).read_text(encoding="utf-8"))
    comuni = []
    for f in fc["features"]:
        g = f["geometry"]
        poligoni = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        xs = [p[0] for poly in poligoni for p in poly[0]]
        ys = [p[1] for poly in poligoni for p in poly[0]]
        comuni.append({"c": f["properties"]["c"], "p": f["properties"]["p"],
                       "poligoni": poligoni, "bbox": (min(xs), min(ys), max(xs), max(ys))})
    return comuni


def _in_anello(x, y, anello):
    dentro = False
    j = len(anello) - 1
    for i in range(len(anello)):
        xi, yi = anello[i]
        xj, yj = anello[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def _in_poligono(x, y, poly):
    if not _in_anello(x, y, poly[0]):
        return False
    return not any(_in_anello(x, y, buco) for buco in poly[1:])


def _dist_km(x, y, anello):
    """Distanza minima (km) tra il punto e i lati dell'anello, con approssimazione equirettangolare."""
    kx, ky = 111.32 * math.cos(math.radians(y)), 110.57
    best = float("inf")
    for i in range(len(anello) - 1):
        ax, ay = (anello[i][0] - x) * kx, (anello[i][1] - y) * ky
        bx, by = (anello[i + 1][0] - x) * kx, (anello[i + 1][1] - y) * ky
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / L2))
        px, py = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(px, py))
    return best


def trova_comune(lat, lon, comuni, tolleranza_km=TOLLERANZA_KM):
    """Restituisce (comune, provincia, distanza_km) oppure None se il punto non e' in Puglia."""
    for c in comuni:
        x0, y0, x1, y1 = c["bbox"]
        if x0 <= lon <= x1 and y0 <= lat <= y1 and any(_in_poligono(lon, lat, p) for p in c["poligoni"]):
            return c["c"], c["p"], 0.0
    margine = tolleranza_km / 80.0
    migliore = None
    for c in comuni:
        x0, y0, x1, y1 = c["bbox"]
        if not (x0 - margine <= lon <= x1 + margine and y0 - margine <= lat <= y1 + margine):
            continue
        d = min(_dist_km(lon, lat, p[0]) for p in c["poligoni"])
        if d <= tolleranza_km and (migliore is None or d < migliore[2]):
            migliore = (c["c"], c["p"], round(d, 2))
    return migliore


# ------------------------------------------------------------------ dati FIRMS
def _affidabilita(v):
    v = str(v).strip().lower()
    if v in ("h", "high", "alta"):
        return "alta"
    if v in ("n", "nominal", "nominale"):
        return "nominale"
    if v in ("l", "low", "bassa"):
        return "bassa"
    try:                        # MODIS: percentuale 0-100
        n = float(v)
    except ValueError:
        return "nominale"
    return "alta" if n >= 80 else ("nominale" if n >= 30 else "bassa")


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def leggi_csv(testo, fonte, comuni):
    """Converte il CSV di FIRMS nella lista di punti pugliesi."""
    if not testo.lstrip().lower().startswith("latitude"):
        raise ValueError("risposta inattesa da FIRMS: " + testo.strip()[:160])
    punti = []
    for r in csv.DictReader(io.StringIO(testo)):
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            continue
        dove = trova_comune(lat, lon, comuni)
        if dove is None:
            continue                                  # fuori dalla Puglia
        ora = str(r.get("acq_time", "0")).strip().zfill(4)
        punti.append({
            "lat": round(lat, 5), "lon": round(lon, 5),
            "t": f"{r['acq_date']}T{ora[:2]}:{ora[2:]}:00Z",
            "fonte": fonte,
            "affid": _affidabilita(r.get("confidence", "")),
            "frp": _num(r.get("frp")),
            "bt": _num(r.get("bright_ti4") or r.get("brightness")),
            "scan": _num(r.get("scan")), "track": _num(r.get("track")),
            "dn": (r.get("daynight") or "").strip().upper()[:1],
            "tipo": (r.get("type") or "").strip() or None,
            "comune": dove[0], "prov": dove[1], "fuori_km": dove[2],
        })
    return punti


def scarica(fonte, chiave, tentativi=3):
    url = API.format(key=chiave, src=fonte, bbox=",".join(str(v) for v in BBOX), days=DAY_RANGE)
    ultimo = None
    for t in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "focolai-puglia/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = e
            time.sleep(10 * (t + 1))
    # nel messaggio d'errore non compare mai la chiave
    raise RuntimeError(f"{type(ultimo).__name__}: {str(ultimo).replace(chiave, '***')}")


# ------------------------------------------------------------------ main
def main():
    chiave = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not chiave:
        print("Manca la chiave: imposta la variabile d'ambiente FIRMS_MAP_KEY.", file=sys.stderr)
        return 1

    comuni = carica_comuni()
    ora = datetime.now(timezone.utc)
    fonti, punti = {}, []
    for f in FONTI:
        try:
            nuovi = leggi_csv(scarica(f, chiave), f, comuni)
            fonti[f] = {"ok": True, "n": len(nuovi), "errore": None}
            punti += nuovi
        except Exception as e:                         # una fonte che fallisce non blocca le altre
            fonti[f] = {"ok": False, "n": 0, "errore": str(e).replace(chiave, "***")[:200]}
        print(f"{f}: {fonti[f]}")

    if not any(v["ok"] for v in fonti.values()):
        print("Nessuna fonte disponibile: il file precedente non viene modificato.", file=sys.stderr)
        return 1

    visti, unici = set(), []
    for p in sorted(punti, key=lambda p: p["t"], reverse=True):
        k = (p["lat"], p["lon"], p["t"], p["fonte"])
        if k not in visti:
            visti.add(k)
            unici.append(p)

    precedente = None
    if OUT.exists():
        try:
            precedente = json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            precedente = None
    stato = {k: v["ok"] for k, v in fonti.items()}
    if precedente and precedente.get("punti") == unici and \
            {k: v.get("ok") for k, v in precedente.get("fonti", {}).items()} == stato:
        try:
            ultimo = datetime.fromisoformat(precedente["controllato_il"].replace("Z", "+00:00"))
            if ora - ultimo < timedelta(hours=BATTITO_ORE):
                print("Nessuna novita': file lasciato invariato.")
                return 0
        except (KeyError, TypeError, ValueError):
            pass
    generato = precedente["generato_il"] if precedente and precedente.get("punti") == unici \
        and precedente.get("generato_il") else ora.isoformat(timespec="seconds").replace("+00:00", "Z")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "controllato_il": ora.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "generato_il": generato,
        "bbox": BBOX, "day_range": DAY_RANGE, "fonti": fonti, "punti": unici,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Salvati {len(unici)} punti di calore in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
