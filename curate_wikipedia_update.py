"""Save manually checked introductions for selected multi-part heritage sites."""
from datetime import datetime, timezone
import json
import fetch_wikipedia as w


CASES={
 'wb-1-99':{'title':'曲阜孔庙、孔林和孔府','revision':91237643,
   'text':'曲阜孔庙和孔府位于山东省曲阜市。孔庙是祭祀孔子的庙宇，孔府是孔子嫡系后裔居住的府第；两者与孔林合称“三孔”。',
   'image':'20230612_Dacheng_Dian,_Qufu_Kongmiao.jpg','subject':'曲阜孔庙大成殿，孔庙建筑的一部分'},
 'wb-2-1':{'title':'林则徐销烟池','revision':91628545,
   'text':'林则徐销烟池与虎门炮台旧址位于广东省东莞市虎门镇。1839年，林则徐在虎门集中销毁收缴的鸦片，史称虎门销烟。销烟池于1957年重建，现位于鸦片战争博物馆馆区内；该文物保护单位还包括虎门炮台旧址。1982年，销烟池与虎门炮台旧址列入第二批全国重点文物保护单位。',
   'image':'Opium_Destruction_Pool.JPG','subject':'林则徐销烟池，文保单位的组成部分'},
 'wb-2-8':{'title':'西柏坡纪念馆','revision':94131936,
   'text':'西柏坡中共中央旧址位于河北省平山县西柏坡，主要包括中共七届二中全会会址、中央军委作战室及多处领导人旧居。1948年至1949年，中共中央和中国人民解放军总部驻在西柏坡，组织指挥了辽沈、淮海、平津三大战役，并召开中共七届二中全会。旧址的部分纪念建筑在1958年迁建复原。',
   'image':'毛澤東舊居 - panoramio.jpg','subject':'西柏坡中共中央旧址中的毛泽东旧居'},
}


def main():
    rows={r['id']:r for r in json.loads((w.ROOT/'dist/data/heritage.json').read_text(encoding='utf-8'))['rows']}
    pages=w.get_pages([c['title'] for c in CASES.values()])
    metadata=w.image_metadata([c['image'] for c in CASES.values()],320)
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds');updated=[]
    for ident,case in CASES.items():
        page=pages.get(case['title'],{})
        if page.get('lastrevid')!=case['revision']:raise ValueError('Source revision changed: '+ident)
        image=w.store_image(case['image'],metadata.get(case['image'].replace('_',' '),{}))
        if not image:raise ValueError('No attributable local image: '+ident)
        image['subject']=case['subject'];image['matchEvidence']='人工复核图片中的文物子项及所在地'
        override=w.OVERRIDES.setdefault(ident,{})
        override.update(title=page['title'],reviewedRevisionId=page['lastrevid'],reviewedReason='人工核对组合文物与百科条目的对应关系',reviewedSourceUrl='https://zh.wikipedia.org/w/index.php?oldid='+str(page['lastrevid']))
        entry=w.article_record(rows[ident],page,override['reviewedReason'],stamp,image)
        entry.update(text=case['text'],shortened=True,textScope='body-excerpt',editorialNotes=['根据对应百科条目整理，明确组合文物及图片所示子项。'])
        w.save_json(w.DATA/(ident+'.json'),entry);updated.append(ident)
    w.OVERRIDES_PATH.write_text(json.dumps(w.OVERRIDES,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    w.save_json(w.ROOT/'wikipedia-curated-update-audit.json',{'updated':updated})
    print('人工复核条目：',len(updated))


if __name__=='__main__':main()
