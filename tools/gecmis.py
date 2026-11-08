"""Geniş geçmiş veri: football-data ana ligleri (22 lig, 2015/16'dan beri) + ek ülkeler (2019'dan beri)."""
import csv, io, urllib.request, sys
MAINL = ['E0','E1','E2','E3','EC','SC0','SC1','SC2','SC3','D1','D2','I1','I2','SP1','SP2','F1','F2','N1','B1','P1','T1','G1']
S = ['1516','1617','1718','1819','1920','2021','2122','2223','2324','2425','2526','2627']
NEW = ['ARG','AUT','BRA','CHN','DNK','FIN','IRL','JPN','MEX','NOR','POL','ROU','RUS','SWE','SWZ','USA']
COLS = ['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG',
        'B365H','B365D','B365A','B365>2.5','B365<2.5','B365CH','B365CD','B365CA','B365C>2.5','B365C<2.5',
        'PSH','PSD','PSA','P>2.5','P<2.5','PSCH','PSCD','PSCA','PC>2.5','PC<2.5']
def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=90).read().decode('latin-1')
out = io.StringIO(); w = csv.writer(out, lineterminator='\n'); w.writerow(COLS); n = 0; stat = {}
for lg in MAINL:
    for s in S:
        try: raw = get(f'https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv')
        except Exception as e: print('yok', lg, s, e); continue
        for r in csv.DictReader(io.StringIO(raw.lstrip('﻿'))):
            if not (r.get('HomeTeam') or '').strip() or not (r.get('FTHG') or '').strip(): continue
            r['Div'] = lg
            w.writerow([(r.get(c) or '').strip() for c in COLS]); n += 1; stat[lg] = stat.get(lg, 0) + 1
for c in NEW:
    try: raw = get(f'https://www.football-data.co.uk/new/{c}.csv')
    except Exception as e: print('yok', c, e); continue
    for r in csv.DictReader(io.StringIO(raw.lstrip('﻿'))):
        d = (r.get('Date') or '').strip()
        if not d or int(d[-4:]) < 2019 or not (r.get('HG') or '').strip(): continue
        row = {'Div': c, 'Date': d, 'HomeTeam': r.get('Home'), 'AwayTeam': r.get('Away'), 'FTHG': r.get('HG'), 'FTAG': r.get('AG'),
               'B365CH': r.get('B365CH'), 'B365CD': r.get('B365CD'), 'B365CA': r.get('B365CA'),
               'PSCH': r.get('PSCH'), 'PSCD': r.get('PSCD'), 'PSCA': r.get('PSCA')}
        w.writerow([(row.get(k) or '').strip() for k in COLS]); n += 1; stat[c] = stat.get(c, 0) + 1
open('data/gecmis.csv', 'w', encoding='utf-8').write(out.getvalue())
print('satir', n); print(stat)
