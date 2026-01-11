import argparse
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import formatdate
from urllib.parse import quote_plus


def _best_locale_value(maybe_localized):
    if isinstance(maybe_localized, dict):
        return maybe_localized.get('en-US') or maybe_localized.get('en') or next(iter(maybe_localized.values()), '')
    return maybe_localized or ''


def _format_homepage(maybe_homepage):
    """Return a human-friendly homepage string.

    If the homepage is a dict with locale keys (eg. {'url': {'en-CA': 'https://...'}})
    include the locale in the output: "Homepage (en-CA): https://...".
    Otherwise return a simple string URL or repr fallback.
    """
    if not maybe_homepage:
        return ''

    # If it's already a string, return it
    if isinstance(maybe_homepage, str):
        return maybe_homepage

    # If it's a dict try common shapes
    if isinstance(maybe_homepage, dict):
        # common shape: {'url': {'en-US': 'https://...'}, 'outgoing': {...}}
        url_field = maybe_homepage.get('url') or maybe_homepage.get('homepage')
        if isinstance(url_field, dict):
            # pick the first locale key to display but keep the locale label
            try:
                locale_key = next(iter(url_field.keys()))
                locale_val = url_field.get(locale_key) or ''
                return f"Homepage ({locale_key}): {locale_val}"
            except StopIteration:
                pass

        if isinstance(url_field, str):
            return url_field

        # fallback: check for 'outgoing' which may be a dict similar to 'url'
        outgoing = maybe_homepage.get('outgoing')
        if isinstance(outgoing, dict):
            try:
                locale_key = next(iter(outgoing.keys()))
                locale_val = outgoing.get(locale_key)
                return f"Homepage ({locale_key}): {locale_val}"
            except StopIteration:
                pass

    # Last resort: string representation
    try:
        return str(maybe_homepage)
    except Exception:
        return ''


