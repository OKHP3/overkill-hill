#!/usr/bin/env python3
"""Build the four regional locale drafts without changing public release files.

The canonical English HTML is the source for both regional pairs. Existing
target files are preserved as draft working artifacts during regeneration, so
an editorial pass can update changed units without treating another locale as
translation authority.
"""
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
ROUTES = {"/": "index.html", "/about/": "about/index.html", "/projects/": "projects/index.html", "/contact/": "contact/index.html"}
REVIEWED_ES_MX = {"index.html": "index.html", "about/index.html": "about-index.html", "projects/index.html": "projects-index.html", "contact/index.html": "contact-index.html"}
BASE = "https://overkillhill.com"
SOURCE_HASHES = ROOT / 'i18n' / 'pilot' / 'source-hashes-murderbird-stills-2026-09-06.json'
PAIR_CONTRACTS = {
    'en-gb': ('dictionary.en-us-en-uk.json', 'voice-profile.en-us.json'),
    'es-mx': ('dictionary.en-us-es-mx.json', 'voice-profile.en-us.json'),
}
CSP_META_RE = re.compile(
    rb'<meta\b(?=[^>]*\bhttp-equiv=["\']Content-Security-Policy["\'])[^>]*>',
    re.I,
)
ASSET_FINGERPRINT_RE = re.compile(
    rb'(\b(?:href|src)=["\'][^"\']*/assets/[^"\']*?)\?v=[0-9a-f]{8,64}(?=["\'])',
    re.I,
)

def sync_asset_fingerprints(page: str, canonical: str) -> str:
    """Use the canonical release fingerprints in every locale output."""
    for asset in ("/assets/css/theme.css", "/assets/js/app.js"):
        match = re.search(rf'{re.escape(asset)}\?v=([0-9a-f]+)', canonical, re.I)
        if match:
            page = re.sub(rf'{re.escape(asset)}\?v=[0-9a-f]+', f'{asset}?v={match.group(1)}', page, flags=re.I)
    return page

ST_GEORGE = (
    '<svg aria-hidden="true" class="lang-flag" height="14" viewBox="0 0 30 20" width="21">'
    '<rect fill="#FFFFFF" height="20" width="30"/><path d="M15 0V20M0 10H30" stroke="#CE1124" stroke-width="4"/>'
    '</svg>'
)
MEXICO = (
    '<svg aria-hidden="true" class="lang-flag" height="14" viewBox="0 0 30 20" width="21">'
    '<rect fill="#006847" height="20" width="10"/><rect fill="#FFFFFF" height="20" width="10" x="10"/><rect fill="#CE1126" height="20" width="10" x="20"/>'
    '<g aria-label="Mexico coat of arms" transform="translate(15 10)"><path d="M-1.7-2.8C.6-3.8 2.8-2 2.1.1C1.5 1.9-.5 3-2.1 2.1C-3.3 1.4-3.1-.7-1.7-2.8Z" fill="#6B4F2F"/><path d="M-2.4 2.6c.7-2.1 1.2-3 2.2-3.8M-3.1 1.1l1.2.5M-2.8-.4l1.1.5" fill="none" stroke="#006847" stroke-linecap="round" stroke-width=".65"/><path d="M1.1-1.7l1.5-.8" stroke="#CE1126" stroke-linecap="round" stroke-width=".65"/></g>'
    '</svg>'
)

