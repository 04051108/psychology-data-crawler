"""尝试 BPS 的 JSON API"""
from scrapling.fetchers import Fetcher

Fetcher.configure(adaptive=True, huge_tree=True)

# 常见的 Drupal/Next.js API 端点
api_paths = [
    '/jsonapi/node/news',
    '/api/news',
    '/api/v1/news',
    '/bps-news/page-0',
    '/bps-news/page-1',
    '/api/bps-news',
    '/jsonapi',
    '/sites/default/files/json/news.json',
    '/news.json',
    '/bps-news/index.json',
]

for path in api_paths:
    url = f'https://www.bps.org.uk{path}'
    try:
        resp = Fetcher.get(url, proxy='http://127.0.0.1:7897', timeout=10)
        body = resp.body.decode('utf-8', errors='replace')[:200]
        if resp.status == 200 and len(resp.body) > 50:
            print(f"✅ {url}: {resp.status}, {len(resp.body)}b")
            print(f"   {body}")
            break
        else:
            print(f"❌ {url}: {resp.status}, {len(resp.body)}b")
    except Exception as e:
        print(f"⚠️ {url}: {e}")
