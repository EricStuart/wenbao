import json, re, collections, pathlib, shutil

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / 'dist/data'
SOURCE = ROOT / 'sources'
SOURCE.mkdir(exist_ok=True)
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write(p, d): p.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
def norm(s): return re.sub(r'[\s\-－—·，、（）()]+','',s or '')
raw=read(SOURCE/'national-heritage-sites.json')
research=read(ROOT/'research_sources.json')
rows=raw['rows'].copy()
for m in research['merges']:
    old=[r for r in rows if r['name_zh'] in m['from_names']]
    rows=[r for r in rows if r not in old]
    rows.append({**m,'aliases':m['from_names'],'history':old})
rows.extend(research['additions'])
regions=read(SOURCE/'regions.json')['rows']
regions={r['id']:r['name_zh'] for r in regions}
admin=read(SOURCE/'admin.json')
prov={p['code']+'0000':p for p in admin}
china=read(DATA/'china.json')
centers={str(f['properties']['adcode']):f['properties'].get('centroid',f['properties'].get('center')) for f in china['features'] if 'adcode' in f['properties']}
atlas=read(SOURCE/'sites.json')['rows']
atlasidx=collections.defaultdict(list)
for r in atlas:
    if 'national' in r['designations']: atlasidx[(r['region_id'],norm(r['name_zh']))].append(r)
gis=[]
for f in SOURCE.glob('arcgis-*.json'): gis += [r['attributes'] for r in read(f)['features']]
gisidx=collections.defaultdict(list)
for r in gis: gisidx[(r['xzqhdm'],norm(r['mc']))].append(r)
categories={'古建筑及历史纪念建筑物':'古建筑','革命遗址及革命纪念建筑物':'近现代重要史迹及代表性建筑','石窟寺':'石窟寺及石刻','石刻及其他':'石窟寺及石刻','其它':'其他'}
era_rules=[('史前','旧石器|新石器|史前'),('夏商周','夏|商|周|春秋|战国'),('秦汉','秦|汉'),('魏晋南北朝','魏|晋|南北朝|北齐|北周|南朝|北朝'),('隋唐五代','隋|唐|五代'),('宋辽金夏','宋|辽|金|西夏'),('元','元'),('明','明'),('清','清'),('近现代',r'近现代|民国|中华人民|19\d\d|20\d\d')]
result=[]
for i,r in enumerate(rows):
    names=[r['name_zh']]+r.get('aliases',[])
    candidates=[]; matched=None; coordinate_source=None
    for n in names:
        candidates=atlasidx.get((r['region_id'],norm(n)),[])
        if len(candidates)==1:
            a=candidates[0]; matched=[a['lon'],a['lat']];coordinate_source='Atlas of China';break
    g=None
    for n in names:
        candidates=gisidx.get((r['region_id'],norm(n)),[])
        if len(candidates)==1:
            g=candidates[0];break
    if not matched and g: matched=[g['lon'],g['lat']];coordinate_source='ArcGIS 公开地理数据'
    # Derive only unambiguous administrative matches; preserve the original historical address.
    address=(g['dz'] if g else '') or r.get('address','')
    p=prov.get(r['region_id']); city='待核对'; county='待核对'
    if p:
        found=[]
        for c in p['children']:
            for k in c.get('children',[]):
                if k['name'] in address: found.append((c['name'],k['name']))
        found=list(dict.fromkeys(found))
        if len(found)==1: city,county=found[0]
        elif len(found)>1:
            cities=set(c for c,k in found); city=next(iter(cities)) if len(cities)==1 else '跨市';county='跨区县'
        else:
            cities=[c['name'] for c in p['children'] if c['name'] not in ['市辖区','县'] and c['name'] in address]
            if len(cities)==1:city=cities[0]
        if p['code'] in ['11','12','31','50']: city=p['name']
        elif city in ['市辖区','县']:city='待核对'
    cat=categories.get(r['category'],r['category']);era=r.get('era') or '年代未注明'
    tags=[label for label,rule in era_rules if re.search(rule,era)]
    r.update(id=f"wb-{r['batch']}-{r['seq'] or ('s'+str(i))}",name=r['name_zh'],province=regions.get(r['region_id'],'跨省'),city=city,county=county,category_original=r['category'],category=cat,era=era,tags=tags,coordinates=matched,coordinate_source=coordinate_source,location_status='参考点位' if matched else '待定位')
    result.append(r)
result.sort(key=lambda r:(r['batch'],r['seq'] or 9999,r['name']))
assert len(result)==5058, len(result)
assert len({r['id'] for r in result})==5058
assert all(not r['coordinates'] or 70<r['coordinates'][0]<140 and 15<r['coordinates'][1]<56 for r in result)
meta={'checked_at':'2026-11-06','count':len(result),'located':sum(bool(r['coordinates']) for r in result),'city_resolved':sum(r['city']!='待核对' for r in result),'county_resolved':sum(r['county'] not in ['待核对','跨区县'] for r in result),'categories':list(dict.fromkeys(categories.values())),'research':research,'attribution':raw['attribution'],'license':raw['license']}
write(DATA/'heritage.json',{'meta':meta,'rows':result})
write(DATA/'research.json',research)
write(ROOT/'data-audit.json',{'count':len(result),'located':meta['located'],'missing_coordinates':[r['name'] for r in result if not r['coordinates']],'by_batch':dict(collections.Counter(r['batch'] for r in result)),'by_category':dict(collections.Counter(r['category'] for r in result)),'city_resolved':meta['city_resolved'],'county_resolved':meta['county_resolved']})
print(json.dumps({k:v for k,v in meta.items() if k not in ['research','categories']},ensure_ascii=False))
