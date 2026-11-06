"""Cache DataV province/city boundaries for offline administrative drill-down."""
import concurrent.futures, json, pathlib, subprocess, time

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / 'dist/data/boundaries'
OUT.mkdir(exist_ok=True)
china = json.loads((ROOT / 'dist/data/china.json').read_text(encoding='utf-8'))
rows = json.loads((ROOT / 'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
province_ids = sorted({r['region_id'] for r in rows})

def fetch(code):
    path = OUT / f'{code}.json'
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if data.get('features'): return str(code), data
        except Exception: pass
    for attempt in range(2):
        response = subprocess.run(['curl.exe','-sSL','--compressed','--max-time','25',
            f'https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json'],capture_output=True)
        try:
            data = json.loads(response.stdout)
            assert data['type'] == 'FeatureCollection' and data['features']
            path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            return str(code), data
        except Exception:
            if attempt == 0: time.sleep(.3)
    return str(code), None

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    provinces = dict(pool.map(fetch,province_ids))
print('Province files:',sum(v is not None for v in provinces.values()),flush=True)
city_codes = sorted({str(f['properties']['adcode']) for data in provinces.values() if data
    for f in data['features'] if f['properties'].get('level') == 'city' and f['properties'].get('childrenNum',0)>0})
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    cities = {}
    for code,data in pool.map(fetch,city_codes):
        cities[code] = data
        if len(cities)%50==0: print('City files processed:',len(cities),'/',len(city_codes),flush=True)
report={'source':'https://geo.datav.aliyun.com/','downloaded_at':'2026-11-06',
    'provinces':len(provinces),'cities':len(cities),'missing':[k for k,v in {**provinces,**cities}.items() if not v],
    'files':sorted(k for k,v in {**provinces,**cities}.items() if v)}
(OUT/'index.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)

# Keep administrative names/codes separate from geometry, including municipal
# and province-administered county groupings.
raw_admin = json.loads((ROOT/'sources/admin.json').read_text(encoding='utf-8'))
province_names = {r['region_id']:r['province'] for r in rows}
index=[]
for p in raw_admin:
    code=p['code']+'0000'
    if code not in province_names: continue
    children=[]
    for c in p['children']:
        municipal=p['code'] in ['11','12','31','50']
        name=p['name'] if municipal else c['name']
        city_code=code if municipal else c['code'].ljust(6,'0')
        counties=[{'code':k['code'],'name':k['name']} for k in c.get('children',[])]
        previous=next((x for x in children if x['name']==name),None)
        if previous: previous['counties']+=counties
        else: children.append({'code':city_code,'name':name,'counties':counties,'municipality':municipal})
    index.append({'code':code,'name':province_names[code],'fullName':p['name'],'cities':children})
(OUT.parent/'admin-index.json').write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
