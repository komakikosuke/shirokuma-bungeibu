import copy
import unittest
from test_prefecture_atlas import atlas, PREFECTURES


def document(at='2026-11-30T15:50:00Z', status='ok', articles=None):
    return {'generatedAt': at, 'sync': {'status': status}, 'articles': articles or []}


class HistoryTests(unittest.TestCase):
    def test_does_not_record_before_launch(self):
        doc = document('2026-11-27T00:00:00Z')
        atlas.record_history({}, doc, PREFECTURES)
        self.assertEqual(doc['history'], [])

    def test_first_success_has_white_baseline_and_unique_article_counts(self):
        article = {'key': 'n1', 'prefectures': ['13', '26', '13']}
        doc = document(articles=[article, article])
        atlas.record_history({}, doc, PREFECTURES)
        self.assertEqual(len(doc['history']), 2)
        self.assertEqual(len(doc['history'][0]['counts']), 47)
        self.assertTrue(all(n == 0 for n in doc['history'][0]['counts'].values()))
        self.assertEqual(doc['history'][1]['counts']['13'], 1)
        self.assertEqual(doc['history'][1]['counts']['26'], 1)

    def test_partial_collection_preserves_existing_history(self):
        previous = document(); atlas.record_history({}, previous, PREFECTURES)
        original = copy.deepcopy(previous)
        partial = document('2026-11-30T18:50:00Z', 'partial')
        atlas.record_history(previous, partial, PREFECTURES)
        self.assertEqual(partial['history'], previous['history'])
        self.assertEqual(previous, original)

    def test_later_snapshot_can_decrease_and_same_timestamp_is_not_duplicated(self):
        previous = document(articles=[{'key': 'n1', 'prefectures': ['13']}])
        atlas.record_history({}, previous, PREFECTURES)
        later = document('2026-11-30T18:50:00Z')
        atlas.record_history(previous, later, PREFECTURES)
        self.assertEqual(later['history'][-1]['counts']['13'], 0)
        again = document('2026-11-30T18:50:00Z')
        atlas.record_history(later, again, PREFECTURES)
        self.assertEqual(again['history'], later['history'])

    def test_corrupt_history_is_not_silently_overwritten(self):
        with self.assertRaises(ValueError):
            atlas.record_history({'history': [{'at': 'bad', 'counts': {}}]}, document(), PREFECTURES)
