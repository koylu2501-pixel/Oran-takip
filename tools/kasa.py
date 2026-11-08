#!/usr/bin/env python3
"""Sanal kasa: her gün bir kez
  1) bekleyen kuponları football-data sonuçlarıyla sonuçlandırır,
  2) bugünün maçları için birebir oran eşleşmesiyle 3'lü kupon kurar ve kaydeder,
  3) özeti Telegram'a tek mesaj olarak yollar (TELEGRAM_TOKEN varsa).
Kurallar: Bet365 açılış oranıyla birebir eşleşen 5-15 geçmiş maç; seçenek ya hepsinde
ya da biri hariç hepsinde (en az %85) tutmuş olmalı; iddaa oranı en az 1.30; her maçtan tek
seçim; 3 maç; basış = kasanın %20'si. Uygun 3 maç yoksa o gün kupon yok.
"""
import csv, io, json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import takip as T

KASA = os.path.join(ROOT, "data", "kasa.json")
now = datetime.now(timezone.utc)
TR = timezone(timedelta(hours=3))
MIN_ODD, NMIN, NMAX, MINP, LEGS = 1.30, 5, 15, 0.85, 3
MAINF = ['E0','E1','E2','E3','EC','SC0','SC1','SC2','SC3','D1','D2','I1','I2','SP1','SP2','F1','F2','N1','B1','P1','T1','G1']
LAB = {'1_1':'MS {n}','2_88':'İY {n}','2_36':'2. yarı {n}','2_90':'İY/MS {n}','2_92':'Çifte şans {n}','2_77':'İY çifte şans {n}',
       '2_101':'{s} {n}','2_60':'İY {s} {n}','2_89':'KG {n}','2_720':'İY KG {n}','2_603':'Ev sahibi {s} {n}','2_604':'Deplasman {s} {n}'}


def f2(v):
    try:
        x = float(v)
        return x if x > 1 else None
    except Exception:
        return None


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=90).read().decode("latin-1")


def R(a, b):
    return '1' if a > b else '2' if a < b else '0'


def W(key, r):
    st, sv, n = key.split('|')
    sov = float(sv) if sv else None
    fh, fa, hh, ha = r['fh'], r['fa'], r['hh'], r['ha']
    if st in ('2_88', '2_36', '2_90', '2_77', '2_60', '2_720') and hh is None:
        return None
    t = fh + fa
    x, y = (n.split(' ve ') + [None])[:2]
    OU = lambda v, w: {'Üst': v > (sov or 0), 'Alt': v < (sov or 0)}.get(w)
    KG = lambda a, b, w: {'Var': a > 0 and b > 0, 'Yok': not (a > 0 and b > 0)}.get(w)
    if st == '1_1': return R(fh, fa) == n
    if st == '2_88': return R(hh, ha) == n
    if st == '2_36': return R(fh - hh, fa - ha) == n
    if st == '2_90': return R(hh, ha) + '/' + R(fh, fa) == n
    if st == '2_92': return R(fh, fa) in (x, y)
    if st == '2_77': return R(hh, ha) in (x, y)
    if st == '2_101': return OU(t, n)
    if st == '2_60': return OU(hh + ha, n)
    if st == '2_89': return KG(fh, fa, n)
    if st == '2_720': return KG(hh, ha, n)
    if st == '2_603': return OU(fh, n)
    if st == '2_604': return OU(fa, n)
    return None


def label(key):
    st, sv, n = key.split('|')
    return LAB[st].format(n=n.replace(' ve ', '-'), s=sv)


def history():
    H = []
    for r in csv.DictReader(open(os.path.join(ROOT, "data", "gecmis.csv"), encoding="utf-8")):
        try:
            fh, fa = int(r['FTHG']), int(r['FTAG'])
        except Exception:
            continue
        H.append({'fh': fh, 'fa': fa, 'hh': int(r['HTHG']) if r['HTHG'] else None, 'ha': int(r['HTAG']) if r['HTAG'] else None,
                  'o': [f2(r[k]) for k in ('B365H', 'B365D', 'B365A', 'B365>2.5', 'B365<2.5')]})
    return H


def iddaa_all():
    """Tüm futbol bülteni (lig kısıtı yok), seçenekleriyle."""
    d = T.get_json("https://sportsbookv2.iddaa.com/sportsbook/events?st=1&type=0&version=0")["data"]
    return [e for e in d.get("events", []) if now < datetime.fromtimestamp(e["d"], timezone.utc) < now + timedelta(hours=20)]


