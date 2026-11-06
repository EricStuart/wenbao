"""Use subject-specific Commons categories explicitly linked by Wikidata."""
import json
import re
import urllib.parse
import complete_wikipedia_images as p
import fetch_wikipedia as w


def main():
    p.restore_gallery()
    rows=json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    candidates=[];errors=[];added=0
    for row in rows:
        entry=json.loads((w.DATA/(row['id']+'.json')).read_text(encoding='utf-8'))
        if entry.get('image') or entry.get('status')!='ready':continue
        # A regional subset must not inherit photographs from a broader subject.
        names=[row['name'],*(row.get('aliases') or []),re.split(r'[（(]',row['name'])[0],*re.findall(r'[（(]([^（）()]+)[）)]',row['name'])]
        if w.OVERRIDES.get(row['id'],{}).get('title'):names.append(w.OVERRIDES[row['id']]['title'])
        if w.normalized(entry['title']) not in {w.normalized(name) for name in names}:continue
        qid=p.GALLERY.get(entry['title'],{}).get('qid')
        claims=p.ENTITIES.get(qid,{}).get('claims',{}).get('P373',[])
        rejected=w.OVERRIDES.get(row['id'],{}).get('rejectedCategories',[])
        categories=[c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in claims if c.get('rank')!='deprecated']
        categories=[category for category in categories if category and category not in rejected and not re.search(r'\bculture\b',category,re.I)]
        if categories:candidates.append((row,[category for category in categories if category]))
    for i,(row,categories) in enumerate(candidates,1):
        try:
            for category in categories:
                result=w.api({'action':'query','generator':'categorymembers','gcmtitle':'Category:'+category,
                              'gcmnamespace':6,'gcmlimit':20,'prop':'imageinfo','iiprop':'url|extmetadata|mime|size|thumbmime',
                              'iiurlwidth':320,'iiextmetadatalanguage':'zh',
                              'iiextmetadatafilter':'Artist|Credit|LicenseShortName|LicenseUrl|ImageDescription'},w.COMMONS)
                saved=False
                for page in result.get('query',{}).get('pages',[]):
                    name=page['title'].removeprefix('File:')
                    if not p.usable_name(name) or re.search(r'portrait|painting|map\.|plan\.|sketch|poster|signature|肖像|画像|地图|示意|平面图',name,re.I):continue
                    photo=w.store_image(name,page)
                    if photo and w.photo_allowed(row['id'],photo):
                        photo['matchEvidence']='对应 Wikidata P373 专属相册：'+category
                        photo['categorySourceUrl']='https://commons.wikimedia.org/wiki/Category:'+urllib.parse.quote(category.replace(' ','_'))
                        if p.attach(row['id'],photo):added+=1
                        saved=True;break
                if saved:break
        except Exception as error:errors.append({'id':row['id'],'error':str(error)})
        if i%10==0 or i==len(candidates):w.log(f'Subject photo categories: {i}/{len(candidates)}, {added} added')
    w.save_json(w.ROOT/'wikipedia-categories-audit.json',{'checked':len(candidates),'added':added,'errors':errors})


if __name__=='__main__':main()
