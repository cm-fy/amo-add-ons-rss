import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import formatdate

def generate_rss_feed():
    # Fetch latest add-ons from AMO API
    api_url = "https://addons.mozilla.org/api/v5/addons/?sort=-last_updated&page_size=20"
    headers = {"User-Agent": "amo-addons-rss/1.0 (+https://github.com/cm-fy/amo-add-ons-rss)"}
    response = requests.get(api_url, headers=headers, timeout=30)
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
        # name may be a dict keyed by locale or a plain string
        name = addon.get('name')
        if isinstance(name, dict):
            title_name = name.get('en-US') or next(iter(name.values()), '')
        else:
            title_name = name or ''
        version = addon.get('current_version', {}).get('version', '')
        item_title.text = f"{title_name} v{version}" if title_name or version else 'Unknown'

        item_description = ET.SubElement(item, "description")
        summary = addon.get('summary')
        if isinstance(summary, dict):
            item_description.text = summary.get('en-US') or next(iter(summary.values()), 'No description available')
        else:
            item_description.text = summary or 'No description available'

        item_link = ET.SubElement(item, "link")
        item_link.text = f"https://addons.mozilla.org/en-US/firefox/addon/{addon.get('slug', '')}/"

        # Use last_updated as pubDate
        created_str = None
        try:
            created_str = addon.get('current_version', {}).get('file', {}).get('created')
        except Exception:
            created_str = None
        if created_str:
            pub_date = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
            item_pubdate = ET.SubElement(item, "pubDate")
            item_pubdate.text = formatdate(pub_date.timestamp())
        else:
            # skip pubDate when not available
            pass

    # Write to file
    tree = ET.ElementTree(rss)
    # Ensure output directory exists when run in CI
    try:
        import os
        os.makedirs('public', exist_ok=True)
        outpath = os.path.join('public', 'amo_latest_addons.xml')
    except Exception:
        outpath = 'amo_latest_addons.xml'
    tree.write(outpath, encoding="utf-8", xml_declaration=True)
    print(f"RSS feed generated: {outpath}")

if __name__ == "__main__":
    generate_rss_feed()