def generate_rss_feed(search_url=None, amo_type=None, q=None, page_size=50, max_items=None, max_days=None):
    """
    Generate RSS feed from AMO search API.

    - If `search_url` is provided, it will be used verbatim.
    - Otherwise a search URL is built using `amo_type` and `q` parameters.
    - Writes `public/amo_latest_addons.xml` always and, when `amo_type` is given,
      also writes `public/amo_latest_{amo_type}s.xml`.
    """

    headers = {"User-Agent": "amo-addons-rss/1.0 (+https://github.com/cm-fy/amo-add-ons-rss)"}

    collected = []

    # Helper to fetch pages following AMO's `next` links when present
    def _fetch_following(url):
        nonlocal collected
        while url:
            try:
                resp = requests.get(url, headers=headers, timeout=30)
            except Exception as e:
                print(f"Failed to fetch data from AMO API: {e}")
                break

            if resp.status_code != 200:
                print(f"Failed to fetch data from AMO API: {resp.status_code}")
                break

            data = resp.json()
            results = data.get('results', [])
            if not results:
                break

            collected.extend(results)

            # Stop when we've fetched enough items if max_items is set
            if max_items and len(collected) >= int(max_items):
                break

            # Follow AMO-provided next link if available
            next_url = data.get('next')
            if next_url:
                url = next_url
                continue

            # No 'next' link: if this was a constructed paged URL, fall back
            break

    # Normalize requested type for API vs filename (allow aliases like "theme")
    api_type = None
    file_label = None
    if amo_type:
        at = str(amo_type).lower()
        if at in ('theme', 'themes'):
            api_type = 'statictheme'
            file_label = 'theme'
        else:
            api_type = at
            # ensure a singular label for filenames (e.g. 'extension' -> 'extension')
            file_label = at[:-1] if at.endswith('s') else at

    # If the caller provided a full search URL, follow its `next` links
    if search_url:
        _fetch_following(search_url)
    else:
        base = 'https://addons.mozilla.org/api/v5/addons/search/'
        page = 1
        while True:
            params = []
            params.append('sort=updated')
            params.append(f'page_size={int(page_size)}')
            params.append(f'page={page}')
            if api_type:
                params.append(f'type={quote_plus(str(api_type))}')
            if q:
                params.append(f'q={quote_plus(str(q))}')
            api_url = base + '?' + '&'.join(params)

            try:
                resp = requests.get(api_url, headers=headers, timeout=30)
            except Exception as e:
                print(f"Failed to fetch data from AMO API: {e}")
                break

            if resp.status_code != 200:
                print(f"Failed to fetch data from AMO API: {resp.status_code}")
                break

            data = resp.json()
            results = data.get('results', [])
            if not results:
                break

            collected.extend(results)

            # Stop when we've fetched enough items if max_items is set
            if max_items and len(collected) >= int(max_items):
                break

            # Follow AMO-provided next link if available
            next_url = data.get('next')
            if next_url:
                # continue from the provided next URL
                _fetch_following(next_url)
                break

            # If fewer results than page_size, we've reached the end
            if len(results) < int(page_size):
                break

            page += 1

    # If max_days is supplied, filter out older addons
    if max_days:
        def _get_created_dt(a):
            # Attempt several fields to find a created/updated timestamp
            for candidate in (
                a.get('current_version', {}).get('file', {}).get('created'),
                a.get('current_version', {}).get('created'),
                a.get('last_updated'),
                a.get('created'),
            ):
                if candidate:
                    try:
                        return datetime.fromisoformat(candidate.replace('Z', '+00:00'))
                    except Exception:
                        try:
                            # fallback: try parsing common formats
                            return datetime.strptime(candidate, '%Y-%m-%dT%H:%M:%S.%fZ')
                        except Exception:
                            continue
            return None

        cutoff = datetime.utcnow() - timedelta(days=int(max_days))
        filtered = []
        for a in collected:
            dt = _get_created_dt(a)
            if dt is None or dt >= cutoff:
                filtered.append(a)
        collected = filtered

    addons = collected

    # Create RSS root
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    # Channel metadata
    title = ET.SubElement(channel, "title")
    title.text = "Latest Mozilla Add-on Releases"

    description = ET.SubElement(channel, "description")
    description.text = "RSS feed of the latest add-on updates from Mozilla Add-ons (AMO)"

    link = ET.SubElement(channel, "link")
    link.text = "https://addons.mozilla.org/"

    language = ET.SubElement(channel, "language")
    language.text = "en-us"

    # Add items
    for addon in addons:
        item = ET.SubElement(channel, "item")

        item_title = ET.SubElement(item, "title")
        title_name = _best_locale_value(addon.get('name'))
        version = addon.get('current_version', {}).get('version', '')
        item_title.text = f"{title_name} v{version}" if title_name or version else 'Unknown'

        # Build a richer HTML description including icon and metadata
        summary = _best_locale_value(addon.get('summary')) or 'No description available'

        # Try to find an icon URL in several possible shapes returned by AMO
        icon_url = None
        icons = addon.get('icons')
        if isinstance(icons, dict):
            for size in ('64', '48', '32', '16'):
                if icons.get(size):
                    icon_url = icons.get(size)
                    break
            if not icon_url:
                # fallback to any value
                icon_url = next(iter(icons.values()), None)
        elif isinstance(icons, list) and icons:
            first = icons[0]
            if isinstance(first, dict):
                icon_url = first.get('url') or first.get('src')
            else:
                icon_url = first
        icon_url = icon_url or addon.get('icon_url') or addon.get('thumbnail_url') or addon.get('preview_url')

        # Gather additional metadata when available
        authors = addon.get('authors') or []
        author_name = ''
        if isinstance(authors, list) and authors:
            first_author = authors[0]
            if isinstance(first_author, dict):
                author_name = first_author.get('name') or ''
            else:
                author_name = str(first_author)

        users = addon.get('average_daily_users') or addon.get('weekly_downloads') or addon.get('users') or addon.get('user_count') or ''
        # rating may appear in various places
        rating = None
        try:
            rating = addon.get('current_version', {}).get('rating') or addon.get('rating') or addon.get('average_rating')
        except Exception:
            rating = None

        categories = []
        for cat in addon.get('categories') or []:
            if isinstance(cat, dict):
                categories.append(cat.get('name') or cat.get('slug') or '')
            else:
                categories.append(str(cat))

        permissions = addon.get('permissions') or addon.get('required_permissions') or []
        homepage = addon.get('homepage') or addon.get('homepage_url') or addon.get('website') or addon.get('url')
        addon_id = addon.get('id') or addon.get('slug') or ''

        # Try to extract Firefox minimum version compatibility from latest version info
        def _extract_min_firefox_version(a):
            try:
                cv = a.get('current_version') or {}
                # common place: cv['compatibility']
                compat = cv.get('compatibility') or {}
                if isinstance(compat, dict):
                    f = compat.get('firefox') or compat.get('firefox_desktop')
                    if isinstance(f, dict):
                        mv = f.get('min_version') or f.get('min')
                        if mv:
                            return str(mv)

                # files -> applications
                files = cv.get('files') or []
                if files and isinstance(files, list):
                    for fobj in files:
                        apps = fobj.get('applications') or fobj.get('application') or {}
                        if isinstance(apps, dict):
                            firefox = apps.get('firefox') or apps.get('firefox-desktop') or apps.get('firefox_android')
                            if isinstance(firefox, dict):
                                mv = firefox.get('min_version') or firefox.get('min')
                                if mv:
                                    return str(mv)

                # file -> applications
                file0 = cv.get('file') or {}
                if isinstance(file0, dict):
                    apps = file0.get('applications') or {}
                    if isinstance(apps, dict):
                        firefox = apps.get('firefox')
                        if isinstance(firefox, dict):
                            mv = firefox.get('min_version') or firefox.get('min')
                            if mv:
                                return str(mv)
            except Exception:
                pass
            return ''

        min_firefox = _extract_min_firefox_version(addon)

        # Compose HTML description (will be escaped in XML); many feed readers accept HTML in descriptions
        parts = []
        if icon_url:
            parts.append(f'<img src="{icon_url}" alt="icon" style="float:left;margin:0 10px 6px 0;width:64px;height:64px;"/>')

        # Title and version already set in <title>, but include a header here
        header_html = f'<div><strong>{title_name}' + (f' v{version}' if version else '') + '</strong></div>'
        parts.append(header_html)

        parts.append(f'<div>{summary}</div>')

        meta_items = []
        if author_name:
            meta_items.append(f'Author: {author_name}')
        if users:
            meta_items.append(f'Users: {users}')
        if rating:
            meta_items.append(f'Rating: {rating}')
        if categories:
            meta_items.append('Categories: ' + ', '.join([c for c in categories if c]))
        if permissions:
            # permissions may be a list or string
            if isinstance(permissions, (list, tuple)):
                perms = ', '.join(str(p) for p in permissions)
            else:
                perms = str(permissions)
            meta_items.append('Permissions: ' + perms)
        if homepage:
            hp = _format_homepage(homepage)
            if hp:
                # _format_homepage may already include the "Homepage (... )" prefix
                meta_items.append(hp if hp.lower().startswith('homepage') else f'Homepage: {hp}')
        if min_firefox:
            meta_items.append(f'Works with Firefox: {min_firefox} and later')
        if addon_id:
            meta_items.append(f'ID: {addon_id}')

        if meta_items:
            # Use a slightly lighter grey so the footer is readable in dark themes
            parts.append('<div style="margin-top:6px;color:#9aa0a6;font-size:0.95em;">' + ' • '.join(meta_items) + '</div>')

        item_description = ET.SubElement(item, "description")
        item_description.text = '\n'.join(parts)

        item_link = ET.SubElement(item, "link")
        item_link.text = f"https://addons.mozilla.org/en-US/firefox/addon/{addon.get('slug', '')}/"

        # Try to derive a pubDate from various possible fields
        created_str = None
        for candidate in (
            addon.get('current_version', {}).get('file', {}).get('created'),
            addon.get('current_version', {}).get('created'),
            addon.get('last_updated'),
            addon.get('created'),
        ):
            if candidate:
                created_str = candidate
                break

        if created_str:
            try:
                pub_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
                item_pubdate = ET.SubElement(item, "pubDate")
                item_pubdate.text = formatdate(pub_date.timestamp())
            except Exception:
                pass

        # Add enclosure for the icon when available (helps some feed readers show thumbnails)
        try:
            if icon_url:
                # attempt to infer type from extension
                t = 'image/png'
                if icon_url.lower().endswith('.jpg') or icon_url.lower().endswith('.jpeg'):
                    t = 'image/jpeg'
                elif icon_url.lower().endswith('.gif'):
                    t = 'image/gif'
                ET.SubElement(item, 'enclosure', attrib={'url': icon_url, 'type': t})
        except Exception:
            pass

        # Add author element for RSS
        if author_name:
            try:
                ael = ET.SubElement(item, 'author')
                ael.text = author_name
            except Exception:
                pass

        # Add GUID
        try:
            guid = ET.SubElement(item, 'guid')
            guid.text = addon.get('slug') or str(addon.get('id') or '')
        except Exception:
            pass

    # Ensure output directory exists when run in CI
    outdir = os.path.join(os.getcwd(), 'public')
    os.makedirs(outdir, exist_ok=True)

    # Write the default feed only when no specific `amo_type` was requested.
    # This prevents a subsequent type-specific run (e.g. --type extension)
    # from overwriting the combined `amo_latest_addons.xml` output.
    tree = ET.ElementTree(rss)
    if not amo_type:
        default_outpath = os.path.join(outdir, 'amo_latest_addons.xml')
        tree.write(default_outpath, encoding="utf-8", xml_declaration=True)
        print(f"RSS feed generated: {default_outpath}")

    # Always write a type-specific file when `amo_type` is provided
    if amo_type:
        safe_label = ''.join(ch for ch in str(file_label or amo_type) if ch.isalnum() or ch in ('_', '-')).lower()
        type_outpath = os.path.join(outdir, f'amo_latest_{safe_label}s.xml')
        tree.write(type_outpath, encoding="utf-8", xml_declaration=True)
        print(f"Type-specific RSS feed generated: {type_outpath}")


