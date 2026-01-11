import requests
url = "https://addons.mozilla.org/api/v5/addons/search/?sort=updated&page_size=50&type=extension"
collected = []
while url:
    print("fetch", url)
    r = requests.get(url, headers={"User-Agent":"amo-test"}, timeout=30)
    print("status", r.status_code)
    j = r.json()
    results = j.get("results", [])
    print("results", len(results))
    collected.extend(results)
    print("total", len(collected))
    url = j.get("next")
print("done total", len(collected))
