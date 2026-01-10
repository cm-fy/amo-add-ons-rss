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

        item_description = ET.SubElement(item, "description")
        item_description.text = _best_locale_value(addon.get('summary')) or 'No description available'

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