USA = (
    '<svg aria-hidden="true" class="lang-flag" height="14" viewBox="0 0 30 20" width="21">'
    '<rect fill="#B22234" height="20" width="30"/><rect fill="#FFFFFF" height="1.54" width="30" y="1.54"/>'
    '<rect fill="#FFFFFF" height="1.54" width="30" y="4.62"/><rect fill="#FFFFFF" height="1.54" width="30" y="7.69"/>'
    '<rect fill="#FFFFFF" height="1.54" width="30" y="10.77"/><rect fill="#FFFFFF" height="1.54" width="30" y="13.85"/>'
    '<rect fill="#FFFFFF" height="1.54" width="30" y="16.92"/><rect fill="#3C3B6E" height="10.77" width="12"/>'
    '</svg>'
)
FRANCE = '<svg aria-hidden="true" class="lang-flag" height="14" viewBox="0 0 30 20" width="21"><rect fill="#0055A4" height="20" width="10"/><rect fill="#FFFFFF" height="20" width="10" x="10"/><rect fill="#EF4135" height="20" width="10" x="20"/></svg>'
GERMANY = '<svg aria-hidden="true" class="lang-flag" height="14" viewBox="0 0 30 20" width="21"><rect fill="#000000" height="6.67" width="30"/><rect fill="#DD0000" height="6.67" width="30" y="6.67"/><rect fill="#FFCE00" height="6.66" width="30" y="13.34"/></svg>'
SPAIN = '<svg aria-hidden="true" class="lang-flag" height="14" viewBox="0 0 30 20" width="21"><rect fill="#AA151B" height="5" width="30"/><rect fill="#F1BF00" height="10" width="30" y="5"/><rect fill="#AA151B" height="5" width="30" y="15"/></svg>'
LOCALE_MENU = (
    ('en', 'en-US', 'English (US)', USA),
    ('en-gb', 'en-GB', 'English (UK) · Draft', ST_GEORGE),
    ('fr', 'fr-FR', 'Français (France)', FRANCE),
    ('de', 'de-DE', 'Deutsch (Deutschland)', GERMANY),
    ('es', 'es-ES', 'Español (España)', SPAIN),
    ('es-mx', 'es-MX', 'Español (México) · Borrador', MEXICO),
)


def noindex(page: str) -> str:
    page = re.sub(r'(<meta[^>]+name=["\']robots["\'][^>]+content=["\'])[^"\']*', r'\1noindex, follow', page, flags=re.I)
    page = re.sub(r'(<meta[^>]+content=["\'])[^"\']*(?=["\'][^>]+name=["\']robots)', r'\1noindex, follow', page, flags=re.I)
    if "name=\"robots\"" not in page and "name='robots'" not in page:
        page = page.replace("</head>", '<meta name="robots" content="noindex, follow">\n</head>')
    return page


def route_links(page: str, source_locale: str, target_locale: str) -> str:
    page = page.replace(f"/{source_locale}/", f"/{target_locale}/")
    return page


def locale_href(locale: str, route: str) -> str:
    return route if locale == 'en' else f'/{locale}{route}'


def render_locale_switch(active_locale: str, route: str) -> str:
    """Render the complete draft selector without changing published locale pages."""
    active = next(item for item in LOCALE_MENU if item[0] == active_locale)
    options = []
    for locale, tag, label, flag in LOCALE_MENU:
        current = ' aria-current="true" class="lang-switch-option is-current"' if locale == active_locale else ' class="lang-switch-option"'
        options.append(
            f'<li><a{current} aria-label="{label}" href="{locale_href(locale, route)}" hreflang="{tag}" lang="{tag}">{flag}'
            f'<span class="lang-switch-option-label">{label}</span></a></li>'
        )
    return (
        '<div class="lang-switch"><button aria-expanded="false" aria-haspopup="true" '
        f'aria-label="Language: {active[2]}" class="lang-switch-toggle" type="button">'
        f'<span class="lang-flag-current">{active[3]}</span></button>'
        f'<ul class="lang-switch-menu" hidden>{"".join(options)}</ul></div>'
    )


