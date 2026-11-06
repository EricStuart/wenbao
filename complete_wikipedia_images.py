"""Fill local photo gaps using article illustrations, Wikidata P18 and Commons.

Only attributable Commons files are stored. Direct Commons searches require both
the monument name and location evidence; generic destination photos are rejected.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import re
import fetch_wikipedia as w

WIKIDATA='https://www.wikidata.org/w/api.php'
GENERIC=re.compile(r'flag[ _]of|icon|logo|locator|location[ _]map|prfc[ _]map|red[ _]pog|commons[ _]|disambig|golden[ _]sun[ _]bird|太阳神鸟|全国重点文物保护单位.*标志|文物保护单位.*标志',re.I)
GALLERY={}
ENTITIES={}

def restore_gallery():
    for path in w.CACHE.glob('*.json'):
        try:result=json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):continue
        if not isinstance(result,dict):continue
        ENTITIES.update(result.get('entities',{}))
        query=result.get('query',{});pages=query.get('pages',[])
        if 'images' not in result.get('limits',{}) and not any('images' in p for p in pages):continue
        aliases={p['from']:p['to'] for key in ('normalized','redirects') for p in query.get(key,[])}
        for p in pages:
            if p.get('ns',0)==0:
                GALLERY[p['title']]={'qid':p.get('pageprops',{}).get('wikibase_item'),'files':[x['title'].removeprefix('File:') for x in p.get('images',[]) if usable_name(x['title'])][:4]}
        for alias in aliases:
            title=alias;seen=set()
            while title in aliases and title not in seen:
                seen.add(title);title=aliases[title]
            if title in GALLERY:GALLERY[alias]=GALLERY[title]

def usable_name(name):
    return bool(re.search(r'\.(jpe?g|png|webp|tiff?)$',name,re.I)) and not GENERIC.search(name)

def article_files(titles):
    known={title:GALLERY[title] for title in titles if title in GALLERY}
    titles=[title for title in titles if title not in known]
    if not titles:return known
    if len(w.urllib.parse.urlencode({'titles':'|'.join(titles)}))>6000 and len(titles)>1:
        middle=len(titles)//2
        return {**known,**article_files(titles[:middle]),**article_files(titles[middle:])}
    result=w.api({'action':'query','titles':'|'.join(titles),'redirects':1,'prop':'images|pageprops','imlimit':500})
    query=result.get('query',{})
    pages={p['title']:p for p in query.get('pages',[])}
    aliases={p['from']:p['to'] for key in ('normalized','redirects') for p in query.get(key,[])}
    output={}
    for title in titles:
        resolved=title;seen=set()
        while resolved in aliases and resolved not in seen:
            seen.add(resolved);resolved=aliases[resolved]
        page=pages.get(resolved,{})
        output[title]={'qid':page.get('pageprops',{}).get('wikibase_item'),'files':[p['title'].removeprefix('File:') for p in page.get('images',[]) if usable_name(p['title'])][:4]}
    return {**known,**output}

def entity_files(ids):
    known={id:ENTITIES[id] for id in ids if id in ENTITIES}
    ids=[id for id in ids if id not in known]
    result=w.api({'action':'wbgetentities','ids':'|'.join(ids),'props':'claims'},WIKIDATA) if ids else {}
    output={}
    for entity_id,entity in {**known,**result.get('entities',{})}.items():
        claims=entity.get('claims',{}).get('P18',[])
        output[entity_id]=[c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in claims if c.get('rank')!='deprecated']
    return output

def commons_matches(row, page):
    info=(page.get('imageinfo') or [{}])[0];meta=info.get('extmetadata',{})
    text=w.plain(page.get('title','')+' '+meta.get('ImageDescription',{}).get('value','')).lower()
    names=w.article_names(row)
    if not any(w.normalized(n).lower() in w.normalized(text) for n in names if len(n)>=3):return False
    county=row.get('county','')
    siblings=w.COUNTIES.get((row.get('province'),row.get('city')),[])
    if county in siblings and county not in text and any(other!=county and other in text for other in siblings):return False
    places=[row.get(k,'') for k in ('city','county')]
    places=[place for place in places if place and place not in ('待核对','跨市','跨区县')]
    if not places:places=[row.get('province',''),row.get('region','')]
    variants=[variant for place in places for variant in (place,re.sub(r'(自治县|自治州|地区|市|县|区)$','',place)) if len(variant)>=2]
    return any(place.lower() in text for place in variants)

def search_commons(row):
    result=w.api({'action':'query','generator':'search','gsrsearch':'"'+row['name']+'" filetype:bitmap',
                  'gsrnamespace':6,'gsrlimit':5,'prop':'imageinfo','iiprop':'url|extmetadata|mime|size|thumbmime',
                  'iiurlwidth':320,'iiextmetadatalanguage':'zh',
                  'iiextmetadatafilter':'Artist|Credit|LicenseShortName|LicenseUrl|ImageDescription'},w.COMMONS)
    for page in result.get('query',{}).get('pages',[]):
        name=page['title'].removeprefix('File:')
        if usable_name(name) and commons_matches(row,page):
            photo=w.store_image(name,page)
            if photo:
                photo['matchEvidence']='维基共享资源名称与所在地一致'
                return photo
    return None

def search_commons_batch(rows):
    terms=list(dict.fromkeys(name for row in rows for name in w.article_names(row)))
    # CirrusSearch mixes OR and keyword filters unexpectedly. Keep a pure OR
    # query, restrict namespace through the API, and filter raster files locally.
    query=' OR '.join('"'+name.replace('"','')+'"' for name in terms)
    if len(query)>700 and len(rows)>1:
        middle=len(rows)//2
        return {**search_commons_batch(rows[:middle]),**search_commons_batch(rows[middle:])}
    old_params={'format':'json','formatversion':2,'maxlag':5,'action':'query','generator':'search','gsrsearch':query,
                'gsrnamespace':6,'gsrlimit':50,'prop':'imageinfo','iiprop':'url|extmetadata|mime|size|thumbmime',
                'iiurlwidth':320,'iiextmetadatalanguage':'zh',
                'iiextmetadatafilter':'Artist|Credit|LicenseShortName|LicenseUrl|ImageDescription'}
    key=w.hashlib.sha256((w.COMMONS+json.dumps(old_params,sort_keys=True)).encode()).hexdigest()
    cached=w.CACHE/(key+'.json')
    if cached.exists():
        pages=json.loads(cached.read_text(encoding='utf-8')).get('query',{}).get('pages',[])
        return {row['id']:[page for page in pages if usable_name(page['title']) and commons_matches(row,page)][:4] for row in rows}
    result=w.api({'action':'query','list':'search','srsearch':query,'srnamespace':6,'srlimit':50,'srprop':'snippet'},w.COMMONS)
    hits=result.get('query',{}).get('search',[])
    candidates={}
    for row in rows:
        names=[w.normalized(n).lower() for n in w.article_names(row) if len(n)>=3]
        candidates[row['id']]=[hit['title'].removeprefix('File:') for hit in hits if usable_name(hit['title']) and any(n in w.normalized(w.plain(hit['title']+' '+hit.get('snippet',''))).lower() for n in names)][:4]
    files=list(dict.fromkeys(name for names in candidates.values() for name in names))
    metadata=w.image_metadata(files,320) if files else {}
    return {row['id']:[metadata[name.replace('_',' ')] for name in candidates[row['id']] if commons_matches(row,metadata.get(name.replace('_',' '),{}))] for row in rows}

def attach(record_id,photo):
    if not w.photo_allowed(record_id,photo):return False
    path=w.DATA/(record_id+'.json')
    entry=json.loads(path.read_text(encoding='utf-8'))
    if entry.get('image'):return False
    entry['image']=photo;w.save_json(path,entry);return True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--commons',action='store_true')
    parser.add_argument('--commons-only',action='store_true')
    args=parser.parse_args()
    restore_gallery()
    rows=json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    entries={r['id']:json.loads((w.DATA/(r['id']+'.json')).read_text(encoding='utf-8')) for r in rows}
    needs=[r for r in rows if not entries[r['id']].get('image')]
    wiki_needs=[] if args.commons_only else [r for r in needs if entries[r['id']].get('status')=='ready']
    titles=list(dict.fromkeys(entries[r['id']]['title'] for r in wiki_needs))
    gallery={};errors=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(article_files,b):b for b in w.chunks(titles,50)}
        for i,f in enumerate(as_completed(tasks),1):
            try:gallery.update(f.result())
            except Exception as e:errors.append({'stage':'article_files','error':str(e)})
            if i%10==0 or i==len(tasks):w.log(f'Article illustrations: {i}/{len(tasks)} batches')
    qids=list(dict.fromkeys(g['qid'] for g in gallery.values() if g.get('qid')))
    entity_images={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(entity_files,b):b for b in w.chunks(qids,50)}
        for i,f in enumerate(as_completed(tasks),1):
            try:entity_images.update(f.result())
            except Exception as e:errors.append({'stage':'wikidata','error':str(e)})
            if i%10==0 or i==len(tasks):w.log(f'Wikidata image links: {i}/{len(tasks)} batches')
    candidates={};trusted_names={}
    for row in wiki_needs:
        if json.loads((w.DATA/(row['id']+'.json')).read_text(encoding='utf-8')).get('image'):continue
        article=entries[row['id']];g=gallery.get(article['title'],{})
        trusted_names[row['id']]={n.replace('_',' ') for n in entity_images.get(g.get('qid'),[]) if n}
        names=[*entity_images.get(g.get('qid'),[]),*g.get('files',[])]
        candidates[row['id']]=list(dict.fromkeys(n for n in names if n and usable_name(n)))[:4]
    names=list(dict.fromkeys(n for values in candidates.values() for n in values))
    metadata={}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(w.image_metadata,b,320):b for b in w.chunks(names,35)}
        for i,f in enumerate(as_completed(tasks),1):
            try:metadata.update(f.result())
            except Exception as e:errors.append({'stage':'metadata','error':str(e)})
            if i%10==0 or i==len(tasks):w.log(f'Extra photo metadata: {i}/{len(tasks)} batches')
    def fill(row):
        current=json.loads((w.DATA/(row['id']+'.json')).read_text(encoding='utf-8'))
        if current.get('image'):return False
        for name in candidates.get(row['id'],[]):
            try:
                meta=metadata.get(name.replace('_',' '),{})
                is_entity_image=name.replace('_',' ') in trusted_names.get(row['id'],set())
                if not is_entity_image and not commons_matches(row,meta):continue
                photo=w.store_image(name,meta)
                if photo:
                    photo['matchEvidence']='对应 Wikidata 条目的 P18 配图' if is_entity_image else '对应百科配图的名称与所在地一致'
                    return attach(row['id'],photo)
            except Exception as e:errors.append({'stage':'image','id':row['id'],'error':str(e)})
        return False
    added=0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(fill,r):r for r in wiki_needs}
        for i,f in enumerate(as_completed(tasks),1):
            try:added+=bool(f.result())
            except Exception as e:errors.append({'stage':'fill','error':str(e)})
            if i%100==0 or i==len(tasks):w.log(f'Illustration gaps: {i}/{len(tasks)}, {added} photos added')
    if args.commons or args.commons_only:
        remaining=[r for r in rows if not json.loads((w.DATA/(r['id']+'.json')).read_text(encoding='utf-8')).get('image')]
        found={}
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks={pool.submit(search_commons_batch,b):b for b in w.chunks(remaining,10)}
            for i,f in enumerate(as_completed(tasks),1):
                try:found.update(f.result())
                except Exception as e:errors.append({'stage':'commons_search','ids':[r['id'] for r in tasks[f]],'error':str(e)})
                if i%20==0 or i==len(tasks):w.log(f'Commons lookup: {i}/{len(tasks)} batches')
        def fill_commons(row):
            for page in found.get(row['id'],[]):
                try:
                    photo=w.store_image(page['title'].removeprefix('File:'),page)
                    if photo:
                        photo['matchEvidence']='维基共享资源名称与所在地一致'
                        return attach(row['id'],photo)
                except Exception as e:errors.append({'stage':'commons','id':row['id'],'error':str(e)})
            return False
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            tasks={pool.submit(fill_commons,r):r for r in remaining if found.get(r['id'])}
            for i,f in enumerate(as_completed(tasks),1):
                try:added+=bool(f.result())
                except Exception as e:errors.append({'stage':'commons_fill','error':str(e)})
                if i%50==0 or i==len(tasks):w.log(f'Commons photos: {i}/{len(tasks)}, {added} photos added')
    entries=[json.loads((w.DATA/(r['id']+'.json')).read_text(encoding='utf-8')) for r in rows]
    report={'total':len(entries),'withText':sum(bool(r.get('text')) for r in entries),'withWikipediaText':sum(r.get('status')=='ready' for r in entries),'withPhoto':sum(bool(r.get('image')) for r in entries),'addedPhotos':added,'errors':errors,'missingPhotos':[{'id':r['id'],'name':r['name']} for r in entries if not r.get('image')]}
    w.save_json(w.ROOT/'wikipedia-images-audit.json',report)
    w.log('Photo completion: '+json.dumps({k:v for k,v in report.items() if k not in ('errors','missingPhotos')}))

if __name__=='__main__':main()
