"""Canonical editorial project facts and deterministic public summaries."""
from __future__ import annotations

import html
import json
import re
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup, Comment

ROOT = Path(__file__).resolve().parents[1]


def load_registry(root=ROOT):
    data = json.loads((root / 'site-src/project-status.json').read_text(encoding='utf-8'))
    validate(data, root)
    return data['projects']


def validate(data, root=ROOT):
    if data['schema'] != 2:
        raise ValueError('Expected project registry schema 2')
    date.fromisoformat(data['reviewed'])
    ids, routes = set(), set()
    for record in data['projects']:
        for field in ('id', 'title', 'route', 'kind', 'availability', 'maturity'):
            if not isinstance(record[field], str) or not record[field].strip():
                raise ValueError(f'Missing project {field}')
        if record['id'] in ids or record['route'] in routes:
            raise ValueError('Duplicate project ID or route')
        ids.add(record['id'])
        routes.add(record['route'])
        date.fromisoformat(record['reviewed'])
        if record['kind'] not in ('detail', 'shelf-exception'):
            raise ValueError('Unknown project kind')
        if not isinstance(record['shelf'], bool):
            raise ValueError('Shelf membership must be explicit')
        if (not record['shelf'] or record['kind'] == 'shelf-exception') and not record['shelf_exception']:
            raise ValueError('Missing shelf exception reason')
        evidence = record['evidence']
        if not re.fullmatch(r'[0-9a-f]{40}', evidence['revision']):
            raise ValueError('Evidence requires an immutable source revision')
        if not evidence['url'].startswith('https://github.com/OKHP3/') or '/blob/' + evidence['revision'] + '/' not in evidence['url']:
            raise ValueError('Evidence URL must identify its public source revision')
        # This source-review schema deliberately cannot certify runtime delivery.
        if evidence['tier'] != 'source-described' or evidence['delivery'] != 'unknown':
            raise ValueError('Unsupported delivery proof: source review cannot certify operation')
        if not evidence['summary'].strip():
            raise ValueError('Missing evidence scope')
        source = (root / evidence['source']).resolve()
        if not source.is_relative_to(root.resolve()) or not source.is_file():
            raise ValueError('Evidence source must exist inside the repository')
    pages_root = root / 'site-src/pages'
    manifest = json.loads((root / 'site-src/pages.json').read_text(encoding='utf-8'))
    redirects = {p['route'] for p in manifest['pages'] if p.get('redirect_to')}
    details = {
        '/' + p.parent.relative_to(pages_root).as_posix() + '/'
        for section in ('projects', 'skillz-forge')
        for p in (pages_root / section).rglob('index.main.html')
        if p.parent != pages_root / 'projects'
    } - redirects
    if details != {r['route'] for r in data['projects'] if r['kind'] == 'detail'}:
        raise ValueError('Project detail coverage differs from the source inventory')
    shelf = BeautifulSoup((root / 'site-src/pages/projects/index.main.html').read_text(encoding='utf-8'), 'html.parser')
    actual = set()
    for section in shelf.select('[data-project-shelf]'):
        for card in section.find_all('article'):
            actual.add(card.find('a')['href'])
    if actual != {r['route'] for r in data['projects'] if r['shelf']}:
        raise ValueError('Shelf coverage differs from declared records and exceptions')


def summary(record):
    return (f"Availability: {record['availability']}. Maturity: {record['maturity']}. "
            f"Evidence: {record['evidence']['summary']} Delivery: unknown.")


def summary_html(record):
    evidence = record['evidence']
    source = evidence['url']
    return ('<!-- AUTOGEN:PROJECT-STATUS -->'
            f'<p data-project-status="{html.escape(record["id"], quote=True)}">'
            + '<span data-project-status-text="">' + html.escape(summary(record)) + '</span> '
            + f'<a href="{html.escape(source, quote=True)}">Source record</a>'
            + f' (reviewed {record["reviewed"]}).</p><!-- /AUTOGEN:PROJECT-STATUS -->')


def visitor_summary(record):
    """Keep visible limitations derived from the canonical record."""
    if record['evidence']['delivery'] != 'unknown':
        raise ValueError('Disclosure wording requires review for a new delivery state')
    text = record['maturity'].rstrip('.') + '.'
    if record['maturity'] == 'Unknown':
        text = record['availability'] + '. Maturity unknown.'
    if record['id'] == 'mac-studio-local-ai-workbench':
        # The RAG limit is material even when the source disclosure is closed.
        return text + ' ' + record['evidence']['summary']
    if record['id'] == 'diagram-truth':
        # The deep link opened in a browser; the source registry does not
        # certify the rest of the tutorial or future deployments.
        return text + ' Step 3 observed September 29, 2026; full tutorial acceptance unverified.'
    software = record['availability'] in ('Published project', 'Published catalog project', 'Noindex concept page')
    label = 'Operation unverified.' if software else 'Delivery unverified.'
    return text + ' ' + label


def disclosure_html(record):
    """Native disclosure preserving complete canonical source facts."""
    return (f'<div data-project-status-disclosure="{html.escape(record["id"], quote=True)}">'
            + '<p data-project-status-brief="">' + html.escape(visitor_summary(record)) + '</p>'
            + '<details><summary>Status and source</summary>'
            + summary_html(record) + '</details></div>')


def render(main, route, records, *, disclosure=False):
    """Render status once per applicable card or detail, preserving source history."""
    if route not in ('/', '/projects/', '/universe/') and not any(r['route'] == route and r['kind'] == 'detail' for r in records):
        return main
    soup = BeautifulSoup(main, 'html.parser')
    disclosure = disclosure or soup.select_one('[data-status-presentation="disclosure"]') is not None
    labels = soup.select_one('[data-project-labels]')
    if labels:
        # Leave one separator where the moved block used to be. Repeated
        # rendering must not progressively collapse adjacent blank lines.
        previous = labels.previous_sibling
        following = labels.next_sibling
        if isinstance(previous, str) and not previous.strip() and isinstance(following, str) and not following.strip():
            following.extract()
        labels.extract()
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if str(comment).strip() in ('AUTOGEN:PROJECT-STATUS', '/AUTOGEN:PROJECT-STATUS'):
            comment.extract()
    for old in soup.select('[data-project-status-disclosure]'):
        old.decompose()
    for old in soup.select('[data-project-status]'):
        old.decompose()
    formatter = disclosure_html if disclosure else summary_html
    by_route = {r['route']: r for r in records}
    record = by_route.get(route)
    if record and record['kind'] == 'detail':
        status = BeautifulSoup(formatter(record), 'html.parser')
        anchor = soup.h1
        if disclosure:
            purpose = soup.h1.find_next_sibling('p')
            if purpose:
                anchor = purpose
            # Source labels are useful on request, after the reader knows the project.
            if labels:
                status.details.append(labels)
        elif labels:
            soup.h1.insert_before(labels)
        anchor.insert_after(status)
    if route in ('/', '/projects/', '/universe/'):
        for card in soup.find_all('article'):
            matches = {a.get('href') for a in card.find_all('a')} & by_route.keys()
            if len(matches) == 1:
                record = by_route[matches.pop()]
                heading = card.find(['h2', 'h3'])
                if heading:
                    anchor = heading
                    if disclosure:
                        anchor = next((p for p in heading.find_next_siblings('p') if not p.find('a')), heading)
                    anchor.insert_after(BeautifulSoup(formatter(record), 'html.parser'))
    return str(soup)
