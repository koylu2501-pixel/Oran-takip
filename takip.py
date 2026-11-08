#!/usr/bin/env python3
"""Oran takip (mini test).

Her çalışmada:
  1) iddaa bülteninden MS 1-0-2 oranlarını kaydeder (data/iddaa.csv)  -> sınırsız, her çalışmada
  2) OddsPapi'den Pinnacle (ve varsa Bet365) MS oranlarını kotayı aşmadan kaydeder (data/pinnacle.csv)
     Her maç için en fazla 2 okuma: maçtan 30–6 saat önce ve 2 saat–30 dk önce.
  3) Pinnacle bir seçenekte en az DROP_PCT düşmüş, iddaa hâlâ yüksekse Telegram'a sinyal yollar (data/sinyaller.csv)
  4) Günde bir, sinyallerin sonradan ne olduğunu (iddaa düştü mü, kaç dakikada) rapor eder.
Sadece Python standart kütüphanesi kullanır.
"""
import csv, json, os, re, sys, time, unicodedata, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
STATE_F = os.path.join(DATA, "state.json")
TR = timezone(timedelta(hours=3))

TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
OP_KEY = os.environ.get("ODDSPAPI_KEY", "").strip()

# iddaa yarışma kodları -> bizim lig kodlarımız (iddaa kaydı 9 lig için)
ICI = {43: "E0", 129: "SP1", 143: "I1", 45: "D1", 381: "F1", 584: "T1", 322: "N1", 566: "P1", 148: "B1"}
# Pinnacle takibi (ücretsiz kota için sadece 2 lig). OddsPapi tournamentId'leri ilk çalışmada isimden bulunur.
OP_LEAGUES = {"E0": ("England", ["Premier League"]), "T1": ("Turkey", ["Super Lig"]),
              "SP1": ("Spain", ["LaLiga", "La Liga"]), "I1": ("Italy", ["Serie A"]), "D1": ("Germany", ["Bundesliga"]),
              "F1": ("France", ["Ligue 1"]), "N1": ("Netherlands", ["Eredivisie"]),
              "P1": ("Portugal", ["Liga Portugal", "Primeira Liga", "Liga Portugal Betclic"]),
              "B1": ("Belgium", ["Pro League", "Jupiler Pro League", "First Division A"])}
# Okuma pencereleri (maça kalan saat): ilk okuma 30 saat içinde ilk fırsatta, sonra 1.75–1 saat ve 0.5–0.15 saat kala
WINDOWS = [("ilk", 1.0, 30.0), ("orta", 1.0, 1.75), ("son", 0.15, 0.5)]
MONTHLY_BUDGET = int(os.environ.get("ODDSPAPI_BUDGET", "235"))  # ücretsiz paket 250/ay, 20 yedek
DROP_PCT = float(os.environ.get("DROP_PCT", "5"))        # Pinnacle düşüşü eşiği (%)
UA = {"User-Agent": "oran-takip/1.0", "Accept": "application/json"}

now = datetime.now(timezone.utc)
log_lines = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    log_lines.append(s)


def get_json(url, params=None, timeout=25):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def load_state():
    try:
        with open(STATE_F, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(st):
    with open(STATE_F, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1, sort_keys=True)


def append_csv(name, header, rows):
    if not rows:
        return
    p = os.path.join(DATA, name)
    new = not os.path.exists(p)
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerows(rows)


def read_csv(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- Telegram ----------
def tg_chat_id(st):
    if TG_CHAT:
        return TG_CHAT
    if st.get("tg_chat"):
        return st["tg_chat"]
    if not TG_TOKEN:
        return None
    try:
        me = get_json(f"https://api.telegram.org/bot{TG_TOKEN}/getMe", timeout=40).get("result", {})
        log("Telegram anahtarı şu bota ait: @" + str(me.get("username")))
    except Exception as e:
        log("Telegram getMe hatası:", type(e).__name__, str(e)[:80])
    d = None
    for attempt in range(2):  # bota ilk mesajı atan sohbeti bul
        try:
            d = get_json(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates", timeout=40)
            break
        except Exception as e:
            log("Telegram getUpdates hatası:", type(e).__name__)
            time.sleep(3)
    if d:
        for u in reversed(d.get("result", [])):
            m = u.get("message") or u.get("channel_post") or {}
            cid = (m.get("chat") or {}).get("id")
            if cid:
                st["tg_chat"] = str(cid)
                return st["tg_chat"]
        log("Telegram: bota henüz mesaj yazılmamış (getUpdates boş)")
    return None


def tg_send(st, text):
    cid = tg_chat_id(st)
    if not (TG_TOKEN and cid):
        why = "TELEGRAM_TOKEN tanımlı değil" if not TG_TOKEN else "sohbet bulunamadı (bota /start yazılmamış)"
        log(f"[Telegram yok: {why}] " + text.replace("\n", " | "))
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": cid, "text": text[:4000], "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)
        urllib.request.urlopen(req, timeout=20).read()
        return True
    except Exception as e:
        log("Telegram gönderim hatası:", type(e).__name__)
        return False


# ---------- isim eşleştirme ----------
STOP = {"fc", "cf", "sc", "ac", "as", "afc", "club", "de", "spor", "sk", "fk", "kv", "rc", "sv", "united", "city", "town",
        "real", "calcio", "olympique", "stade", "athletic", "sporting", "the", "hotspur", "albion", "and", "jk", "as"}


def toks(name):
    s = unicodedata.normalize("NFKD", str(name).lower().replace("ı", "i")).encode("ascii", "ignore").decode()
    return [w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2 and w not in STOP]


def sim(a, b):
    A, B = toks(a), toks(b)
    if not A or not B:
        return str(a).lower()[:4] == str(b).lower()[:4]
    return any(x == y or (min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x))) or (len(x) >= 4 and len(y) >= 4 and x[:4] == y[:4])
               for x in A for y in B)


