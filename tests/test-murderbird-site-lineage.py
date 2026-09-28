"""Prevent retired branding from returning through pages, locales, or metadata."""
import importlib.util
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import urljoin, urlsplit
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release', ROOT / 'scripts/build-release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def local_production_references(text, page):
    """Reject retired website paths while allowing canonical repository citations."""
    references = []

    class References(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name in {'href', 'src', 'poster', 'data'} and value:
                    url = urlsplit(urljoin(f'https://overkillhill.com/{page}', value))
                    if (url.hostname in {'overkillhill.com', 'www.overkillhill.com'}
                            and url.path.startswith('/assets/murderbird/production/')):
                        references.append(value)

    References().feed(text)
    return references


class LineageTests(unittest.TestCase):
    def test_public_references_retire_old_branding(self):
        retired = re.compile(r'over-kill-hill-p3-(?:sentinel-|bird-patrol-|title-horiz-|title-left-comp-right)')
        for relative in release.load_public_pages(ROOT):
            with self.subTest(page=str(relative)):
                text = (ROOT / relative).read_text(encoding='utf-8')
                self.assertIsNone(retired.search(text))
                self.assertEqual(local_production_references(text, relative), [])
                self.assertNotIn('frontal-alternate', text)

    def test_production_links_distinguish_website_from_source_repository(self):
        source = 'https://github.com/OKHP3/murderbird-uncaged/blob/main/assets/murderbird/production/audio/iron-verdict/production-notes.md'
        self.assertEqual(local_production_references(f'<a href="{source}">Notes</a>', 'projects/murderbird-uncaged/index.html'), [])
        for url in ('/assets/murderbird/production/file.wav',
                    '../../assets/murderbird/production/file.wav',
                    'https://overkillhill.com/assets/murderbird/production/file.wav',
                    '//www.overkillhill.com/assets/murderbird/production/file.wav'):
            with self.subTest(url=url):
                self.assertEqual(local_production_references(f'<audio src="{url}"></audio>', 'projects/murderbird-uncaged/index.html'), [url])

    def test_historical_sigil_remains_labeled(self):
        for path in ('manifesto/index.html', 'writings/murderbird/index.html'):
            self.assertIn('over-kill-hill-p3-title-low-right-bird-perch-comp-square-1024.webp', (ROOT / path).read_text(encoding='utf-8'))
        self.assertIn('The original sigil.', (ROOT / 'writings/murderbird/index.html').read_text(encoding='utf-8'))

    def test_cutout_alpha_and_delivery_aspect(self):
        for role in ('legal-guardian', 'contact-warning', 'under-construction', '404-reassembly'):
            with Image.open(ROOT / f'assets/img/murderbird-v2-{role}-960.png') as image:
                self.assertEqual(image.width, 960)
                self.assertEqual(image.height, 960 if role in ('legal-guardian', 'contact-warning') else 640)
                if role in ('legal-guardian', 'contact-warning'):
                    self.assertEqual(image.mode, 'RGBA')
                    self.assertEqual(image.getextrema()[3], (0, 255))


if __name__ == '__main__':
    unittest.main()
