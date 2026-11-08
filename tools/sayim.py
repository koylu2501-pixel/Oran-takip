import csv, io, urllib.request, json
L = ['E0','E1','SP1','I1','D1','F1','T1','N1','P1','B1']
S = ['1920','2021','2122','2223','2324','2425','2526','2627']
out = {}
for lg in L:
    for s in S:
        url = f'https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv'
        try:
            raw = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60).read().decode('latin-1')
        except Exception as e:
            out[f'{lg} {s}'] = {'hata': str(e)[:80]}
            continue
        rows = list(csv.DictReader(io.StringIO(raw.lstrip('﻿'))))
        rows = [r for r in rows if (r.get('HomeTeam') or '').strip()]
        played = [r for r in rows if (r.get('FTHG') or '').strip() != '']
        teams = {r['HomeTeam'].strip() for r in rows} | {r['AwayTeam'].strip() for r in rows}
        keys = [(r.get('Date'), r['HomeTeam'].strip(), r['AwayTeam'].strip()) for r in played]
        pairs = [(r['HomeTeam'].strip(), r['AwayTeam'].strip()) for r in played]
        f = lambda k: sum(1 for r in played if (r.get(k) or '').strip() not in ('', '0'))
        out[f'{lg} {s}'] = {'satir': len(rows), 'oynanmis': len(played), 'takim': len(teams),
                            'tekrar_mac': len(keys) - len(set(keys)), 'ayni_eslesme_tekrar': len(pairs) - len(set(pairs)),
                            'B365H': f('B365H'), 'B365CH': f('B365CH'), 'HTHG': f('HTHG'), 'PSH': f('PSH'), 'PSCH': f('PSCH'),
                            'ilk': played[0].get('Date') if played else None, 'son': played[-1].get('Date') if played else None}
json.dump(out, open('data/sayim.json', 'w'), indent=1)
print(json.dumps(out)[:3000])
