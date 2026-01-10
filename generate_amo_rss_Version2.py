import argparse
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import formatdate
from urllib.parse import quote_plus


def _best_locale_value(maybe_localized):
    if isinstance(maybe_localized, dict):
        return maybe_localized.get('en-US') or maybe_localized.get('en') or next(iter(maybe_localized.values()), '')
    return maybe_localized or ''


def generate_rss_feed(search_url=None, amo_type=None, q=None, page_size=20):
    """
    Generate RSS feed from AMO search API.

    - If `search_url` is provided, it will be used verbatim.
    - Otherwise a search URL is built using `amo_type` and `q` parameters.
    - Writes `public/amo_latest_addons.xml` always and, when `amo_type` is given,
      also writes `public/amo_latest_{amo_type}s.xml`.
    """

    if search_url:
        api_url = search_url
    else:
        base = 'https://addons.mozilla.org/api/v5/addons/search/'
        params = []
        params.append('sort=updated')
        params.append(f'page_size={int(page_size)}')
        if amo_type:
            params.append(f'type={quote_plus(str(amo_type))}')
        if q:
            params.append(f'q={quote_plus(str(q))}')
        api_url = base + '?' + '&'.join(params)

    headers = {"User-Agent": "amo-addons-rss/1.0 (+https://github.com/cm-fy/amo-add-ons-rss)"}
    try:
        response = requests.get(api_url, headers=headers, timeout=30)
    except Exception as e:
        print(f"Failed to fetch data from AMO API: {e}")
        return

    if response.status_code != 200:
        print(f"Failed to fetch data from AMO API: {response.status_code}")
        try:
            print(response.text[:1000])
        except Exception:
            pass
        return

    data = response.json()
    addons = data.get('results', [])

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
            meta_items.append(f'Homepage: {homepage}')
        if addon_id:
            meta_items.append(f'ID: {addon_id}')

        if meta_items:
            parts.append('<div style="margin-top:6px;color:#666;font-size:0.95em;">' + ' • '.join(meta_items) + '</div>')

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

    # Always write the default feed name
    default_outpath = os.path.join(outdir, 'amo_latest_addons.xml')
    tree = ET.ElementTree(rss)
    tree.write(default_outpath, encoding="utf-8", xml_declaration=True)
    print(f"RSS feed generated: {default_outpath}")

    # Also write a type-specific file if requested
    if amo_type:
        safe_type = ''.join(ch for ch in str(amo_type) if ch.isalnum() or ch in ('_', '-')).lower()
        type_outpath = os.path.join(outdir, f'amo_latest_{safe_type}s.xml')
        tree.write(type_outpath, encoding="utf-8", xml_declaration=True)
        print(f"Type-specific RSS feed generated: {type_outpath}")


def _env_or_arg():
    parser = argparse.ArgumentParser(description='Generate AMO RSS feeds')
    parser.add_argument('--search-url', help='Full AMO API search URL to use (overrides other params)')
    parser.add_argument('--type', dest='amo_type', help='AMO type parameter (e.g. extension or theme)')
    parser.add_argument('--q', help='Search query (q param)')
    parser.add_argument('--page-size', type=int, default=20, help='Number of results to fetch')
    args = parser.parse_args()

    search_url = args.search_url or os.environ.get('AMO_SEARCH_URL')
    amo_type = args.amo_type or os.environ.get('AMO_TYPE')
    q = args.q or os.environ.get('AMO_QUERY')
    page_size = args.page_size or int(os.environ.get('AMO_PAGE_SIZE', '20'))

    return search_url, amo_type, q, page_size


if __name__ == "__main__":
    search_url, amo_type, q, page_size = _env_or_arg()
    generate_rss_feed(search_url=search_url, amo_type=amo_type, q=q, page_size=page_size)
