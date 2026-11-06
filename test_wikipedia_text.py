import unittest
from enrich_wikipedia_text import body_paragraphs


class BodyExcerptTests(unittest.TestCase):
    def test_body_preserves_prose_and_omits_images_references_and_tables(self):
        raw='寺庙简介。\n== 历史 ==\n始建於唐代，称{{lang|zh|古寺}}。<ref>文献引用</ref>\n[[File:Temple.jpg|thumb|图片说明]]\n== 建筑 ==\n大殿面阔三间。\n{| class="wikitable"\n| 数据表\n|}\n== 参考文献 ==\n不应混入正文的书目。'
        text=body_paragraphs(raw)
        self.assertIn('始建于唐代，称古寺。',text)
        self.assertIn('大殿面阔三间。',text)
        for unwanted in ('文献引用','图片说明','数据表','书目','File:','{{'):
            self.assertNotIn(unwanted,text)

    def test_unrendered_language_conversion_is_not_published(self):
        self.assertEqual(body_paragraphs('简介。\n== 历史 ==\n仍含-{zh-cn:古寺;zh-tw:古廟;}-规则。'),'')

    def test_historical_prose_keeps_rare_characters_and_omits_visitor_routes(self):
        text=body_paragraphs('简介。\n== 历史 ==\n明代以{{僻字|夯}}土修筑。\n== 内部交通 ==\n缆车七百米。\n== 保护范围 ==\n围墙以北二十米。')
        self.assertIn('明代以夯土修筑。',text)
        self.assertNotIn('缆车',text)
        self.assertNotIn('围墙以北',text)


if __name__=='__main__':unittest.main()