# ---------- 1) iddaa ----------
def fetch_iddaa():
    d = get_json("https://sportsbookv2.iddaa.com/sportsbook/events?st=1&type=0&version=0")["data"]
    out = []
    for e in d.get("events", []):
        lg = ICI.get(e.get("ci"))
        if not lg:
            continue
        ko = datetime.fromtimestamp(e["d"], timezone.utc)
        if ko < now or ko > now + timedelta(days=3):
            continue
        ms = {}
        for m in e.get("m", []):
            if m.get("t") == 1 and m.get("st") == 1:
                for o in m.get("o", []):
                    if o.get("odd", 0) > 1:
                        ms[o.get("n")] = o["odd"]
        if all(k in ms for k in ("1", "0", "2")):
            out.append({"id": e["i"], "lg": lg, "ko": ko, "h": e.get("hn", ""), "a": e.get("an", ""), "o": [ms["1"], ms["0"], ms["2"]]})
    return out


# ---------- 2) Pinnacle (OddsPapi) ----------
OP = "https://api.oddspapi.io/v4"


def op_get(st, path, params):
    month = now.strftime("%Y-%m")
    if st.get("op_month") != month:
        st["op_month"], st["op_used"] = month, 0
    if st.get("op_used", 0) >= MONTHLY_BUDGET:
        raise RuntimeError("aylık OddsPapi kotası doldu")
    p = dict(params)
    p["apiKey"] = OP_KEY
    for attempt in range(3):
        time.sleep(2)  # OddsPapi hız sınırı
        st["op_used"] = st.get("op_used", 0) + 1
        try:
            return get_json(f"{OP}/{path}", p, timeout=40)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                wait = min(30, int(e.headers.get("Retry-After") or 10))
                log(f"OddsPapi 429, {wait} sn bekleniyor")
                time.sleep(wait)
                continue
            raise


def op_tournaments(st):
    tid = st.get("op_tid") or {}
    missing = [lg for lg in OP_LEAGUES if lg not in tid]
    if missing:
        ts = op_get(st, "tournaments", {"sportId": 10})
        for lg in missing:
            country, names = OP_LEAGUES[lg]
            nl = [n.lower() for n in names]
            c = [t for t in ts if str(t.get("tournamentName", "")).lower() in nl]
            c2 = [t for t in c if country.lower() in str(t.get("categoryName", "")).lower()]
            pick = (c2 or [None])[0]
            if pick:
                tid[lg] = pick["tournamentId"]
                log("OddsPapi turnuva bulundu:", lg, pick["tournamentId"], pick.get("tournamentName"))
            else:
                log("OddsPapi turnuva bulunamadı:", lg)
        st["op_tid"] = tid
    return tid