def _env_or_arg():
    parser = argparse.ArgumentParser(description='Generate AMO RSS feeds')
    parser.add_argument('--search-url', help='Full AMO API search URL to use (overrides other params)')
    parser.add_argument('--type', dest='amo_type', help='AMO type parameter (e.g. extension or theme)')
    parser.add_argument('--q', help='Search query (q param)')
    parser.add_argument('--page-size', type=int, default=50, help='Number of results to fetch per page')
    parser.add_argument('--max-items', type=int, default=200, help='Maximum total number of items to fetch (across pages)')
    parser.add_argument('--max-days', type=int, default=0, help='Maximum age in days for items to include (0 = no limit)')
    args = parser.parse_args()

    search_url = args.search_url or os.environ.get('AMO_SEARCH_URL')
    amo_type = args.amo_type or os.environ.get('AMO_TYPE')
    q = args.q or os.environ.get('AMO_QUERY')
    page_size = args.page_size or int(os.environ.get('AMO_PAGE_SIZE', '50'))
    max_items = args.max_items or int(os.environ.get('AMO_MAX_ITEMS', '200'))
    max_days = args.max_days or int(os.environ.get('AMO_MAX_DAYS', '0'))

    return search_url, amo_type, q, page_size, max_items, (max_days if max_days > 0 else None)


if __name__ == "__main__":
    search_url, amo_type, q, page_size, max_items, max_days = _env_or_arg()
    generate_rss_feed(search_url=search_url, amo_type=amo_type, q=q, page_size=page_size, max_items=max_items, max_days=max_days)
