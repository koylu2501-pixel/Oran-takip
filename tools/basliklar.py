import csv, io, urllib.request, json
out = {}
for lg, s in [('E0','2425'),('T1','2425'),('E0','2526'),('E0','2627'),('B1','2223')]:
    raw = urllib.request.urlopen(urllib.request.Request(f'https://www.football-data.co.uk/mmz4281/{s}/{lg}.csv', headers={'User-Agent':'Mozilla/5.0'}), timeout=60).read().decode('latin-1')
    rows = list(csv.DictReader(io.StringIO(raw.lstrip('﻿'))))
    rows = [r for r in rows if (r.get('FTHG') or '').strip()]
    hdr = list(rows[0].keys()) if rows else []
    out[f'{lg} {s}'] = {'n': len(rows), 'basliklar': hdr,
        'dolu': {h: sum(1 for r in rows if (r.get(h) or '').strip()) for h in hdr if h.startswith('P') or h.startswith('AH') or h.startswith('B365')}}
json.dump(out, open('data/basliklar.json','w'), indent=1)
