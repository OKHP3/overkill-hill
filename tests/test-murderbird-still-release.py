"""Clean-checkout dependencies and narrative placement for the accepted still release."""
import hashlib
import runpy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
MODULE = runpy.run_path(str(ROOT / 'scripts/build-murderbird-release-register.py'))
RELEASE = runpy.run_path(str(ROOT / 'scripts/build-release.py'))


class MurderBirdStillTests(unittest.TestCase):
    def test_dependency_closure_and_exact_source_identity(self):
        payload = MODULE['record']()
        self.assertEqual(6, len(payload['masters']))
        self.assertEqual(18, sum(len(m['derivatives']) for m in payload['masters']))
        source = ROOT / payload['masters'][0]['path']
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            MODULE['describe'](source, '0' * 64)

    def test_story_semantics_and_no_video_placeholders(self):
        page = BeautifulSoup((ROOT / 'writings/murderbird/index.html').read_text(encoding='utf-8'), 'html.parser')
        for scene in ('maker', 'water', 'mechanic', 'heart', 'sentinel'):
            figure = page.select_one('#media-' + scene)
            self.assertIsNotNone(figure)
            self.assertEqual('the-builder' if scene == 'heart' else 'the-' + scene, figure.parent['id'])
            self.assertEqual('lazy', figure.img['loading'])
            self.assertTrue(figure.img['alt'])
            self.assertTrue(figure.figcaption.get_text(strip=True))
        self.assertEqual('p', page.select_one('#media-maker').find_next_sibling().name)
        self.assertIn('morning of the demonstration', page.select_one('#media-maker').find_next_sibling().get_text())
        self.assertEqual(1, len(page.select('video')))
        figure = page.select_one('#media-first-choice')
        self.assertEqual('the-builder', figure.parent['id'])
        self.assertIn('before the support failed', figure.find_previous_sibling('p').get_text())
        video = figure.video
        self.assertTrue(video.has_attr('controls'))
        self.assertTrue(video.has_attr('playsinline'))
        self.assertFalse(video.has_attr('autoplay'))
        self.assertFalse(video.has_attr('loop'))
        self.assertEqual('none', video['preload'])
        self.assertEqual('video/mp4', video.source['type'])
        self.assertEqual('/assets/video/murderbird-first-choice-635f0e15.mp4', video.source['src'])
        self.assertEqual('635f0e1552bac61699c03c8406157207f6230ea817bb1ecaeb3adbb3a7bf8613',
                         hashlib.sha256((ROOT / video.source['src'].lstrip('/')).read_bytes()).hexdigest())
        self.assertTrue((ROOT / video['poster'].lstrip('/')).is_file())
        self.assertIn('silent', figure.figcaption.get_text())
        for description_id in video['aria-describedby'].split():
            self.assertTrue(page.find(id=description_id).get_text(strip=True))

    def test_story_theme_song_is_reader_started(self):
        page = BeautifulSoup((ROOT / 'writings/murderbird/index.html').read_text(encoding='utf-8'), 'html.parser')
        players = page.select('audio')
        self.assertEqual(1, len(players))
        player = players[0]
        self.assertTrue(player.has_attr('controls'))
        self.assertFalse(player.has_attr('autoplay'))
        self.assertFalse(player.has_attr('loop'))
        self.assertEqual('none', player['preload'])
        self.assertEqual('Iron Verdict, the MurderBird theme song', player['aria-label'])
        sources = player.select('source')
        self.assertEqual(1, len(sources))
        self.assertEqual('audio/mpeg', sources[0]['type'])
        self.assertEqual('https://okhp3.github.io/murderbird-uncaged/audio/iron-verdict-v3/full-song.mp3',
                         sources[0]['src'])
        lyrics = player.parent.find('a', href='https://okhp3.github.io/murderbird-uncaged/audio/iron-verdict-v3/lyrics.txt')
        self.assertIsNotNone(lyrics)
        self.assertEqual('Read the lyrics', lyrics.get_text(strip=True))

    def test_exploratory_package_not_required(self):
        # Archived source may coexist in Git. Prove dependency independence in
        # a selected-input tree instead of requiring its absence from the repo.
        selected = MODULE['record']()
        with tempfile.TemporaryDirectory(prefix='murderbird-selected-inputs-') as temporary:
            fixture = Path(temporary)
            required = [
                'scripts/build-murderbird-hero.py',
                'scripts/build-murderbird-release-register.py',
                selected['social']['path'],
                *[master['path'] for master in selected['masters']],
            ]
            for relative in required:
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            (fixture / 'assets/audit').mkdir(parents=True)

            def run_builder(name, *arguments):
                result = subprocess.run(
                    [sys.executable, str(fixture / 'scripts' / name), *arguments],
                    cwd=fixture, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            self.assertFalse((fixture / 'assets/murderbird/v2').exists())
            self.assertFalse((fixture / 'assets/img/webp').exists())
            for master in selected['masters']:
                run_builder('build-murderbird-hero.py', '--asset', master['id'])
                run_builder('build-murderbird-hero.py', '--check', '--asset', master['id'])
            run_builder('build-murderbird-release-register.py')
            run_builder('build-murderbird-release-register.py', '--check')
            rebuilt = json.loads((fixture / 'assets/audit/murderbird-still-release-register.json').read_text(encoding='utf-8'))
            self.assertEqual(6, len(rebuilt['masters']))
            self.assertEqual(18, sum(len(master['derivatives']) for master in rebuilt['masters']))
            self.assertEqual(18, len(list((fixture / 'assets/img/webp').glob('*.webp'))))
            self.assertEqual(selected['social']['sha256'], rebuilt['social']['sha256'])
            self.assertEqual(
                {master['path']: master['sha256'] for master in selected['masters']},
                {master['path']: master['sha256'] for master in rebuilt['masters']},
            )
            self.assertFalse((fixture / 'assets/murderbird/v2').exists())
            for name in MODULE['HELD_NAMES']:
                self.assertFalse((fixture / 'assets/img/library' / name).exists())
            # Positive dependency control: an accepted input really is required.
            missing = fixture / selected['masters'][0]['path']
            missing.unlink()
            rejected = subprocess.run(
                [sys.executable, str(fixture / 'scripts/build-murderbird-release-register.py'), '--check'],
                cwd=fixture, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn(missing.name, rejected.stderr)

    def test_archived_inputs_stay_out_of_pages(self):
        self.assertTrue((ROOT / 'assets/murderbird/v2').is_dir())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'site-release'
            RELEASE['build'](ROOT, output, 'a' * 40)
            self.assertFalse((output / 'assets/murderbird/v2').exists())
            for name in MODULE['HELD_NAMES']:
                self.assertTrue((ROOT / 'assets/img/library' / name).is_file())
                self.assertFalse((output / 'assets/img/library' / name).exists())


if __name__ == '__main__':
    unittest.main()
