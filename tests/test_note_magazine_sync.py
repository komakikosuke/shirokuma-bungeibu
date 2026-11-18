"""Offline checks for Wednesday release gating and resumable magazine additions."""
import copy
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'note_magazine_sync.py'
spec = importlib.util.spec_from_file_location('note_magazine_sync', SCRIPT)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

RELEASE = datetime.fromisoformat('2026-11-18T21:00:00+09:00')
NOW = datetime.fromisoformat('2026-11-18T21:01:00+09:00')


def work(index=1):
    return {'key': f'n{index}', 'handle': f'writer{index}',
            'url': f'https://note.com/writer{index}/n/n{index}',
            'publishedAt': '2026-11-17T20:00:00+09:00',
            'sourceType': 'extracted', 'charCount': 20}


def feed(count=1):
    return {'version': 1, 'pageStatus': 'ready', 'sourceHashtag': '20字小説',
            'eventDate': '2026-11-17',
            'sourceWindow': {'since': '2026-11-17T19:00:00+09:00',
                             'until': '2026-11-17T21:00:00+09:00'},
            'sourceSummary': {'extracted': count}, 'works': [work(i) for i in range(1, count + 1)]}


def announcement():
    return {'key': 'nnotice', 'user': {'urlname': sync.AUTHOR},
            'name': '20字小説のエンドロールを公開しました！', 'status': 'published',
            'publish_at': '2026-11-18T21:00:00+09:00', 'price': 0,
            'body': f'<p>公開しました。</p><a href="{sync.ENDROLL_PAGE}">エンドロール</a>'}


class PublicData:
    def __init__(self, document=None, article=None, listed=True):
        self.document = document or feed()
        self.article = article or announcement()
        self.listed = listed
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url == sync.ENDROLL_FEED:
            return copy.deepcopy(self.document)
        if '/creators/' in url:
            rows = [{'key': self.article['key'], 'status': 'published',
                     'publishAt': self.article['publish_at']}] if self.listed else []
            return {'data': {'contents': rows, 'isLastPage': True}}
        if '/api/v3/notes/' in url:
            return {'data': copy.deepcopy(self.article)}
        if '/api/v1/magazines/' in url:
            return {'data': {'key': 'm47893b257d5a', 'name': sync.ENDROLL_TARGET,
                             'status': 'public', 'magazine_url': sync.ENDROLL_MAGAZINE,
                             'user': {'urlname': sync.AUTHOR}}}
        raise AssertionError('Unexpected public request: ' + url)