def op_fixtures(st, tid):
    """Maç listesi en fazla 2 günde bir çekilir (kota)."""
    cache = st.get("op_fx") or {}
    fresh = cache.get("at") and (now - datetime.fromisoformat(cache["at"])) < timedelta(hours=44) and set(cache.get("lgs", [])) >= set(tid)
    if fresh:
        return cache["list"]
    lst = []
    for lg, t in tid.items():
        fx = op_get(st, "fixtures", {"sportId": 10, "tournamentId": t,
                                     "from": now.strftime("%Y-%m-%d"), "to": (now + timedelta(days=4)).strftime("%Y-%m-%d")})
        for f in fx or []:
            if not f.get("hasOdds", True):
                continue
            lst.append({"fid": f["fixtureId"], "lg": lg, "ko": f.get("startTime") or f.get("trueStartTime"),
                        "h": f.get("participant1Name", ""), "a": f.get("participant2Name", "")})
    st["op_fx"] = {"at": now.isoformat(), "list": lst, "lgs": sorted(tid)}
    log("OddsPapi maç listesi:", len(lst), "maç")
    return lst


def op_ms(st, fid):
    d = op_get(st, "odds", {"fixtureId": fid, "bookmakers": "pinnacle,bet365"})
    books = (d or {}).get("bookmakerOdds") or {}
    res = {}
    for slug in ("pinnacle", "bet365"):
        b = books.get(slug)
        if not b or b.get("suspended"):
            continue
        for mid in ("101", "10728"):
            m = (b.get("markets") or {}).get(mid)
            if not m:
                continue
            pr = []
            for oid in (mid, str(int(mid) + 1), str(int(mid) + 2)):
                o = (m.get("outcomes") or {}).get(oid)
                p = ((o or {}).get("players") or {}).get("0") or {}
                pr.append(p.get("price") if p.get("active", True) else None)
            if all(isinstance(x, (int, float)) and x > 1 for x in pr):
                res[slug] = pr
                break
    return res


