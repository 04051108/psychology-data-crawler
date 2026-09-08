"""
人邮出版社 - tenantId作为header
"""
from scrapling.fetchers import Fetcher
import json, os

Fetcher.configure(adaptive=True, huge_tree=True)

# 尝试多种方式传tenantId
url = "https://www.ptpress.com.cn/api/app-api/ws/newsInfo/getAppNewsInfoList"

# 1. header
for h in [{"tenantId": "1"}, {"tenant-id": "1"}, {"Tenant-Id": "1"}, {"X-Tenant-Id": "1"}]:
    r = Fetcher.get(url, timeout=10, headers={**h, "Content-Type": "application/json"})
    if r.status == 200:
        print(f"Header {h}: {r.status}, {len(r.body)}b -> {r.body.decode('utf-8',errors='replace')[:200]}")

# 2. 浏览器 - 拦截真实的API请求
from scrapling.fetchers import DynamicFetcher
DynamicFetcher.configure(adaptive=True, huge_tree=True)

def capture(page):
    import time, json
    api_responses = []
    def on_response(resp):
        if '/api/app-api' in resp.url:
            try:
                body = resp.text()
                api_responses.append({'url': resp.url, 'status': resp.status, 'body': body[:500],
                    'headers': dict(resp.request.headers)})
            except:
                pass
    page.on('response', on_response)
    page.goto("https://www.ptpress.com.cn", wait_until='networkidle')
    time.sleep(5)
    with open('_tmp.json','w',encoding='utf-8') as f:
        json.dump(api_responses, f, ensure_ascii=False)

DynamicFetcher.fetch("https://www.ptpress.com.cn", headless=True, timeout=30000,
    disable_resources=False, network_idle=True, load_dom=True, page_action=capture)

if os.path.exists('_tmp.json'):
    with open('_tmp.json', encoding='utf-8') as f:
        data = json.load(f)
    os.remove('_tmp.json')
    for r in data:
        print(f"\nURL: {r['url'][:120]}")
        print(f"Status: {r['status']}")
        print(f"Headers: {json.dumps(r.get('headers',{}), ensure_ascii=False)[:200]}")
        print(f"Body: {r.get('body','')[:200]}")