class ReleaseTests(unittest.TestCase):
    def test_before_21_does_not_even_look_up_announcement(self):
        public = PublicData()
        result = sync.load_endroll_feed(datetime.fromisoformat('2026-11-18T20:59:59+09:00'), public)
        self.assertEqual(result['status'], 'waiting_for_wednesday_21')
        self.assertEqual(result['works'], {})
        self.assertEqual(public.calls, [sync.ENDROLL_FEED])

    def test_21_without_public_article_still_waits(self):
        result = sync.load_endroll_feed(NOW, PublicData(listed=False))
        self.assertEqual(result['status'], 'waiting_for_public_announcement')
        self.assertEqual(result['works'], {})

    def test_public_announcement_releases_all_113_works(self):
        result = sync.load_endroll_feed(NOW, PublicData(feed(113)))
        self.assertEqual(result['status'], 'released')
        self.assertEqual(len(result['works']), 113)
        self.assertEqual(result['announcement']['url'], 'https://note.com/komaki_kousuke/n/nnotice')
        self.assertEqual(result['magazineUrl'], sync.ENDROLL_MAGAZINE)

    def test_jst_gate_is_correct_when_caller_uses_utc(self):
        result = sync.load_endroll_feed(datetime.fromisoformat('2026-11-18T12:00:00+00:00'), PublicData())
        self.assertEqual(result['status'], 'released')

    def test_announcement_published_after_21_is_supported(self):
        article = announcement()
        article['publish_at'] = '2026-11-18T21:00:30+09:00'
        self.assertEqual(sync.load_endroll_feed(NOW, PublicData(article=article))['status'], 'released')

    def test_rejects_unpublished_unrelated_or_wrong_week_articles(self):
        for changes in [
                {'status': 'draft'}, {'is_reserved': True}, {'is_draft': True},
                {'is_published': False}, {'is_limited': True}, {'price': 500},
                {'user': {'urlname': 'someone_else'}}, {'key': 'nother'},
                {'publish_at': '2026-11-18T20:59:59+09:00'},
                {'publish_at': '2026-11-18T21:02:00+09:00'},
                {'publish_at': '2026-11-11T21:00:00+09:00'},
                {'body': '<p>エンドロールを公開しました</p>'},
                {'body': '<a href="https://example.com/twenty-credits/">エンドロール</a>'},
                {'body': '<a href="https://komakikosuke.github.io/shirokuma-bungeibu/twenty-credits-other/">見る</a>'}]:
            with self.subTest(changes=changes):
                article = dict(announcement(), **changes)
                self.assertFalse(sync.announcement_matches(article, 'nnotice', RELEASE, NOW))

    def test_next_day_article_does_not_unlock_previous_wednesday(self):
        article = announcement()
        article['publish_at'] = '2026-11-19T21:00:00+09:00'
        later = datetime.fromisoformat('2026-11-19T21:01:00+09:00')
        self.assertFalse(sync.announcement_matches(article, 'nnotice', RELEASE, later))

    def test_exact_endroll_link_in_embedded_card_and_query_is_accepted(self):
        article = announcement()
        article['body'] = f'<div data-src="{sync.ENDROLL_PAGE}?from=note&amp;a=b#watch"></div>'
        self.assertTrue(sync.announcement_matches(article, 'nnotice', RELEASE, NOW))

    def test_new_week_cannot_reuse_last_weeks_announcement(self):
        data = feed()
        data['eventDate'] = '2026-11-24'
        data['sourceWindow'] = {k: v.replace('2026-11-17', '2026-11-24')
                                for k, v in data['sourceWindow'].items()}
        data['works'][0]['publishedAt'] = '2026-11-24T20:00:00+09:00'
        result = sync.load_endroll_feed(datetime.fromisoformat('2026-11-25T21:01:00+09:00'), PublicData(data))
        self.assertEqual(result['status'], 'waiting_for_public_announcement')

    def test_stale_or_future_week_does_not_open_magazine(self):
        for at, status in [('2026-11-17T21:00:00+09:00', 'waiting_for_wednesday_21'),
                           ('2026-11-25T21:00:00+09:00', 'stale_endroll')]:
            public = PublicData()
            self.assertEqual(sync.load_endroll_feed(datetime.fromisoformat(at), public)['status'], status)
            self.assertEqual(public.calls, [sync.ENDROLL_FEED])

    def test_magazine_identity_must_match(self):
        public = PublicData()
        def wrong_magazine(url):
            data = public(url)
            if '/api/v1/magazines/' in url:
                data['data']['magazine_url'] = sync.MAGAZINE
            return data
        with self.assertRaisesRegex(RuntimeError, 'identity'):
            sync.load_endroll_feed(NOW, wrong_magazine)

    def test_invalid_feed_is_never_partially_added(self):
        variants = []
        for changes in [{'pageStatus': 'private'}, {'sourceHashtag': 'シロクマ文芸部'},
                        {'eventDate': '2026-11-18'}, {'sourceWindow': {}},
                        {'sourceSummary': {'extracted': 2}}, {'works': []}]:
            variants.append(dict(feed(), **changes))
        for changes in [{'sourceType': 'demo'}, {'charCount': 18}, {'charCount': True},
                        {'url': 'https://note.com/wrong/n/n1'},
                        {'publishedAt': '2026-11-17T21:00:00+09:00'}]:
            data = feed()
            data['works'][0].update(changes)
            variants.append(data)
        duplicate = feed()
        duplicate['works'] *= 2
        variants.append(duplicate)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(RuntimeError):
                sync.validate_endroll(data)


class StateAndScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name, value in [('DATA_DIR', root), ('LOG_FILE', root / 'sync.log'),
                            ('STATE_FILE', root / 'state.json'),
                            ('ROOM_STATE_FILE', root / 'room-state.json'),
                            ('SAFARI_GUARD_FILE', root / 'safari-guard.json'),
                            ('ENDROLL_STATE_FILE', root / 'endroll-state.json')]:
            patched = patch.object(sync, name, value)
            patched.start()
            self.addCleanup(patched.stop)
        self.log = patch.object(sync, 'log').start()
        self.addCleanup(patch.stopall)

    @staticmethod
    def safari(operation, *args):
        if operation == 'open':return '42'
        return 'ok'

    def test_first_endroll_run_queues_all_works_and_old_channels_still_cap_at_five(self):
        works = {row['url']: row for row in feed(113)['works']}
        channel = sync._prepare_channel('20字小説', works, sync.ENDROLL_STATE_FILE,
                                        sync.ENDROLL_TARGET, False,
                                        lambda w: w['url'], max_per_run=None)
        self.assertEqual(len(channel['pending']), 113)
        room = sync._prepare_channel('部室', works, sync.DATA_DIR / 'room-state.json',
                                     sync.ROOM_TARGET, False, lambda w: w['url'])
        self.assertEqual(len(room['pending']), 5)
        featured = sync._prepare_channel('注目記事', works, sync.DATA_DIR / 'state.json',
                                         sync.TARGET, True, lambda w: w['url'])
        self.assertEqual(featured['pending'], [])

    def test_waiting_does_not_create_checkpoint_or_start_safari(self):
        waiting = {'status': 'waiting_for_public_announcement', 'eventDate': '2026-11-17',
                   'workCount': 113, 'works': {}}
        with patch.object(sync, 'load_endroll_feed', return_value=waiting), \
                patch.object(sync.sys, 'platform', 'darwin'), patch.object(sync, 'applescript') as safari:
            sync.main(endroll_only=True)
        safari.assert_not_called()
        self.assertFalse(sync.ENDROLL_STATE_FILE.exists())

    def test_failed_work_is_retried_but_confirmed_work_is_not_added_again(self):
        release = sync.load_endroll_feed(NOW, PublicData(feed(3)))
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=self.safari), \
                patch.object(sync.time, 'sleep'), \
                patch.object(sync, 'process', side_effect=['added', RuntimeError('not confirmed')]) as process:
            with self.assertRaisesRegex(RuntimeError, 'not confirmed'):
                sync.main(endroll_only=True)
            self.assertEqual(process.call_count, 2)
        state = sync._load_state(sync.ENDROLL_STATE_FILE)
        self.assertEqual(state['added'], [work(1)['url']])
        self.assertEqual(state['announcement']['url'], release['announcement']['url'])
        with patch.object(sync.sys, 'platform', 'darwin'), patch.object(sync, 'applescript') as safari:
            sync.main(endroll_only=True)
            safari.assert_not_called()
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=self.safari), \
                patch.object(sync.time, 'sleep'), patch.object(sync, 'process', return_value='already') as process:
            sync.main(endroll_only=True,resume_safari=True)
            self.assertEqual([call.args[1]['url'] for call in process.call_args_list],
                             [work(2)['url'], work(3)['url']])
            process.reset_mock()
            sync.main(endroll_only=True)
            process.assert_not_called()

    def test_failure_during_window_creation_cannot_spawn_repeated_windows(self):
        release = sync.load_endroll_feed(NOW, PublicData())
        opened = []
        def safari(operation, *args):
            if operation == 'open':
                opened.append(operation)
                raise RuntimeError('Could not get new window ID')
            return 'ok'
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), patch.object(sync, 'applescript', side_effect=safari):
            with self.assertRaisesRegex(RuntimeError, 'window ID'):
                sync.main(endroll_only=True)
            for _ in range(34):
                sync.main(endroll_only=True)
        self.assertEqual(opened, ['open'])
        guard = json.loads(sync.SAFARI_GUARD_FILE.read_text())
        self.assertEqual(guard['stage'], 'open')
        self.assertIn('window ID', guard['error'])
        self.assertEqual(sync._load_state(sync.ENDROLL_STATE_FILE)['added'], [])

    def test_permission_failure_does_not_create_a_window(self):
        release = sync.load_endroll_feed(NOW, PublicData())
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=RuntimeError('JavaScript from Apple Events is disabled')) as safari:
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                sync.main(endroll_only=True)
            sync.main(endroll_only=True)
        self.assertEqual([c.args for c in safari.call_args_list], [('preflight',)])

    def test_cleanup_failure_saves_confirmation_and_stops_future_windows(self):
        release = sync.load_endroll_feed(NOW, PublicData())
        def safari(operation, *args):
            if operation == 'close':raise RuntimeError('Could not close working window')
            return self.safari(operation,*args)
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=safari) as browser, \
                patch.object(sync.time, 'sleep'), patch.object(sync, 'process', return_value='added'):
            with self.assertRaisesRegex(RuntimeError, 'Could not close'):
                sync.main(endroll_only=True)
            self.assertEqual(sync._load_state(sync.ENDROLL_STATE_FILE)['added'], [work(1)['url']])
            browser.reset_mock()
            sync.main(endroll_only=True)
            browser.assert_not_called()
        self.assertEqual(json.loads(sync.SAFARI_GUARD_FILE.read_text())['stage'], 'close')

    def test_interrupted_run_leaves_guard_and_does_not_mark_unconfirmed_work(self):
        release = sync.load_endroll_feed(NOW, PublicData())
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=self.safari), \
                patch.object(sync, 'process', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):sync.main(endroll_only=True)
        self.assertTrue(sync.SAFARI_GUARD_FILE.exists())
        self.assertEqual(sync._load_state(sync.ENDROLL_STATE_FILE)['added'], [])

    def test_manual_one_work_check_does_not_process_remaining_works(self):
        release = sync.load_endroll_feed(NOW, PublicData(feed(113)))
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=self.safari), \
                patch.object(sync.time, 'sleep'), patch.object(sync, 'process', return_value='added') as process:
            sync.main(endroll_only=True,max_works=1)
        self.assertEqual(process.call_count,1)
        self.assertEqual(len(sync._load_state(sync.ENDROLL_STATE_FILE)['added']),1)
        self.assertFalse(sync.SAFARI_GUARD_FILE.exists())

    def test_unconfirmed_return_never_counts_as_added(self):
        release = sync.load_endroll_feed(NOW, PublicData())
        with patch.object(sync, 'load_endroll_feed', return_value=release), \
                patch.object(sync.sys, 'platform', 'darwin'), \
                patch.object(sync, 'applescript', side_effect=self.safari), \
                patch.object(sync, 'process', return_value='clicked'):
            with self.assertRaisesRegex(RuntimeError,'Unconfirmed'):sync.main(endroll_only=True)
        self.assertEqual(sync._load_state(sync.ENDROLL_STATE_FILE)['added'],[])
        self.assertTrue(sync.SAFARI_GUARD_FILE.exists())

    def test_diagnosis_prints_evidence_without_operating_safari(self):
        sync.LOG_FILE.write_text('Safari open: original failure\n',encoding='utf-8')
        sync.safari_guard('open',RuntimeError('original failure'))
        with patch.object(sync,'load_endroll_feed',return_value={'status':'released','works':{}}), \
                patch.object(sync,'applescript') as safari, patch('builtins.print') as output:
            sync.diagnose_endroll()
        safari.assert_not_called()
        self.assertTrue(any('original failure' in str(c) for c in output.call_args_list))
        self.assertTrue(sync.SAFARI_GUARD_FILE.exists())

    def test_endroll_failure_does_not_block_existing_channels(self):
        with patch.object(sync, 'load_endroll_feed', side_effect=RuntimeError('offline')), \
                patch.object(sync, 'load_room_feed', return_value={}) as room, \
                patch.object(sync, 'load_feed', return_value={}) as featured:
            channels, errors = sync.prepare_channels()
        self.assertEqual([c['label'] for c in channels], ['部室', '注目記事'])
        self.assertEqual(len(errors), 1)
        room.assert_called_once()
        featured.assert_called_once()

    def test_endroll_only_does_not_load_old_channels(self):
        waiting = {'status': 'waiting_for_wednesday_21', 'eventDate': '2026-11-17', 'workCount': 113}
        with patch.object(sync, 'load_endroll_feed', return_value=waiting), \
                patch.object(sync, 'load_room_feed') as room, patch.object(sync, 'load_feed') as featured:
            self.assertEqual(sync.prepare_channels(True), ([], []))
        room.assert_not_called()
        featured.assert_not_called()

    def test_agent_runs_wednesday_at_21_and_retries_without_changing_old_triggers(self):
        path = sync.DATA_DIR / 'note_magazine_sync.py'
        config = plistlib.loads(plistlib.dumps(sync.agent_config(path)))
        self.assertEqual(config['ProgramArguments'], ['/usr/bin/python3', str(path), '--endroll-only'])
        self.assertIn({'Weekday': 3, 'Hour': 21, 'Minute': 0}, config['StartCalendarInterval'])
        self.assertTrue(all(time['Weekday'] == 3 and time['Hour'] >= 21
                            for time in config['StartCalendarInterval']))
        self.assertTrue(config['RunAtLoad'])


if __name__ == '__main__':
    unittest.main()
