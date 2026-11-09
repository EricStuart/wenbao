"""Recover missing introductions and photos with cautious batched lookups."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import json
import re
import fetch_wikipedia as w
import complete_wikipedia_images as photos


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photos-only',action='store_true',help='Only supplement already reviewed articles')
    args=parser.parse_args()
    rows=json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    entries={r['id']:json.loads((w.DATA/(r['id']+'.json')).read_text(encoding='utf-8')) for r in rows}
    missing=[] if args.photos_only else [r for r in rows if entries[r['id']].get('status')=='catalogue']
    errors=[];matched={}
    def search(batch):
        names=list(dict.fromkeys(r['name'] for r in batch if len(r['name'])>=3))
        query=' OR '.join('"'+n.replace('"','')+'"' for n in names)
        result=w.api({'action':'query','list':'search','srsearch':query,'srnamespace':0,'srlimit':50,'srprop':'snippet'})
        hits=result.get('query',{}).get('search',[])
        candidates={}
        for row in batch:
            terms=[w.normalized(n) for n in w.article_names(row) if len(n)>=3]
            candidates[row['id']]=[hit['title'] for hit in hits if any(n in w.normalized(w.plain(hit['title']+' '+hit.get('snippet',''))) for n in terms)][:5]
        titles=list(dict.fromkeys(title for values in candidates.values() for title in values))
        pages={}
        for chunk in w.chunks(titles,20):pages.update(w.get_pages(chunk))
        found={}
        for row in batch:
            for title in candidates[row['id']]:
                page=pages.get(title,{});reason=w.match_reason(row,page)
                if reason:found[row['id']]=(page,reason);break
        return found
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(search,b):b for b in w.chunks(missing,8)}
        for i,f in enumerate(as_completed(jobs),1):
            try:matched.update(f.result())
            except Exception as error:errors.append({'stage':'search','ids':[r['id'] for r in jobs[f]],'error':str(error)})
            if i%10==0 or i==len(jobs):w.log(f'百科补充检索 {i}/{len(jobs)}，匹配 {len(matched)}')
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds');new_text=[]
    for row in missing:
        if row['id'] not in matched:continue
        page,reason=matched[row['id']];old=entries[row['id']]
        item=w.article_record(row,page,reason,stamp,old.get('image'));w.save_json(w.DATA/(row['id']+'.json'),item)
        entries[row['id']]=item;new_text.append(row['id'])
    # A page's lead image is used only for a verified, corresponding subject.
    reviewed=[r for r in rows if not entries[r['id']].get('image') and (r['id'] in matched or w.OVERRIDES.get(r['id'],{}).get('reviewedRevisionId'))]
    titles=list(dict.fromkeys(entries[r['id']]['title'] for r in reviewed));gallery={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(photos.article_files,b) for b in w.chunks(titles,30)]
        for f in as_completed(jobs):
            try:gallery.update(f.result())
            except Exception as error:errors.append({'stage':'gallery','error':str(error)})
    ids=list(dict.fromkeys(g['qid'] for g in gallery.values() if g.get('qid')));entity={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(photos.entity_files,b) for b in w.chunks(ids,50)]
        for f in as_completed(jobs):
            try:entity.update(f.result())
            except Exception as error:errors.append({'stage':'wikidata','error':str(error)})
    candidates={}
    for row in reviewed:
        entry=entries[row['id']];g=gallery.get(entry['title'],{});trusted=[x for x in entity.get(g.get('qid'),[]) if x]
        candidates[row['id']]={'trusted':trusted,'all':list(dict.fromkeys([*trusted,*g.get('files',[])]))[:5]}
    names=list(dict.fromkeys(n for c in candidates.values() for n in c['all'] if photos.usable_name(n)));metadata={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(w.image_metadata,b,320) for b in w.chunks(names,30)]
        for f in as_completed(jobs):
            try:metadata.update(f.result())
            except Exception as error:errors.append({'stage':'imageinfo','error':str(error)})
    def fill(row):
        item=candidates[row['id']];entry=entries[row['id']]
        exact=w.normalized(re.split(r'\s*[（(]',entry['title'])[0])==w.normalized(row['name'])
        for name in item['all']:
            page=metadata.get(name.replace('_',' '),{})
            if not page or not photos.usable_name(name):continue
            if not photos.commons_matches(row,page) and not (exact and name in item['trusted']):continue
            photo=w.store_image(name,page)
            if photo and w.photo_allowed(row['id'],photo):
                photo['matchEvidence']='名称及地点核对一致' if photos.commons_matches(row,page) else '对应同名维基数据条目的 P18 配图'
                if photos.attach(row['id'],photo):return {'id':row['id'],'name':row['name'],'title':name}
        return None
    added=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(fill,row):row for row in reviewed}
        for i,f in enumerate(as_completed(jobs),1):
            try:
                result=f.result()
                if result:added.append(result)
            except Exception as error:errors.append({'stage':'download','id':jobs[f]['id'],'error':str(error)})
            if i%50==0 or i==len(jobs):w.log(f'配图复核 {i}/{len(jobs)}，补充 {len(added)}')
    name='wikipedia-update-photos-audit.json' if args.photos_only else 'wikipedia-update-audit.json'
    w.save_json(w.ROOT/name,{'newText':new_text,'newImages':added,'errors':errors})
    w.log(f'本轮完成：百科介绍 {len(new_text)}，图片 {len(added)}，错误 {len(errors)}')


if __name__=='__main__':main()
