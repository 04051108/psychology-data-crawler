"""查找 APA 分页 API"""
from scrapling.fetchers import Fetcher
import json

Fetcher.configure(adaptive=True, huge_tree=True)

# 1. 查看 content.min.js
print("=== content.min.js ===")
resp = Fetcher.get(
    'https://dl-client.apa.org/content.min.js',
    proxy='http://127.0.0.1:7897',
    timeout=15,
)
if resp.status == 200:
    js = resp.body.decode('utf-8', errors='replace')
    print(f"Length: {len(js)} chars")
    # 搜索 API 端点
    import re
    endpoints = re.findall(r'["\'](https?://[^"\']*api[^"\']*|/[^"\']*api[^"\']*)["\']', js)
    for e in endpoints[:10]:
        print(f'  API: {e}')
    # 搜索 ajax/fetch 调用
    for kw in ['ajax', 'fetch', 'getJSON', 'load', 'paginated', 'page']:
        idx = js.lower().find(kw)
        if idx >= 0:
            print(f"\n  Found '{kw}' at {idx}:")
            print(js[max(0,idx-50):idx+200])

# 2. 检查页面中初始加载的新闻数量
with open('apa_debug.html', 'r', encoding='utf-8') as f:
    html = f.read()

releases = re.findall(r'<div class="module first">(.*?)</div>\s*</div>', html, re.DOTALL)
print(f"\n\n=== 页面中初始加载的新闻: {len(releases)} ===")
for r in releases[:5]:
    title = re.search(r'class="title">(.*?)</p>', r)
    date = re.search(r'<em>(.*?)</em>', r)
    link = re.search(r'href="([^"]*)"', r)
    desc = re.search(r'class="wysiwyg">(.*?)</div>', r)
    print(f'  Title: {title.group(1) if title else "N/A"}')
    print(f'  Date: {date.group(1) if date else "N/A"}')
    print(f'  Link: {link.group(1) if link else "N/A"}')
    print(f'  Desc: {desc.group(1)[:80] if desc else "N/A"}')
    print()

# 3. 查找 all-paginated 相关的 data 属性
idx = html.find('all-paginated')
if idx >= 0:
    section = html[max(0,idx-200):idx+500]
    print(f"\n=== all-paginated 附近 ===")
    print(section)

# 4. 查找 loader
loader_idx = html.find('class="loader"')
if loader_idx >= 0:
    section = html[max(0,loader_idx-200):loader_idx+500]
    print(f"\n=== loader 附近 ===")
    print(section)
