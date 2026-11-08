"""Piyasa verisi: son 5 yıl, ana 22 lig + 16 ülke. Pinnacle, Bet365, piyasa en yüksek (Max) ve ortalama (Avg) oranları."""
import csv, io, urllib.request
from datetime import date, timedelta
MAINL = ['E0','E1','E2','E3','EC','SC0','SC1','SC2','SC3','D1','D2','I1','I2','SP1','SP2','F1','F2','N1','B1','P1','T1','G1']
S = ['2122','2223','2324','2425','2526','2627']
NEW = ['ARG','AUT','BRA','CHN','DNK','FIN','IRL','JPN','MEX','NOR','POL','ROU','RUS','SWE','SWZ','USA']
CUT = date.today() - timedelta(days=5*365+1)
COLS = ['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG',
        'PSH','PSD','PSA','PSCH','PSCD','PSCA','MaxH','MaxD','MaxA','AvgH','AvgD','AvgA','MaxCH','MaxCD','MaxCA','AvgCH','AvgCD','AvgCA',
        'B365H','B365D','B365A','B365CH','B365CD','B365CA',
        'P>2.5','P<2.5','PC>2.5','PC<2.5','Max>2.5','Max<2.5','Avg>2.5','Avg<2.5','MaxC>2.5','MaxC<2.5','AvgC>2.5','AvgC<2.5',
        'BWH','BWD','BWA','BWCH','BWCD','BWCA','IWH','IWD','IWA','IWCH','IWCD','IWCA','WHH','WHD','WHA','WHCH','WHCD','WHCA','VCH','VCD','VCA','VCCH','VCCD','VCCA','1XBH','1XBD','1XBA','1XBCH','1XBCD','1XBCA','BFH','BFD','BFA','BFCH','BFCD','BFCA','BFEH','BFED','BFEA','BFECH','BFECD','BFECA','BFDH','BFDD','BFDA','BFDCH','BFDCD','BFDCA','BMGMH','BMGMD','BMGMA','BMGMCH','BMGMCD','BMGMCA','BVH','BVD','BVA','BVCH','BVCD','BVCA','CLH','CLD','CLA','CLCH','CLCD','CLCA','LBH','LBD','LBA','LBCH','LBCD','LBCA','SKBH','SKBD','SKBA','SKBCH','SKBCD','SKBCA','BFE>2.5','BFE<2.5','BFEC>2.5','BFEC<2.5','B365>2.5','B365<2.5','B365C>2.5','B365C<2.5']
def recent(d):
    try:
        a, b, c = d.split('/'); y = int(c); y = y + 2000 if y < 100 else y
        return date(y, int(b), int(a)) >= CUT
    except Exception:
        return False
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=90).read().decode('latin-1')
out = io.StringIO(); w = csv.writer(out, lineterminator='\n'); w.writerow(COLS); n = 0
for lg in MAINL:
    for s in S:
        try: raw = get(f'https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv')
        except Exception as e: print('yok', lg, s, e); continue
        for r in csv.DictReader(io.StringIO(raw.lstrip('﻿'))):
            if not (r.get('HomeTeam') or '').strip() or not (r.get('FTHG') or '').strip(): continue
            if not recent((r.get('Date') or '').strip()): continue
            r['Div'] = lg
            w.writerow([(r.get(c) or '').strip() for c in COLS]); n += 1
for c in NEW:
    try: raw = get(f'https://www.football-data.co.uk/new/{c}.csv')
    except Exception as e: print('yok', c, e); continue
    for r in csv.DictReader(io.StringIO(raw.lstrip('﻿'))):
        d = (r.get('Date') or '').strip()
        if not d or not recent(d) or not (r.get('HG') or '').strip(): continue
        r2 = dict(r); r2.update({'Div': c, 'HomeTeam': r.get('Home'), 'AwayTeam': r.get('Away'), 'FTHG': r.get('HG'), 'FTAG': r.get('AG')})
        w.writerow([(r2.get(k) or '').strip() for k in COLS]); n += 1
open('data/piyasa2.csv', 'w', encoding='utf-8').write(out.getvalue())
print('satir', n)
