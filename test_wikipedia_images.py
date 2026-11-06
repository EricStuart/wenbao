import unittest
from complete_wikipedia_images import commons_matches, usable_name


class PhotoMatchTests(unittest.TestCase):
    def setUp(self):
        self.row={'name':'龙泉寺','province':'河北','city':'石家庄市','county':'鹿泉区','region':'Hebei'}

    def photo(self,description):
        return {'title':'File:龙泉寺.jpg','imageinfo':[{'extmetadata':{'ImageDescription':{'value':description}}}]}

    def test_same_province_is_not_enough_when_city_is_known(self):
        self.assertFalse(commons_matches(self.row,self.photo('河北省邢台市龙泉寺')))

    def test_named_monument_and_local_place_can_match(self):
        self.assertTrue(commons_matches(self.row,self.photo('河北石家庄鹿泉龙泉寺')))

    def test_same_city_different_county_is_rejected(self):
        self.assertFalse(commons_matches(self.row,self.photo('河北省石家庄市赞皇县龙泉寺')))

    def test_navigation_symbols_and_maps_are_rejected(self):
        self.assertFalse(usable_name('太阳神鸟金饰 Golden Sun Bird.png'))
        self.assertFalse(usable_name('Shandong prfc map.png'))


if __name__=='__main__':unittest.main()
