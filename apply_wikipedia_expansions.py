"""Apply prepared same-revision text excerpts, excluding visible catalogue conflicts."""
import json
import re
import fetch_wikipedia as w

YEARS=[1961,1982,1988,1996,2001,2006,2013,2019]


def conflicts(ident,text):
    batch=int(ident.split('-')[1]);issues=[]
    for sentence in re.split(r'[。；\n]',text):
        if '全国重点文物保护单位' not in sentence:continue
        for name in re.findall(r'第([一二三四五六七八])批全国重点文物保护单位',sentence):
            number='一二三四五六七八'.index(name)+1
            if number!=batch:issues.append('conflicting national batch')
            for year in re.findall(r'(19\d{2}|20\d{2})年.{0,12}第'+name+'批全国重点文物保护单位',sentence):
                if int(year)!=YEARS[number-1]:issues.append('conflicting announcement year')
    if any(mark in text for mark in ('{{','}}','[[','-{','<ref','参考文献','维基共享资源')):issues.append('unrendered markup')
    if re.search(r'https?://|www\.',text):issues.append('embedded external link')
    for opening,closing in [('“','”'),('「','」'),('（','）'),('《','》')]:
        if text.count(opening)!=text.count(closing):issues.append('unbalanced punctuation')
    return sorted(set(issues))


def main():
    prepared=json.loads((w.CACHE/'enriched-text.json').read_text(encoding='utf-8'))
    applied=[];skipped=[]
    for ident,version in prepared.items():
        path=w.DATA/(ident+'.json');entry=json.loads(path.read_text(encoding='utf-8'))
        if entry.get('revisionId')!=version['revisionId'] or not version['text'].startswith(entry.get('text','')):
            skipped.append({'id':ident,'reason':['source or introduction changed']});continue
        issues=conflicts(ident,version['text'])
        if issues:skipped.append({'id':ident,'reason':issues});continue
        entry.update(text=version['text'],shortened=True,textScope='body-excerpt')
        w.save_json(path,entry);applied.append(ident)
    w.save_json(w.ROOT/'wikipedia-update-text-audit.json',{'applied':applied,'skipped':skipped})
    print('正文扩充',len(applied),'待复核跳过',len(skipped))


if __name__=='__main__':main()
