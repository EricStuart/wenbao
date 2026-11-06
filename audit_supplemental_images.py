"""Remove article-navigation illustrations that do not identify the monument."""
import json
import complete_wikipedia_images as p
import fetch_wikipedia as w


def main():
    p.restore_gallery()
    rows=json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']
    rejected=[];confirmed=0
    for row in rows:
        path=w.DATA/(row['id']+'.json');entry=json.loads(path.read_text(encoding='utf-8'));image=entry.get('image')
        if not image or image.get('matchEvidence')!='对应维基百科条目或 Wikidata 条目的配图':continue
        qid=p.GALLERY.get(entry.get('title'),{}).get('qid')
        claims=p.ENTITIES.get(qid,{}).get('claims',{}).get('P18',[])
        filenames={c.get('mainsnak',{}).get('datavalue',{}).get('value','').replace('_',' ') for c in claims if c.get('rank')!='deprecated'}
        meta={'title':'File:'+image['title'],'imageinfo':[{'extmetadata':{'ImageDescription':{'value':image.get('caption','')}}}]}
        if image['title'].replace('_',' ') in filenames and p.usable_name(image['title']):
            image['matchEvidence']='对应 Wikidata 条目的 P18 配图';confirmed+=1
        elif p.usable_name(image['title']) and p.commons_matches(row,meta):
            image['matchEvidence']='对应百科配图的名称与所在地一致';confirmed+=1
        else:
            rejected.append({'id':row['id'],'name':row['name'],'image':image,'reason':'仅出现于百科页面图片列表，缺少文物本体匹配依据'})
            entry['image']=None
        w.save_json(path,entry)
    w.save_json(w.ROOT/'wikipedia-rejected-images.json',{'confirmed':confirmed,'rejected':rejected})
    w.log(json.dumps({'confirmed':confirmed,'rejected':len(rejected)}))


if __name__=='__main__':main()
