"""Apply individually reviewed aliases without relaxing automatic matching."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import fetch_wikipedia as w
from complete_wikipedia_images import usable_name


def main():
    rows=json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    selected=[row for row in rows if w.OVERRIDES.get(row['id'],{}).get('reviewedRevisionId')]
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    errors=[];updated=[]
    pages={}
    for batch in w.chunks([w.OVERRIDES[row['id']]['title'] for row in selected],20):pages.update(w.get_pages(batch))
    names=[]
    for row in selected:
        old=json.loads((w.DATA/(row['id']+'.json')).read_text(encoding='utf-8'))
        name=pages.get(w.OVERRIDES[row['id']]['title'],{}).get('pageimage')
        if not old.get('image') and name and usable_name(name):names.append(name)
    metadata={}
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks=[pool.submit(w.image_metadata,batch,320) for batch in w.chunks(list(dict.fromkeys(names)),30)]
        for i,future in enumerate(as_completed(tasks),1):
            try:metadata.update(future.result())
            except Exception as error:errors.append({'stage':'metadata','error':str(error)})
            w.log(f'Reviewed photo metadata: {i}/{len(tasks)}')
    def recover(row):
        override=w.OVERRIDES[row['id']]
        page=pages.get(override['title'],{})
        reason=w.match_reason(row,page)
        if not reason:return None
        path=w.DATA/(row['id']+'.json')
        old=json.loads(path.read_text(encoding='utf-8'))
        photo=old.get('image')
        name=page.get('pageimage')
        if not photo and name and usable_name(name):
            try:
                meta=metadata.get(name.replace('_',' '),{})
                description=w.plain(name+' '+(meta.get('imageinfo') or [{}])[0].get('extmetadata',{}).get('ImageDescription',{}).get('value',''))
                subject=override.get('imageSubject')
                if not subject or subject in description:
                    photo=w.store_image(name,meta)
                if photo:
                    photo['matchEvidence']='已复核文物对应百科条目的主图'
                    if page['title']!=row['name']:photo['subject']=page['title']
            except Exception as error:errors.append({'id':row['id'],'error':str(error)})
        entry=w.article_record(row,page,reason,stamp,photo)
        w.save_json(path,entry)
        return {'id':row['id'],'name':row['name'],'title':page['title'],'withPhoto':bool(entry.get('image'))}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(recover,row) for row in selected]
        for i,future in enumerate(as_completed(futures),1):
            try:
                result=future.result()
                if result:updated.append(result)
            except Exception as error:errors.append({'error':str(error)})
            if i%25==0 or i==len(futures):w.log(f'Reviewed aliases: {i}/{len(futures)}')
    w.save_json(w.ROOT/'wikipedia-redirect-review.json',{'updated':updated,'errors':errors})


if __name__=='__main__':main()