def iddaa_markets(e):
    try:
        m = T.get_json(f"https://sportsbookv2.iddaa.com/sportsbook/event/{e['i']}")["data"].get("m") or []
    except Exception:
        m = e.get("m") or []
    o = {}
    for mk in m:
        st = f"{mk.get('t')}_{mk.get('st')}"
        if st not in LAB:
            continue
        for x in mk.get("o", []):
            if x.get("odd", 0) > 1:
                o[f"{st}|{'' if mk.get('sov') is None else mk.get('sov')}|{x.get('n')}"] = x["odd"]
    return o


def uk_to_utc(ds, ts):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import canli as C  # aynı dönüştürücü
    return C.uk_to_utc(ds, ts)


def eq(a, b, idx):
    return all(a[i] is not None and b[i] is not None and abs(a[i] - b[i]) < 1e-6 for i in idx)


def make_coupon(k, msgs):
    today = now.astimezone(TR).strftime("%Y-%m-%d")
    if any(c["tarih"] == today for c in k["kuponlar"]):
        return
    raw = get("https://www.football-data.co.uk/fixtures.csv")
    fx = []
    for r in csv.DictReader(io.StringIO(raw.lstrip("﻿"))):
        if (r.get("Div") or "").strip() not in MAINF:
            continue
        try:
            ko = uk_to_utc(r["Date"], r.get("Time"))
        except Exception:
            continue
        if not (now + timedelta(minutes=45) < ko < now + timedelta(hours=20)):
            continue
        o = [f2(r.get(c)) for c in ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5")]
        if all(o[:3]):
            fx.append({"lg": r["Div"].strip(), "ko": ko, "h": r["HomeTeam"].strip(), "a": r["AwayTeam"].strip(), "o": o})
    if not fx:
        msgs.append("Bugün Bet365 açılış oranı olan maç yok, kupon yapılmadı.")
        return
    H = history()
    ev = iddaa_all()
    meths = [("Bet365 açılış MS birebir", [0, 1, 2]), ("Bet365 açılış MS+2.5 birebir", [0, 1, 2, 3, 4]), ("Bet365 açılış 1 ve 2 birebir", [0, 2])]
    cands = []
    for f in fx:
        m = [e for e in ev if abs(e["d"] - f["ko"].timestamp()) <= 3600 and (T.sim(e.get("hn", ""), f["h"]) and T.sim(e.get("an", ""), f["a"]))]
        if len(m) != 1:
            continue
        e = m[0]
        mk = None
        for name, idx in meths:
            if not all(f["o"][i] for i in idx):
                continue
            M = [r for r in H if eq(r["o"], f["o"], idx)]
            if not (NMIN <= len(M) <= NMAX):
                continue
            mk = mk if mk is not None else iddaa_markets(e)
            for key, io_ in mk.items():
                if io_ < MIN_ODD:
                    continue
                ws = [w for w in (W(key, r) for r in M) if w is not None]
                if len(ws) < NMIN:
                    continue
                kk = sum(1 for w in ws if w)
                if kk / len(ws) >= MINP and kk >= len(ws) - 1:
                    cands.append({"p": kk / len(ws), "n": len(ws), "k": kk, "f": f, "e": e, "key": key, "odd": io_, "yontem": name})
            time.sleep(0.2)
    cands.sort(key=lambda c: (-c["p"], -c["n"], -c["odd"]))
    legs, used = [], set()
    for c in cands:
        mid = c["f"]["h"] + c["f"]["a"]
        if mid in used:
            continue
        used.add(mid)
        legs.append(c)
        if len(legs) == LEGS:
            break
    if len(legs) < LEGS:
        msgs.append(f"Bugün kurallara uyan {len(legs)} maç bulundu (3 gerekiyor), kupon yapılmadı.")
        return
    odd = 1.0
    for c in legs:
        odd *= c["odd"]
    stake = round(k["bakiye"] * k.get("basis_orani", 0.2))
    if stake <= 0:
        msgs.append("Kasa bitti, kupon yapılmadı.")
        return
    k["bakiye"] = round(k["bakiye"] - stake, 2)
    cp = {"id": max([c["id"] for c in k["kuponlar"]] + [0]) + 1, "tarih": today, "olusturma": now.strftime("%Y-%m-%dT%H:%MZ"),
          "basis": stake, "toplam_oran": round(odd, 2), "durum": "bekliyor", "donus": 0,
          "maclar": [{"lg": c["f"]["lg"], "ko": c["f"]["ko"].strftime("%Y-%m-%dT%H:%MZ"), "h": c["f"]["h"], "a": c["f"]["a"], "key": c["key"],
                      "secim": label(c["key"]), "oran": c["odd"], "gecmis": f"{c['k']}/{c['n']}", "yontem": c["yontem"], "sonuc": None} for c in legs]}
    k["kuponlar"].append(cp)
    lines = [f"🎫 Sanal kupon #{cp['id']} · basış {stake} TL · toplam oran {cp['toplam_oran']:.2f}"]
    for l in cp["maclar"]:
        t = datetime.fromisoformat(l["ko"].replace("Z", ":00+00:00")).astimezone(TR).strftime("%H:%M")
        lines.append(f"{t} {l['h']} – {l['a']}: {l['secim']} @ {l['oran']:.2f} ({l['gecmis']})")
    msgs.append("\n".join(lines))


def settle(k, msgs):
    pend = [c for c in k["kuponlar"] if c["durum"] == "bekliyor"]
    if not pend:
        return
    season = (now.year % 100 if now.month >= 7 else now.year % 100 - 1)
    sc = f"{season:02d}{season + 1:02d}"
    cache = {}
    for c in pend:
        for l in c["maclar"]:
            if l["sonuc"] is not None:
                continue
            ko = datetime.fromisoformat(l["ko"].replace("Z", ":00+00:00"))
            if now < ko + timedelta(hours=2, minutes=30):
                continue
            if l["lg"] not in cache:
                try:
                    cache[l["lg"]] = list(csv.DictReader(io.StringIO(get(f"https://www.football-data.co.uk/mmz4281/{sc}/{l['lg']}.csv").lstrip("﻿"))))
                except Exception:
                    cache[l["lg"]] = []
            hit = None
            for r in cache[l["lg"]]:
                if not (r.get("FTHG") or "").strip():
                    continue
                if T.sim(r.get("HomeTeam", ""), l["h"]) and T.sim(r.get("AwayTeam", ""), l["a"]):
                    try:
                        d = datetime.strptime(r["Date"], "%d/%m/%Y").date()
                    except Exception:
                        continue
                    if abs((d - ko.astimezone(TR).date()).days) <= 1:
                        hit = r
                        break
            if hit:
                rr = {"fh": int(hit["FTHG"]), "fa": int(hit["FTAG"]), "hh": int(hit["HTHG"]) if hit.get("HTHG") else None, "ha": int(hit["HTAG"]) if hit.get("HTAG") else None}
                w = W(l["key"], rr)
                l["skor"] = f"{rr['fh']}-{rr['fa']}" + (f" (İY {rr['hh']}-{rr['ha']})" if rr["hh"] is not None else "")
                l["sonuc"] = "tuttu" if w else "yattı" if w is not None else "iade"
            elif now > ko + timedelta(days=5):
                l["sonuc"] = "iade"
                l["skor"] = "sonuç bulunamadı"
        if all(l["sonuc"] for l in c["maclar"]):
            if any(l["sonuc"] == "yattı" for l in c["maclar"]):
                c["durum"], c["donus"] = "kaybetti", 0
            else:
                odd = 1.0
                for l in c["maclar"]:
                    odd *= l["oran"] if l["sonuc"] == "tuttu" else 1.0
                c["durum"], c["donus"] = "kazandı", round(c["basis"] * odd, 2)
                k["bakiye"] = round(k["bakiye"] + c["donus"], 2)
            em = "✅" if c["durum"] == "kazandı" else "❌"
            msgs.append(f"{em} Kupon #{c['id']} {c['durum']}" + (f" · dönüş {c['donus']:.0f} TL" if c["donus"] else "") + "\n" +
                        "\n".join(f"{l['h']} – {l['a']}: {l['secim']} → {l.get('skor', '')} {('✔' if l['sonuc'] == 'tuttu' else '✖' if l['sonuc'] == 'yattı' else 'iade')}" for l in c["maclar"]))


def main():
    k = json.load(open(KASA, encoding="utf-8"))
    msgs = []
    try:
        settle(k, msgs)
    except Exception as e:
        print("sonuçlandırma hatası:", e)
    if os.environ.get("KUPON", "1") == "1":
        try:
            make_coupon(k, msgs)
        except Exception as e:
            print("kupon hatası:", e)
    k["guncelleme"] = now.strftime("%Y-%m-%dT%H:%MZ")
    json.dump(k, open(KASA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    acik = sum(c["basis"] for c in k["kuponlar"] if c["durum"] == "bekliyor")
    msgs.append(f"💰 Sanal kasa: {k['bakiye']:.0f} TL (+ bekleyen kuponlarda {acik:.0f} TL) · başlangıç {k['baslangic']} TL")
    print("\n\n".join(msgs))
    if os.environ.get("TELEGRAM_TOKEN") and (len(msgs) > 1 or os.environ.get("KUPON", "1") == "1"):
        st = T.load_state()
        T.tg_send(st, "\n\n".join(msgs))
        T.save_state(st)


if __name__ == "__main__":
    main()
