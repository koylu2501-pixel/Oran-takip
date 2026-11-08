#!/usr/bin/env python3
"""Uygulama için canlı veri dosyası: data/canli.json

İçerik:
  fixtures: önümüzdeki 7 günün maçları (10 lig)
    b365o: Bet365 açılış (football-data cuma oranı; yoksa takip programının ilk Bet365 okuması)
    b365c: Bet365 güncel (takip programının son Bet365 okuması)
    pino / pinc: Pinnacle ilk / son okuma
  iddaa: iddaa bülteni (tüm pazarlar, uygulamanın kullandığı biçimde)
En fazla 5.5 saatte bir yeniden üretilir (FORCE=1 ile her zaman).
"""
import csv, io, json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import takip as T  # isim eşleştirme ve yardımcılar

OUT = os.path.join(ROOT, "data", "canli.json")
MAIN = ["E0", "SP1", "I1", "D1", "F1", "T1", "N1", "P1", "B1", "E1"]
IST = {"1_1", "2_88", "2_36", "2_90", "2_92", "2_77", "2_101", "2_60", "2_89", "2_720", "2_91", "2_4", "2_603", "2_604",
       "2_7", "2_700", "2_698", "2_699", "2_724", "2_6", "2_11", "2_100"}
now = datetime.now(timezone.utc)


def uk_to_utc(ds, ts):
    d = datetime.strptime(ds.strip(), "%d/%m/%Y")
    hh, mm = (ts or "12:00").split(":")
    t = d.replace(hour=int(hh), minute=int(mm), tzinfo=timezone.utc)

    def last_sun(y, m):
        x = datetime(y, m + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
        return x - timedelta(days=(x.weekday() + 1) % 7)
    bs = last_sun(t.year, 3).replace(hour=1)
    be = last_sun(t.year, 10).replace(hour=1)
    return t - timedelta(hours=1) if bs + timedelta(hours=1) <= t < be + timedelta(hours=1) else t


def fnum(v):
    try:
        x = float(v)
        return x if x > 1 else None
    except Exception:
        return None


def football_data():
    raw = urllib.request.urlopen(urllib.request.Request("https://www.football-data.co.uk/fixtures.csv", headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode("latin-1")
    out = []
    for r in csv.DictReader(io.StringIO(raw.lstrip("﻿"))):
        lg = (r.get("Div") or "").strip()
        if lg not in MAIN:
            continue
        try:
            ko = uk_to_utc(r["Date"], r.get("Time"))
        except Exception:
            continue
        if ko < now - timedelta(hours=2) or ko > now + timedelta(days=7):
            continue
        out.append({"lg": lg, "ko": ko, "h": r["HomeTeam"].strip(), "a": r["AwayTeam"].strip(),
                    "b365o": [fnum(r.get(k)) for k in ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5")]})
    return out


def readings():
    """takip programının okumaları: fixture -> {buro: [satırlar zamana göre]}"""
    rows = T.read_csv("pinnacle.csv")
    by = {}
    for r in rows:
        by.setdefault(r["fixture"], {"lg": r["lig"], "ko": r["baslama"], "h": r["ev"], "a": r["dep"], "b": {}})["b"].setdefault(r["buro"], []).append(r)
    for v in by.values():
        for L in v["b"].values():
            L.sort(key=lambda r: r["zaman"])
    return by


try:  # OddsPapi'nin Bet365 oranlarını football-data'nın Bet365 basamaklarına yuvarla (1.54 -> 1.53 gibi)
    LADDER = json.load(open(os.path.join(ROOT, "data", "b365_ladder.json")))
except Exception:
    LADDER = []


def snap(v):
    if not v or not LADDER:
        return v
    b = min(LADDER, key=lambda x: abs(x - v))
    return b if abs(b - v) <= 0.021 else v


def odds5(r):
    return [fnum(r.get(k)) for k in ("ms1", "ms0", "ms2", "ust25", "alt25")]


def iddaa():
    ici = T.ICI
    d = T.get_json("https://sportsbookv2.iddaa.com/sportsbook/events?st=1&type=0&version=0")["data"]
    evs = [e for e in d.get("events", []) if e.get("ci") in ici and now - timedelta(hours=2) < datetime.fromtimestamp(e["d"], timezone.utc) < now + timedelta(days=3)]
    out = []
    for e in evs:
        try:
            m = T.get_json(f"https://sportsbookv2.iddaa.com/sportsbook/event/{e['i']}")["data"].get("m") or e.get("m") or []
        except Exception:
            m = e.get("m") or []
        o = {}
        for mk in m:
            st = f"{mk.get('t')}_{mk.get('st')}"
            if st not in IST:
                continue
            for x in mk.get("o", []):
                if x.get("odd", 0) > 1:
                    o[f"{st}|{'' if mk.get('sov') is None else mk.get('sov')}|{x.get('n')}"] = x["odd"]
        out.append({"lg": ici[e["ci"]], "ts": e["d"] * 1000, "h": e.get("hn", ""), "a": e.get("an", ""), "o": o})
        time.sleep(0.2)
    return {"at": int(now.timestamp() * 1000), "ev": out}


def main():
    if os.environ.get("FORCE") != "1" and os.path.exists(OUT):
        try:
            at = json.load(open(OUT, encoding="utf-8")).get("at", 0)
            if (now.timestamp() * 1000 - at) < 5.5 * 3600e3:
                print("canli.json yeni, atlandı")
                return
        except Exception:
            pass
    try:
        fx = football_data()
    except Exception as e:
        print("football-data okunamadı:", e)
        fx = []
    rd = readings()
    used = set()
    res = []
    for f in fx:
        m = [k for k, v in rd.items() if v["lg"] == f["lg"] and T.parse_ko(v["ko"]) and abs((T.parse_ko(v["ko"]) - f["ko"]).total_seconds()) <= 3600
             and (T.sim(v["h"], f["h"]) or T.sim(v["a"], f["a"]))]
        g = rd[m[0]] if len(m) == 1 else None
        if g:
            used.add(m[0])
        res.append((f, g))
    for k, v in rd.items():  # football-data'da henüz olmayan maçlar
        ko = T.parse_ko(v["ko"])
        if k in used or not ko or ko < now - timedelta(hours=2):
            continue
        res.append(({"lg": v["lg"], "ko": ko, "h": v["h"], "a": v["a"], "b365o": None}, v))
    fixtures = []
    for f, g in res:
        b = (g or {}).get("b", {})
        bl, pl = b.get("bet365") or [], b.get("pinnacle") or []
        b365o = f["b365o"] if f["b365o"] and any(f["b365o"]) else (odds5(bl[0]) if bl else [None] * 5)
        fixtures.append({"lg": f["lg"], "ko": f["ko"].strftime("%Y-%m-%dT%H:%MZ"), "h": f["h"], "a": f["a"],
                         "b365o": [snap(v) for v in b365o], "b365c": [snap(v) for v in odds5(bl[-1])] if bl else [None] * 5,
                         "pino": odds5(pl[0]) if pl else [None] * 5, "pinc": odds5(pl[-1]) if pl else [None] * 5,
                         "son": (pl or bl)[-1]["zaman"] if (pl or bl) else None})
    fixtures.sort(key=lambda x: (x["ko"], x["lg"]))
    try:
        idd = iddaa()
    except Exception as e:
        print("iddaa okunamadı:", e)
        idd = None
    data = {"at": int(now.timestamp() * 1000), "fixtures": fixtures, "iddaa": idd}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print("canli.json:", len(fixtures), "maç,", len(idd["ev"]) if idd else 0, "iddaa maçı")


if __name__ == "__main__":
    main()
