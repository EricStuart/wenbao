"""Expand short leads with readable body paragraphs from their cited revisions."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import argparse
import json
import re
import fetch_wikipedia as w
import mwparserfromhell
from opencc import OpenCC

CONVERTER=OpenCC('t2s')
REFERENCE=r'\n={2,}\s*(?:参考[^\n=]*|參考[^\n=]*|参见|參見|注释|註釋|外部[^\n=]*|延伸阅读|延伸閱讀|资料来源|資料來源)\s*={2,}'


def body_paragraphs(raw):
    parts=re.split(r'\n(?=={2,}[^=])',raw,maxsplit=1)
    if len(parts)<2:return ''
    raw=re.split(REFERENCE,'\n'+parts[1],maxsplit=1)[0]
    code=mwparserfromhell.parse(raw)
    sections=code.get_sections(levels=[2],include_lead=False,include_headings=True)
    if sections:
        selected=[]
        for section in sections:
            headings=section.filter_headings()
            title=CONVERTER.convert(str(headings[0].title).strip()) if headings else ''
            if re.match(r'^(?:内部交通|交通|保护范围|建设控制|图片|图集|参观|游览|门票|开放时间)',title):continue
            selected.append(str(section))
        code=mwparserfromhell.parse('\n\n'.join(selected))
    def remove(node):
        try:code.remove(node)
        except ValueError:pass
    for tag in code.filter_tags():
        if str(tag.tag).lower() in ('ref','references','gallery','imagemap','table','timeline','score','syntaxhighlight','math'):
            remove(tag)
    for node in code.filter_comments()+code.filter_headings():remove(node)
    for link in code.filter_wikilinks():
        if re.match(r'^(?:File|Image|Category|文件|档案|檔案|图像|圖像|分类|分類|[a-z-]{2,10}):',str(link.title),re.I):remove(link)
    for template in code.filter_templates():
        name=str(template.name).strip().lower()
        params=[p.value for p in template.params if str(p.name).strip().isdigit()]
        replacement=None
        if name in ('lang','nowrap','nobr','small','big') and params:replacement=params[-1]
        if name in ('ilh','ill','link-en','link-ja','僻字','生僻字','unicode','ruby') and params:replacement=params[0]
        if name in ('convert','cvt') and len(params)>=2:replacement=str(params[0])+' '+str(params[1])
        if replacement is not None:
            try:code.replace(template,str(replacement))
            except ValueError:pass
    text=CONVERTER.convert(code.strip_code(normalize=True,collapse=True))
    text=text.replace('清朝嘉靖','明朝嘉靖')
    text=re.sub(r'(?m)^\s*[*#:;]+\s*','',text)
    text=re.sub(r'\n{3,}','\n\n',text).strip()
    # Unexpanded conversion rules or markup need manual review, not publication.
    if any(mark in text for mark in ('{{','}}','[[','{|','-{','<ref')):return ''
    return text


def revisions(ids):
    result=w.api({'action':'query','revids':'|'.join(map(str,ids)),'prop':'revisions','rvprop':'ids|content','rvslots':'main'})
    output={}
    for page in result.get('query',{}).get('pages',[]):
        for revision in page.get('revisions',[]):
            raw=revision.get('slots',{}).get('main',{}).get('content','')
            if raw:output[revision['revid']]=raw
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--minimum',type=int,default=0,help='Minimum current introduction length')
    parser.add_argument('--maximum',type=int,default=80,help='Exclusive maximum introduction length')
    parser.add_argument('--exact-title',action='store_true',help='Only enrich entries whose article and site names match')
    parser.add_argument('--audit',default='wikipedia-text-audit.json',help='Report filename in the project root')
    args=parser.parse_args()
    entries=[json.loads(p.read_text(encoding='utf-8')) for p in w.DATA.glob('wb-*.json')]
    candidates=[e for e in entries if e.get('status')=='ready' and args.minimum<=len(e.get('text',''))<args.maximum and e.get('textScope')!='body-excerpt']
    if args.exact_title:
        candidates=[e for e in candidates if w.normalized(CONVERTER.convert(e['name']))==w.normalized(CONVERTER.convert(e['title']))]
    ids=list(dict.fromkeys(e['revisionId'] for e in candidates))
    raw={};errors=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks={pool.submit(revisions,b):b for b in w.chunks(ids,50)}
        for i,f in enumerate(as_completed(tasks),1):
            try:raw.update(f.result())
            except Exception as error:errors.append({'stage':'revisions','error':str(error)})
            w.log(f'Article body batches: {i}/{len(tasks)}')
    expanded={}
    for entry in candidates:
        body=body_paragraphs(raw.get(entry['revisionId'],''))
        if len(body)<40:continue
        text=w.excerpt(entry['text']+'\n\n'+body,1200)[0]
        if len(text)<len(entry['text'])+40:continue
        expanded[entry['id']]={'text':text,'revisionId':entry['revisionId']}
        if not args.prepare_only:
            path=w.DATA/(entry['id']+'.json')
            current=json.loads(path.read_text(encoding='utf-8'))
            if current.get('revisionId')!=entry['revisionId']:continue
            current.update(text=text,shortened=True,textScope='body-excerpt',retrievedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'))
            w.save_json(path,current)
    w.save_json(w.CACHE/'enriched-text.json',expanded)
    report={'checked':len(candidates),'expanded':len(expanded),'prepareOnly':args.prepare_only,'errors':errors}
    w.save_json(w.ROOT/args.audit,report)
    w.log(json.dumps({k:v for k,v in report.items() if k!='errors'}))


if __name__=='__main__':main()