def replace_locale_switch(page: str, active_locale: str, route: str) -> str:
    updated, count = re.subn(
        r'<div class="lang-switch">.*?</ul></div>',
        render_locale_switch(active_locale, route),
        page,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit(f'Missing language switcher for {active_locale} {route}')
    return updated


def load_pair_contract(locale: str) -> tuple[dict, dict]:
    pair_dir = ROOT / 'i18n' / 'pilot' / locale
    dictionary_name, profile_name = PAIR_CONTRACTS[locale]
    dictionary = json.loads((pair_dir / dictionary_name).read_text(encoding='utf-8'))
    profile = json.loads((pair_dir / profile_name).read_text(encoding='utf-8'))
    pair = dictionary.get('language_pair', {})
    profile_pair = profile.get('language_pair', profile)
    if pair.get('source_locale') != 'en-US' or profile_pair.get('source_locale') != 'en-US':
        raise SystemExit(f'Invalid source locale in {locale} pair contract')
    target_locale = 'en-GB' if locale == 'en-gb' else 'es-MX'
    if pair.get('target_locale') != target_locale:
        raise SystemExit(f'Invalid dictionary target locale for {locale}')
    return dictionary, profile


def normalized_translation_source(content: bytes) -> bytes:
    """Remove generated release metadata before checking editorial source freshness."""
    normalized = content.replace(b"\r\n", b"\n")
    normalized = CSP_META_RE.sub(b"", normalized)
    return ASSET_FINGERPRINT_RE.sub(rb"\1", normalized)


def canonical_text_hash(path: Path) -> str:
    """Hash translatable source independent of checkout and generated CSP metadata."""
    return hashlib.sha256(normalized_translation_source(path.read_bytes())).hexdigest()


def verify_sources() -> dict:
    expected = json.loads(SOURCE_HASHES.read_text(encoding='utf-8'))
    actual = {}
    for route, rel in ROUTES.items():
        source_path = ROOT / rel
        actual[route] = canonical_text_hash(source_path)
        release_hash = expected.get("normalized_routes", {}).get(route)
        if not release_hash:
            raise SystemExit(f'Missing durable normalized release hash for {route}')
        if actual[route] != release_hash:
            raise SystemExit(f'Source changed for {route}; refresh the reviewed pair from the recorded source revision')
    return expected


def set_meta_content(page: str, property_name: str, content: str) -> str:
    """Set one Open Graph meta value without changing unrelated metadata."""
    matches = 0

    def replace_tag(match: re.Match[str]) -> str:
        nonlocal matches
        tag = match.group(0)
        property_match = re.search(r'\bproperty=["\']([^"\']+)["\']', tag, re.I)
        if not property_match or property_match.group(1).lower() != property_name.lower():
            return tag
        updated, replacements = re.subn(
            r'(\bcontent=["\'])[^"\']*(["\'])',
            lambda content_match: content_match.group(1) + content + content_match.group(2),
            tag,
            count=1,
            flags=re.I,
        )
        if replacements != 1:
            raise SystemExit(f'Missing content attribute on {property_name} meta tag')
        matches += 1
        return updated

    result = re.sub(r'<meta\b[^>]*>', replace_tag, page, flags=re.I)
    if matches != 1:
        raise SystemExit(f'Expected one {property_name} meta tag, found {matches}')
    return result


def set_canonical_href(page: str, url: str) -> str:
    """Set the sole canonical link without touching media or structured-data URLs."""
    matches = 0

    def replace_tag(match: re.Match[str]) -> str:
        nonlocal matches
        tag = match.group(0)
        rel_match = re.search(r'\brel=["\']([^"\']+)["\']', tag, re.I)
        if not rel_match or 'canonical' not in rel_match.group(1).lower().split():
            return tag
        updated, replacements = re.subn(
            r'(\bhref=["\'])[^"\']*(["\'])',
            lambda href_match: href_match.group(1) + url + href_match.group(2),
            tag,
            count=1,
            flags=re.I,
        )
        if replacements != 1:
            raise SystemExit('Missing href attribute on canonical link')
        matches += 1
        return updated

    result = re.sub(r'<link\b[^>]*>', replace_tag, page, flags=re.I)
    if matches != 1:
        raise SystemExit(f'Expected one canonical link, found {matches}')
    return result


def rewrite_in_scope_links(page: str, locale: str) -> str:
    """Keep navigation inside the four-page locale set when a target exists."""
    for route in sorted(ROUTES, key=len, reverse=True):
        target = locale_href(locale, route)
        page = re.sub(
            rf'(\bhref=["\']){re.escape(route)}(["\'])',
            lambda match: match.group(1) + target + match.group(2),
            page,
        )
    return page


def replace_navigation_identity(page: str, locale: str) -> str:
    """Keep every regional draft on the current organization mark and home route."""
    home = locale_href(locale, "/")
    match = re.search(r'<div class="logo">.*?</div>', page, re.S)
    if match is None:
        raise SystemExit(f'Missing navigation logo for {locale}')
    logo = match.group(0)
    logo, home_count = re.subn(r'(<a\b[^>]*\bhref=")[^"]*(")', rf'\g<1>{home}\2', logo, count=1)
    if not re.search(
        r'\bsrc="/assets/img/(?:(?:favicons/)?murderbird-v2-icon-nav-96|over-kill-hill-p3-sentinel-warning-square-256)\.png"',
        logo,
    ):
        raise SystemExit(f'Unexpected navigation logo asset for {locale}')
    logo, _loading_count = re.subn(
        r'\s+loading="(?:lazy|eager)"(?=[^>]*\bsrc="/assets/img/(?:(?:favicons/)?murderbird-v2-icon-nav-96|over-kill-hill-p3-sentinel-warning-square-256)\.png")',
        '',
        logo,
        count=1,
    )
    logo = logo.replace(
        '/assets/img/over-kill-hill-p3-sentinel-warning-square-256.png',
        '/assets/img/murderbird-v2-icon-nav-96.png',
        1,
    )
    logo = logo.replace('/assets/img/favicons/murderbird-v2-icon-nav-96.png',
                        '/assets/img/murderbird-v2-icon-nav-96.png', 1)
    logo = logo.replace('height="40"', 'height="40" loading="eager"', 1)
    updated = page[:match.start()] + logo + page[match.end():]
    if home_count != 1:
        raise SystemExit(f'Unexpected navigation logo shape for {locale}')
    return updated


HOMEPAGE_HERO_ALTS = {
    'es-mx': 'El MurderBird está de pie sobre dos patas metálicas junto a un banco de trabajo y una computadora con monitor de tubo. Tiene un pico curvo, alas compactas plegadas, una armadura oscura con pátina y un ojo naranja brillante.',
    'en-gb': 'The MurderBird stands on two metal feet beside a workbench and CRT computer, with a hooked beak, compact folded wings, dark patinated armour, and a glowing orange eye.',
}

# Bounded local-preview fallback; no native-language approval is implied.
HOMEPAGE_STORY_CTAS = {
    'es-mx': 'Conoce al MurderBird: lee la historia de su origen (en inglés) →',
    'en-gb': 'Meet the MurderBird: read the origin story (in English) →',
}


def replace_homepage_hero(page: str, locale: str, canonical: str) -> str:
    """Reuse canonical structure with recorded local-preview locale text."""
    if locale not in HOMEPAGE_HERO_ALTS:
        raise SystemExit(f'No reviewed homepage hero alt for {locale}')
    pattern = r'<div class="hero-visual">.*?</div>'
    match = re.search(pattern, canonical, re.S)
    if match is None:
        raise SystemExit('Missing canonical homepage hero')
    hero, count = re.subn(
        r'(<img\b[^>]*\balt=)(["\'])(.*?)\2',
        lambda found: found.group(1) + '"' + escape(HOMEPAGE_HERO_ALTS[locale], quote=True) + '"',
        match.group(0), count=1, flags=re.S,
    )
    if count != 1:
        raise SystemExit('Canonical homepage hero must have an image alt')
    hero, count = re.subn(
        r'<a href="/writings/murderbird/">.*?</a>',
        lambda _: '<a href="/writings/murderbird/" hreflang="en">' + escape(HOMEPAGE_STORY_CTAS[locale]) + '</a>',
        hero, count=1, flags=re.S,
    )
    if count != 1:
        raise SystemExit('Canonical homepage story invitation missing')
    updated, count = re.subn(pattern, lambda _: hero, page, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'Missing homepage hero for {locale}')
    return updated


def adapt_visible_text(page: str, dictionary: dict) -> str:
    """Apply approved en-GB wording only to text nodes, never attributes or code."""
    replacements = [
        (entry['source'], entry['target'])
        for entry in dictionary.get('entries', [])
        if entry.get('handling') == 'adapt' and entry.get('source') and entry.get('target')
    ]
    protected_tags = {'code', 'pre', 'script', 'style', 'template'}
    protected_depth = 0
    chunks = re.split(r'(<[^>]+>)', page)
    for index, chunk in enumerate(chunks):
        if chunk.startswith('<'):
            tag_match = re.match(r'</?\s*([\w:-]+)', chunk)
            if tag_match:
                tag_name = tag_match.group(1).lower()
                if tag_name in protected_tags:
                    if chunk.startswith('</'):
                        protected_depth = max(0, protected_depth - 1)
                    elif not chunk.rstrip().endswith('/>'):
                        protected_depth += 1
            continue
        if protected_depth:
            continue
        for source, target in replacements:
            chunk = re.sub(rf'\b{re.escape(source)}\b', target, chunk)
        chunks[index] = chunk
    return ''.join(chunks)


def build_en_gb(source: str, route: str, dictionary: dict) -> str:
    page = source
    page = sync_asset_fingerprints(page, source)
    target_url = BASE + '/en-gb' + route
    page = page.replace('<html lang="en">', '<html lang="en-GB">', 1)
    page = set_canonical_href(page, target_url)
    page = set_meta_content(page, 'og:url', target_url)
    page = set_meta_content(page, 'og:locale', 'en_GB')
    page = page.replace('content="index, follow', 'content="noindex, follow')
    page = noindex(page)
    page = page.replace('English (US)', 'English (UK) · Draft')
    page = page.replace('Language: English (US)', 'Language: English (UK) · Draft')
    page = page.replace('hreflang="en"', 'hreflang="en-GB"').replace('lang="en"', 'lang="en-GB"')
    page = rewrite_in_scope_links(page, 'en-gb')
    page = adapt_visible_text(page, dictionary)
    page = page.replace('colors', 'colours').replace('Color Scheme', 'Colour Scheme')
    page = re.sub(r'<link[^>]+rel="alternate"[^>]*>', '', page, flags=re.I)
    page = page.replace(f'href="{route}" hreflang="en-GB"', f'href="/en-gb{route}" hreflang="en-GB"')
    page = page.replace('class="lang-flag"', 'class="lang-flag"', 1)
    page = re.sub(r'<svg aria-hidden="true" class="lang-flag".*?</svg>', ST_GEORGE, page, count=1, flags=re.S)
    page = replace_navigation_identity(replace_locale_switch(page, 'en-gb', route), 'en-gb')
    return replace_homepage_hero(page, 'en-gb', source) if route == '/' else page


def sync_hub_masthead(page: str) -> str:
    """Apply the shared shell while preserving every reviewed translated word."""
    marker = '<!-- AUTOGEN:LOCALE-MASTHEAD -->'
    if marker in page:
        return page
    start = page.index('<section', page.index('<main'))
    end = page.index('</section>', start) + len('</section>')
    soup = BeautifulSoup(page[start:end], 'html.parser')
    hero = soup.section
    if 'forge-masthead' in hero.get('class', []):
        return page[:start] + marker + '\n' + page[start:end] + '\n<!-- /AUTOGEN:LOCALE-MASTHEAD -->' + page[end:]
    before = ' '.join(hero.stripped_strings)
    hero['class'] = [c for c in hero.get('class', []) if c != 'a14-editorial-hero'] + ['forge-masthead', 'forge-masthead--hub']
    hero.h1['id'] = hero.h1.get('id', 'page-title')
    hero['aria-labelledby'] = hero.h1['id']
    for decoration in hero.select('.brand-stripes, .hero-blueprint-bg'):
        decoration.decompose()
    for wrapper in list(hero.select('.container')):
        wrapper.unwrap()
    inner = soup.new_tag('div', attrs={'class': 'container hero-inner'})
    for child in list(hero.contents):
        inner.append(child.extract())
    hero.append(inner)
    for classes in ['hero-blueprint-bg', 'brand-stripes brand-stripes--okh']:
        hero.insert(0, soup.new_tag('div', attrs={'class': classes, 'aria-hidden': 'true'}))
    for node in hero.select('.reveal-on-scroll'):
        node['class'] = [c for c in node['class'] if c != 'reveal-on-scroll']
    if before != ' '.join(hero.stripped_strings):
        raise SystemExit('Locale masthead adaptation changed reviewed text')
    return page[:start] + marker + '\n' + str(hero) + '\n<!-- /AUTOGEN:LOCALE-MASTHEAD -->' + page[end:]


def build_es_mx(source: str, canonical: str, route: str, dictionary: dict) -> str:
    # The reviewed artifact is the translation authority. Loading the pair
    # dictionary here keeps the generator contract explicit without applying
    # generic Spanish substitutions over reviewed prose.
    if not dictionary.get('entries'):
        raise SystemExit('es-MX dictionary has no reviewed vocabulary entries')
    page = sync_hub_masthead(route_links(source, "es", "es-mx"))
    page = sync_asset_fingerprints(page, canonical)
    page = page.replace('<html lang="es">', '<html lang="es-MX">', 1)
    page = page.replace('https://overkillhill.com/es' + route, BASE + '/es-mx' + route)
    page = noindex(page)
    page = page.replace('hreflang="es"', 'hreflang="es-MX"').replace('lang="es"', 'lang="es-MX"')
    page = re.sub(r'(<meta[^>]+property=["\']og:locale["\'][^>]+content=["\'])es_ES', r'\1es_MX', page, flags=re.I)
    # The shared mobile menu is right-anchored to the flag button. Keep the
    # visible current-locale label compact enough to remain wholly on-screen;
    # the expanded accessible name retains the full regional wording.
    page = page.replace('Español</span>', 'ES-MX · Borrador</span>')
    page = page.replace('aria-label="Language: Español"', 'aria-label="Language: Español (México) · Borrador"')
    page = page.replace('aria-label="Español"', 'aria-label="Español (México) · Borrador"')
    page = re.sub(r'<link[^>]+rel="alternate"[^>]*>', '', page, flags=re.I)
    page = re.sub(r'<svg aria-hidden="true" class="lang-flag".*?</svg>', MEXICO, page, count=1, flags=re.S)
    # Project-level Mexican usage overrides. Preserve intentional technology
    # terms such as workflow and promptcraft rather than forcing calques.
    page = page.replace('ordenador', 'computadora').replace('móvil', 'celular')
    # Draft artifacts retain their reviewed prose, but inherit the canonical
    # font resources and current forge notice so the locale shell renders with
    # the same brand typography and site-wide status context as English.
    # Font faces live in the canonical shared stylesheet. Remove legacy links
    # from reviewed input without editing that preserved translation artifact.
    page = re.sub(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', page, flags=re.I)
    if '/assets/css/theme.css' not in page:
        raise SystemExit('Locale page is missing the canonical font stylesheet')
    # The release banner is shared shell content, not part of the preserved
    # translated article copy. Keep draft shells aligned with the current
    # production es-MX banner without rewriting their reviewed source files.
    locale_route = ROOT / 'es-mx' / ROUTES[route]
    if locale_route.exists():
        current_locale = locale_route.read_text(encoding='utf-8')
        current_banner = re.search(
            r'<section\b[^>]*class="site-specials site-specials--okh"[^>]*>.*?</section>',
            current_locale,
            flags=re.S,
        )
        if current_banner:
            banner_pattern = r'<section\b[^>]*class="site-specials site-specials--okh"[^>]*>.*?</section>'
            if re.search(banner_pattern, page, flags=re.S):
                page = re.sub(banner_pattern, current_banner.group(0), page, count=1, flags=re.S)
            else:
                page = page.replace('</header>', current_banner.group(0) + '</header>', 1)
    if 'class="site-specials site-specials--okh"' not in page:
        notice = (
            '<section aria-label="Actualización de la fragua" class="site-specials site-specials--okh">'
            '<span class="site-specials-label">🔥Recién salido de la FRAGUA⚒️</span>'
            '<a class="site-specials-link" data-banner-localized="true" data-banner-release="v0.5" href="/writings/first-diagram-is-a-liar/#council-scoring">'
            'La versión 0.5 ya está en línea: el Consejo de IAs calificó los diagramas de los demás; cada modelo fue más duro consigo mismo que quien diseñó la evaluación. Léelo →'
            '</a></section>'
        )
        page = page.replace('</header>', notice + '</header>', 1)
    page = replace_navigation_identity(replace_locale_switch(page, 'es-mx', route), 'es-mx')
    return replace_homepage_hero(page, 'es-mx', canonical) if route == '/' else page


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--locale', choices=('en-gb', 'es-mx'), required=True)
    args = parser.parse_args()
    dictionary, _profile = load_pair_contract(args.locale)
    verify_sources()
    for route, rel in ROUTES.items():
        source_path = ROOT / rel
        if not source_path.exists():
            raise SystemExit(f'Missing source page: {source_path}')
        page = source_path.read_text(encoding='utf-8')
        output = ROOT / args.locale / rel
        # The canonical English page is always opened first. es-MX output is
        # emitted from the reviewed pair artifact, never from another locale
        # or from the generated output directory.
        reviewed = ROOT / 'i18n' / 'pilot' / 'es-mx' / 'reviewed' / REVIEWED_ES_MX[rel]
        target_input = reviewed.read_text(encoding='utf-8') if args.locale == 'es-mx' else page
        rendered = build_en_gb(page, route, dictionary) if args.locale == 'en-gb' else build_es_mx(target_input, page, route, dictionary)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding='utf-8')
        print(output.relative_to(ROOT))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
