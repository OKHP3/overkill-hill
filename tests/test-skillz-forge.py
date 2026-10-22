"""Protect moved project discovery, legacy links, and Shield evidence boundaries."""
import copy
import json
import runpy
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
STATUS = runpy.run_path(str(ROOT / 'scripts/project-status.py'))
SEARCH = runpy.run_path(str(ROOT / 'scripts/build-search-index.py'))


class SkillzForgeTests(unittest.TestCase):
    def test_inventory_has_no_stale_static_counts(self):
        source = (ROOT / 'site-src/pages/skillz-forge/index.main.html').read_text(encoding='utf-8')
        script = (ROOT / 'site-src/pages/skillz-forge/index.extras.html').read_text(encoding='utf-8')
        soup = BeautifulSoup(source, 'html.parser')
        self.assertEqual(soup.select_one('#skillz-inventory-heading').get_text(strip=True),
                         'Current public distribution catalog')
        self.assertEqual(soup.select_one('#skillz-live-skill-card').get_text(strip=True), 'Pending')
        self.assertEqual(soup.select_one('#skillz-live-family-card').get_text(strip=True), 'Pending')
        self.assertIsNotNone(soup.select_one('#skillz-live-maturity-summary'))
        self.assertNotIn('data-fallback=', source)
        self.assertIn('https://okhp3.github.io/skillz/data/project-summary.json', script)
        self.assertIn("throw new Error('Invalid catalog inventory')", script)
        self.assertIn("skillCardEl.textContent = 'Unavailable'", script)

    def test_project_menu_features_both_pages_as_peers(self):
        from public_page_boundary import iter_public_html_files
        for path in iter_public_html_files(ROOT):
            if 'assets' in path.relative_to(ROOT).parts:
                continue
            soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
            nav = soup.select_one('nav.primary-nav')
            if nav is None:
                continue
            # Some locale drafts use a flat four-link navigation without a
            # project menu. Check peer placement wherever that menu exists.
            project_link = nav.find('a', href=lambda h: h and h.endswith('/projects/'))
            if project_link is None or project_link.parent.find('ul') is None:
                continue
            with self.subTest(page=path.relative_to(ROOT).as_posix()):
                forge = nav.find('a', href='/skillz-forge/')
                shield = nav.find('a', href='/skillz-forge/skillz-shield/')
                self.assertIsNotNone(forge)
                self.assertIsNotNone(shield)
                self.assertEqual(forge.parent.name, 'li')
                self.assertIs(forge.parent.parent, shield.parent.parent)
                self.assertIsNone(forge.parent.find('ul'))

    def test_forge_and_shield_require_project_status(self):
        data = json.loads((ROOT / 'site-src/project-status.json').read_text(encoding='utf-8'))
        STATUS['validate'](data, ROOT)
        for route in ('/skillz-forge/', '/skillz-forge/skillz-shield/'):
            self.assertIn(route, [r['route'] for r in data['projects']])
            incomplete = copy.deepcopy(data)
            incomplete['projects'] = [r for r in incomplete['projects'] if r['route'] != route]
            with self.assertRaisesRegex(ValueError, 'detail coverage'):
                STATUS['validate'](incomplete, ROOT)

    def test_search_keeps_project_sections_and_status(self):
        for route in ('/skillz-forge/', '/skillz-forge/skillz-shield/'):
            entries = SEARCH['process_file'](ROOT / route.strip('/') / 'index.html')
            self.assertEqual(entries[0]['url'], route)
            self.assertEqual(entries[0]['category'], 'Project')
            self.assertTrue(entries[0]['body'].startswith('Availability:'))
            self.assertGreater(len(entries), 1, 'Project section links must stay searchable')
        self.assertEqual(SEARCH['process_file'](ROOT / 'projects/skillz/index.html'), [])

    def test_legacy_route_is_excluded_and_points_to_forge(self):
        soup = BeautifulSoup((ROOT / 'projects/skillz/index.html').read_text(encoding='utf-8'), 'html.parser')
        self.assertIn('noindex', soup.find('meta', attrs={'name': 'robots'})['content'])
        self.assertEqual(soup.find('link', rel='canonical')['href'], 'https://overkillhill.com/skillz-forge/')
        self.assertEqual(soup.find('meta', attrs={'http-equiv': 'refresh'})['content'], '0; url=/skillz-forge/')
        self.assertIsNotNone(soup.select_one('main a[href="/skillz-forge/"]'))
        sitemap = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        self.assertNotIn('<loc>https://overkillhill.com/projects/skillz/</loc>', sitemap)
        for route in ('/skillz-forge/', '/skillz-forge/skillz-shield/'):
            self.assertIn('<loc>https://overkillhill.com' + route + '</loc>', sitemap)

    def test_breadcrumbs_match_public_hierarchy(self):
        for route, expected in [('/skillz-forge/', ['/', '/skillz-forge/']),
                                ('/skillz-forge/skillz-shield/', ['/', '/skillz-forge/', '/skillz-forge/skillz-shield/'])]:
            soup = BeautifulSoup((ROOT / route.strip('/') / 'index.html').read_text(encoding='utf-8'), 'html.parser')
            nodes = [json.loads(s.string) for s in soup.select('script[type="application/ld+json"]')]
            crumbs = next(n for n in nodes if n.get('@type') == 'BreadcrumbList')
            self.assertEqual([i['item'] for i in crumbs['itemListElement']], ['https://overkillhill.com' + p for p in expected])


if __name__ == '__main__':
    unittest.main()
