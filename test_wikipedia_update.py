import unittest
from apply_wikipedia_expansions import conflicts


class ExpansionReviewTests(unittest.TestCase):
    def test_correct_batch_and_year_is_allowed(self):
        self.assertFalse(conflicts('wb-1-132','1961年列为第一批全国重点文物保护单位。'))

    def test_mismatched_batch_or_year_is_flagged(self):
        self.assertTrue(conflicts('wb-1-132','1968年列为第一批全国重点文物保护单位。'))
        self.assertTrue(conflicts('wb-1-132','2001年列为第五批全国重点文物保护单位。'))

    def test_unclosed_quote_and_external_link_are_flagged(self):
        self.assertTrue(conflicts('wb-1-132','提到“尚未结束的引文。'))
        self.assertTrue(conflicts('wb-1-132','详情见 https://example.org。'))


if __name__=='__main__':
    unittest.main()