def parse_ko(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def main():
    os.makedirs(DATA, exist_ok=True)
    st = load_state()
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) iddaa
    idd = []
    try:
        idd = fetch_iddaa()
        append_csv("iddaa.csv", ["zaman", "iddaa_id", "lig", "baslama", "ev", "dep", "ms1", "ms0", "ms2"],
                   [[ts, e["id"], e["lg"], e["ko"].strftime("%Y-%m-%dT%H:%MZ"), e["h"], e["a"], *e["o"]] for e in idd])
        log("iddaa:", len(idd), "maç kaydedildi")
        if not st.get("idd_ok"):
            st["idd_ok"] = tg_send(st, f"✅ Oran takip çalışıyor. iddaa bülteni okunabiliyor ({len(idd)} maç).")
    except Exception as e:
        log("iddaa okunamadı:", type(e).__name__, str(e)[:120])
        if not st.get("idd_fail_told"):
            st["idd_fail_told"] = tg_send(st, f"⚠️ iddaa bülteni bu sunucudan okunamadı ({type(e).__name__}). Muhtemelen yurt dışı erişimi engelli.")

    # 2) Pinnacle
    pin_rows = []
    if OP_KEY:
        try:
            tid = op_tournaments(st)
            fxl = op_fixtures(st, tid)
            done = st.setdefault("op_done", {})  # fid -> okunan pencereler
            for k, v in done.items():  # eski adlar
                done[k] = ["ilk" if x == "erken" else "son" if x == "gec" else x for x in v]
            for f in fxl:
                ko = parse_ko(f["ko"])
                if not ko:
                    continue
                left = (ko - now).total_seconds() / 3600
                got = done.get(f["fid"], [])
                win = None
                for name, lo, hi in WINDOWS:
                    if name not in got and lo <= left <= hi and (name == "ilk" or "ilk" in got):
                        win = name
                        break
                if win is None and "ilk" not in got and 0.15 <= left < 1.0:
                    win = "ilk"  # çok geç bulunan maç
                if not win:
                    continue
                try:
                    od = op_ms(st, f["fid"])
                except Exception as e:
                    log("OddsPapi odds hatası:", type(e).__name__, str(e)[:100])
                    break
                done.setdefault(f["fid"], []).append(win)
                for slug, pr in od.items():
                    pin_rows.append([ts, f["fid"], f["lg"], ko.strftime("%Y-%m-%dT%H:%MZ"), f["h"], f["a"], slug, win, *pr])
            # eski maçları durumdan temizle
            keep = {f["fid"] for f in fxl}
            st["op_done"] = {k: v for k, v in done.items() if k in keep}
            append_csv("pinnacle.csv", ["zaman", "fixture", "lig", "baslama", "ev", "dep", "buro", "pencere", "ms1", "ms0", "ms2"], pin_rows)
            log("Pinnacle/Bet365 okuma:", len(pin_rows), "satır · bu ay kullanılan:", st.get("op_used"), "/", MONTHLY_BUDGET)
        except Exception as e:
            log("OddsPapi hatası:", type(e).__name__, str(e)[:150])
    else:
        log("ODDSPAPI_KEY yok, Pinnacle atlandı")

    # 3) sinyal: Pinnacle ilk okumadan bu okumaya düştü, iddaa hâlâ yüksek
    if pin_rows:
        allpin = [r for r in read_csv("pinnacle.csv") if r["buro"] == "pinnacle"]
        sent = set(st.get("sent", []))
        for r in [r for r in pin_rows if r[6] == "pinnacle" and r[7] in ("orta", "son")]:
            fid = r[1]
            first = [x for x in allpin if x["fixture"] == fid and x["pencere"] in ("ilk", "erken")]
            if not first:
                continue
            e0 = [float(first[0][k]) for k in ("ms1", "ms0", "ms2")]
            c0 = [float(x) for x in r[8:11]]
            ko = parse_ko(r[3])
            im = [e for e in idd if e["lg"] == r[2] and abs((e["ko"] - ko).total_seconds()) <= 3600 and (sim(e["h"], r[4]) or sim(e["a"], r[5]))]
            if len(im) != 1:
                log("iddaa eşleşmedi:", r[4], "-", r[5], len(im))
                continue
            ie = im[0]
            inv = sum(1 / x for x in c0)
            fair = [1 / ((1 / x) / inv) for x in c0]  # Pinnacle marjsız adil oran
            for i, lab in enumerate(("1", "0", "2")):
                drop = (c0[i] - e0[i]) / e0[i] * 100
                if drop > -DROP_PCT:
                    continue
                val = ie["o"][i] / fair[i] - 1
                key = f"{fid}|{lab}"
                if key in sent:
                    continue
                sent.add(key)
                append_csv("sinyaller.csv", ["zaman", "lig", "baslama", "ev", "dep", "secenek", "pin_erken", "pin_gec", "pin_adil", "iddaa", "deger_pct", "iddaa_id"],
                           [[ts, r[2], r[3], ie["h"], ie["a"], "MS " + lab, e0[i], c0[i], round(fair[i], 3), ie["o"][i], round(val * 100, 1), ie["id"]]])
                kt = ko.astimezone(TR).strftime("%H:%M")
                head = "📉 SİNYAL" if val > 0 else "ℹ️ Düşüş var, iddaa da düşmüş"
                tg_send(st, f"{head} · {kt} {ie['h']} – {ie['a']}\nMS {lab}: Pinnacle {e0[i]:.2f} → {c0[i]:.2f} ({drop:.0f}%)\n"
                            f"Pinnacle adil oran {fair[i]:.2f} · iddaa şu an {ie['o'][i]:.2f} ({'+' if val >= 0 else ''}{val*100:.0f}%)\n"
                            f"Test sinyali; oynamadan önce iddaa'daki oranı kontrol et.")
        st["sent"] = sorted(sent)[-500:]

    # 4) günlük rapor (TR 10:00 sonrası ilk çalışma)
    if True:
        sig = read_csv("sinyaller.csv")
        iddrows = read_csv("iddaa.csv")
        lines = []
        for s in sig:
            if s["baslama"] > now.strftime("%Y-%m-%dT%H:%MZ"):
                continue  # maç henüz oynanmadı
            hist = [r for r in iddrows if r["iddaa_id"] == s["iddaa_id"] and r["zaman"] >= s["zaman"]]
            if not hist:
                continue
            k = {"MS 1": "ms1", "MS 0": "ms0", "MS 2": "ms2"}[s["secenek"]]
            o0 = float(s["iddaa"])
            last = float(hist[-1][k])
            fell = next((r for r in hist if float(r[k]) < o0 - 1e-9), None)
            lag = None
            if fell:
                lag = (datetime.fromisoformat(fell["zaman"].replace("Z", "+00:00")) - datetime.fromisoformat(s["zaman"].replace("Z", "+00:00"))).total_seconds() / 60
            lines.append(f"{s['ev']}–{s['dep']} {s['secenek']}: sinyalde {o0:.2f}, maç başı {last:.2f}"
                         + (f", iddaa {lag:.0f} dk sonra düştü" if lag is not None else ", iddaa düşmedi"))
        st.setdefault("reported", [])
        new = [l for l in lines if l not in st["reported"]]
        st["reported"] = (st["reported"] + new)[-300:]
        if new:
            head = f"📊 Sinyal sonuçları · OddsPapi bu ay {st.get('op_used', 0)}/{MONTHLY_BUDGET}"
            tg_send(st, head + "\n" + "\n".join(new[:25]))

    st["last_run"] = ts
    st["last_log"] = log_lines[-20:]
    save_state(st)


if __name__ == "__main__":
    main()
