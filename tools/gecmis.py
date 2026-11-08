import csv, io, urllib.request
L = ['E0','E1','SP1','I1','D1','F1','T1','N1','P1','B1']
S = ['1920','2021','2122','2223','2324','2425','2526','2627']
COLS = ['Div','Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG',
        'B365H','B365D','B365A','B365>2.5','B365<2.5','B365CH','B365CD','B365CA','B365C>2.5','B365C<2.5',
        'PSH','PSD','PSA','P>2.5','P<2.5','PSCH','PSCD','PSCA','PC>2.5','PC<2.5']
out = io.StringIO(); w = csv.writer(out, lineterminator='\n'); w.writerow(COLS); n = 0
for lg in L:
    for s in S:
        raw = urllib.request.urlopen(urllib.request.Request(f'https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv', headers={'User-Agent':'Mozilla/5.0'}), timeout=60).read().decode('latin-1')
        for r in csv.DictReader(io.StringIO(raw.lstrip('﻿'))):
            if not (r.get('HomeTeam') or '').strip() or not (r.get('FTHG') or '').strip():
                continue
            r['Div'] = lg
            w.writerow([(r.get(c) or '').strip() for c in COLS]); n += 1
open('data/gecmis.csv', 'w', encoding='utf-8').write(out.getvalue())
print('satir', n)
