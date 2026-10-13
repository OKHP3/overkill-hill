"""Keep visitor hierarchy and source qualifications consistent across page families."""
import json
import runpy
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
PAGES = json.loads((ROOT / 'site-src/pages.json').read_text(encoding='utf-8'))['pages']
STATUS = runpy.run_path(str(ROOT / 'scripts/project-status.py'))
RECORDS = STATUS['load_registry'](ROOT)
UTILITIES = {'/404.html', '/under-construction.html', '/search/', '/found-ry/'}


class PageFamilyTests(unittest.TestCase):
    def test_draft_writings_keep_status_without_a_blocking_modal(self):
        for slug in ('biases-as-constants', 'magnus-saga'):
            with self.subTest(slug=slug):
                source = ROOT / 'site-src/pages/writings' / slug
                main = BeautifulSoup((source / 'index.main.html').read_text(encoding='utf-8'), 'html.parser')
                extras = BeautifulSoup((source / 'index.extras.html').read_text(encoding='utf-8'), 'html.parser')
                published = BeautifulSoup((ROOT / 'writings' / slug / 'index.html').read_text(encoding='utf-8'), 'html.parser')
                for page in (main, published):
                    notice = page.select_one('.draft-notice[role="note"]')
                    self.assertIsNotNone(notice)
                    self.assertIn('Draft: not yet published.', notice.get_text())
                    self.assertIsNone(page.select_one('.construction-overlay, [data-wip-dismiss]'))
                self.assertIsNone(extras.select_one('.construction-overlay, [data-wip-dismiss]'))
                self.assertIn('noindex', published.select_one('meta[name="robots"]')['content'])

    def test_content_pages_share_an_accessible_masthead(self):
        for page in PAGES:
            if page['route'] in UTILITIES or page.get('redirect_to'):
                continue
            with self.subTest(route=page['route']):
                soup = BeautifulSoup((ROOT / page['path']).read_text(encoding='utf-8'), 'html.parser')
                hero = soup.select_one('.forge-masthead')
                self.assertIsNotNone(hero)
                self.assertEqual(len(hero.select('h1')), 1)
                self.assertEqual(len(hero.select('.hero-inner')), 1)
                self.assertEqual(hero.select_one('.hero-blueprint-bg').get('aria-hidden'), 'true')
                self.assertIsNone(hero.find_parent(class_='container'))

    def test_project_evidence_is_complete_but_collapsed(self):
        for record in RECORDS:
            if record['kind'] != 'detail':
                continue
            path = ROOT / record['route'].strip('/') / 'index.html'
            soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
            with self.subTest(route=record['route']):
                wrappers = soup.select('[data-project-status-disclosure]')
                self.assertEqual(len(wrappers), 1)
                wrapper = wrappers[0]
                self.assertFalse(wrapper.details.has_attr('open'))
                self.assertEqual(wrapper.select_one('[data-project-status-text]').get_text(), STATUS['summary'](record))
                self.assertEqual(wrapper.details.a['href'], record['evidence']['url'])
                self.assertIsNone(wrapper.select_one('[data-project-status-brief]').find_parent('details'))
                self.assertIn(record['maturity'], wrapper.get_text())

    def test_authoring_labels_and_sibling_hero_do_not_leak(self):
        prompt = BeautifulSoup((ROOT / 'prompt-forge/index.html').read_text(encoding='utf-8'), 'html.parser')
        self.assertNotIn('1. HERO', prompt.main.get_text())
        legal = BeautifulSoup((ROOT / 'legal/index.html').read_text(encoding='utf-8'), 'html.parser')
        self.assertIsNone(legal.select_one('.askjamie-hero, .askjamie-paper'))

    def test_locale_brand_fonts_and_regional_regeneration(self):
        builder = runpy.run_path(str(ROOT / 'scripts/build-locale-drafts.py'))
        for locale in ('fr', 'de', 'es', 'en-gb', 'es-mx'):
            for sub in ('', 'about', 'projects', 'contact'):
                path = ROOT / locale / sub / 'index.html'
                soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
                with self.subTest(path=str(path)):
                    self.assertIsNotNone(soup.select_one('.forge-masthead'))
                    fonts = ' '.join(link.get('href', '') for link in soup.select('link[rel="stylesheet"]'))
                    self.assertIn('/assets/css/theme.css', fonts)
                    self.assertNotIn('fonts.googleapis.com', fonts)
                    if locale == 'es-mx':
                        reviewed_name = f'{sub}-index.html' if sub else 'index.html'
                        reviewed = (ROOT / 'i18n/pilot/es-mx/reviewed' / reviewed_name).read_text(encoding='utf-8')
                        adapted = builder['sync_hub_masthead'](reviewed)
                        self.assertEqual(adapted.count('<!-- AUTOGEN:LOCALE-MASTHEAD -->'), 1)
                        self.assertEqual(adapted.count('<!-- /AUTOGEN:LOCALE-MASTHEAD -->'), 1)
                        result = BeautifulSoup(adapted, 'html.parser')
                        self.assertIsNotNone(result.select_one('.forge-masthead'))
                        self.assertEqual(list(BeautifulSoup(reviewed, 'html.parser').stripped_strings), list(result.stripped_strings))
                        self.assertEqual(adapted, builder['sync_hub_masthead'](adapted))

    def test_workbench_identity_precedes_historical_detail(self):
        soup = BeautifulSoup((ROOT / 'projects/mac-studio-local-ai-workbench/index.html').read_text(encoding='utf-8'), 'html.parser')
        hero = soup.select_one('.forge-masthead')
        self.assertIsNotNone(hero)
        self.assertNotIn('Reading this journal:', hero.get_text())
        self.assertIn('RAG unverified', hero.get_text())
        self.assertIn('May 2026', hero.get_text())
        self.assertIsNotNone(soup.select_one('#journal-context'))


if __name__ == '__main__':
    unittest.main()
