import unittest
from unittest.mock import patch
from fetch_wikipedia import article_names, distance_km, excerpt, match_reason, plain


class WikipediaMatchTests(unittest.TestCase):
    def setUp(self):
        self.row = {'name': '龙泉寺', 'province': '北京', 'city': '北京市', 'county': '海淀区', 'coordinates': [116.08, 40.06]}
        self.page = {'title': '龙泉寺 (北京)', 'extract': '龙泉寺位于北京市海淀区。', 'coordinates': [{'lon': 116.08, 'lat': 40.06}]}

    def test_matching_name_and_location(self):
        self.assertIsNotNone(match_reason(self.row, self.page))

    def test_far_away_homonym_rejected(self):
        self.page['coordinates'] = [{'lon': 121.5, 'lat': 31.2}]
        self.assertIsNone(match_reason(self.row, self.page))

    def test_sibling_county_conflict_rejected_even_when_nearby(self):
        self.page['extract'] = '龙泉寺位于北京市门头沟区。'
        self.assertIsNone(match_reason(self.row, self.page))

    def test_name_and_province_alone_not_enough(self):
        self.page.pop('coordinates')
        self.page['extract'] = '龙泉寺位于北京。'
        self.row.update(province='福建', city='福州市', county='鼓楼区')
        self.page['extract'] = '龙泉寺是福建的一座古建筑。'
        self.assertIsNone(match_reason(self.row, self.page))

    def test_nearby_similarly_named_temple_with_different_batch_rejected(self):
        self.row.update(name='玉皇庙',batch=3)
        self.page.update(title='北义城玉皇庙',extract='北义城玉皇庙位于山西省，2006年为第六批全国重点文物保护单位。')
        self.assertIsNone(match_reason(self.row,self.page))

    def test_disambiguation_and_catalogue_rejected(self):
        self.page['pageprops'] = {'disambiguation': ''}
        self.assertIsNone(match_reason(self.row, self.page))
        self.page.pop('pageprops')
        self.page['title'] = '北京市全国重点文物保护单位列表'
        self.assertIsNone(match_reason(self.row, self.page))

    def test_reviewed_alias_is_bound_to_title_and_revision(self):
        self.row['id']='reviewed-alias'
        self.page.update(title='龙泉古寺',extract='古寺已有独立条目。',lastrevid=101)
        review={'title':'龙泉古寺','reviewedRevisionId':101,'reviewedReason':'复核同一处文物'}
        with patch.dict('fetch_wikipedia.OVERRIDES',{'reviewed-alias':review}):
            self.assertEqual(match_reason(self.row,self.page),'复核同一处文物')
            self.page['lastrevid']=102
            self.page.pop('coordinates')
            self.assertIsNone(match_reason(self.row,self.page))

    def test_unrelated_article_with_nearby_coordinates_rejected(self):
        self.page.update(title='颐和园', extract='颐和园位于北京市海淀区。')
        self.assertIsNone(match_reason(self.row, self.page))

    def test_attribution_html_is_plain_text(self):
        self.assertEqual(plain('<a href="/wiki/User:A">A &amp; B</a>'), 'A & B')

    def test_catalogue_alias_can_match_verified_location(self):
        self.row['name'] = '佛宫寺释迦塔（应县木塔）'
        self.page.update(title='应县木塔', extract='应县木塔是佛宫寺释迦塔。')
        self.assertIsNotNone(match_reason(self.row, self.page))

    def test_great_wall_section_names_and_inclusion_notes(self):
        self.assertIn('八达岭', article_names({'name':'万里长城－八达岭'}))
        self.assertNotIn('包括龙虎塔、九顶塔', article_names({'name':'千佛崖造像（包括龙虎塔、九顶塔）'}))

    def test_excerpt_ends_at_sentence_and_retains_paragraphs(self):
        text = '第一段介绍。\n\n第二段详细介绍。最后一句。'
        shortened, changed = excerpt(text, 18)
        self.assertTrue(changed)
        self.assertTrue(shortened.endswith('。'))
        self.assertIn('\n\n', shortened)
        self.assertLessEqual(len(shortened), 18)


if __name__ == '__main__':
    unittest.main()
