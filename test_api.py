import requests
headers={'User-Agent':'amo-addons-rss/1.0'}
urls=[
 'https://addons.mozilla.org/api/v5/addons/?sort=-last_updated&page_size=20',
 'https://addons.mozilla.org/api/v5/addons/addon/?sort=created&page_size=20',
 'https://addons.mozilla.org/api/v5/addons/addon/?sort=-created&page_size=20',
 'https://addons.mozilla.org/api/v5/addons/search/?page_size=20',
 'https://addons.mozilla.org/api/v5/addons/search/?sort=created&page_size=20',
 'https://addons.mozilla.org/api/v5/addons/addon/?page_size=20'
]
for u in urls:
    try:
        r=requests.get(u,headers=headers,timeout=10)
        print(u, r.status_code)
        if r.status_code==200:
            print(r.text[:200])
    except Exception as e:
        print('err',u,e)
