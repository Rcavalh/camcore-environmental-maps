#!/usr/bin/env python3
"""Convert the Camcore provenance catalogue to a compact browser dataset."""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

def clean(value): return (value or '').strip()
def number(value):
    try:
        out=float(str(value).replace(',','.')); return out if math.isfinite(out) else None
    except Exception:return None
def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument('--source',type=Path,required=True); parser.add_argument('--web',type=Path,required=True); args=parser.parse_args()
    records=[]
    with args.source.open(encoding='utf-8-sig',errors='replace',newline='') as handle:
        for row in csv.DictReader(handle):
            lat,lon=number(row.get('Latitude')),number(row.get('Longitude'))
            species=clean(row.get('Species')); name=clean(row.get('Provenance Name'))
            if not species or not name or lat is None or lon is None or not(-90<=lat<=90 and -180<=lon<=180):continue
            group='eucalypts' if clean(row.get('Species group')).lower()=='eucalypt' else 'pines' if clean(row.get('Species group')).lower()=='pine' else 'other'
            records.append({'species':species,'group':group,'name':name,'code':clean(row.get('Prov Code TP')) or clean(row.get('Prov Abbreviation Unique')),'lat':round(lat,6),'lon':round(lon,6),'country':clean(row.get('Country  ')),'state':clean(row.get('State or\n Department')),'municipality':clean(row.get('Municipality')),'altitudeMin':number(row.get('Altitude Min')),'altitudeMax':number(row.get('Altitude Max')),'yearFirst':number(row.get('Year First')),'standType':clean(row.get('Type Stand'))})
    groups=defaultdict(set)
    for item in records: groups[item['group']].add(item['species'])
    payload={'groups':{key:sorted(value) for key,value in groups.items()},'records':records,'speciesCount':len({x['species'] for x in records}),'pointCount':len(records),'countryCount':len({x['country'] for x in records if x['country']})}
    (args.web/'provenances.generated.js').write_text('window.CAMCORE_PROVENANCES='+json.dumps(payload,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
    print(f'PROVENANCE_CATALOG_OK={payload["speciesCount"]} species; {payload["pointCount"]} points')
    return 0
if __name__=='__main__':raise SystemExit(main())
