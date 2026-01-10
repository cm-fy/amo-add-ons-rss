import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import formatdate

def generate_rss_feed():
    # Fetch latest add-ons from AMO API
    api_url = "https://addons.mozilla.org/api/v5/addons/?sort=-last_updated&page_size=20"
    response = requests.get(api_url)
    if response.status_code != 200:
        print("Failed to fetch data from AMO API")
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
        item_title.text = f"{addon['name']['en-US']} v{addon['current_version']['version']}"
        
        item_description = ET.SubElement(item, "description")
        item_description.text = addon.get('summary', {}).get('en-US', 'No description available')
        
        item_link = ET.SubElement(channel, "link")
        item_link.text = f"https://addons.mozilla.org/en-US/firefox/addon/{addon['slug']}/"
        
        # Use last_updated as pubDate
        pub_date = datetime.fromisoformat(addon['current_version']['file']['created'].replace('Z', '+00:00'))
        item_pubdate = ET.SubElement(item, "pubDate")
        item_pubdate.text = formatdate(pub_date.timestamp())
    
    # Write to file
    tree = ET.ElementTree(rss)
    tree.write("amo_latest_addons.xml", encoding="utf-8", xml_declaration=True)
    print("RSS feed generated: amo_latest_addons.xml")

if __name__ == "__main__":
    generate_rss_feed()