"""
简单心理 - 尝试构建文章页URL
"""
from scrapling.fetchers import Fetcher
from urllib.parse import urljoin

Fetcher.configure(adaptive=True, huge_tree=True)

# 用contentId尝试各种路径
cid = 69645
paths = [
    f"/news/{cid}",
    f"/article/{cid}",
    f"/p/{cid}",
    f"/detail/{cid}",
    f"/content/{cid}",
    f"/post/{cid}",
    f"/xapi/posts/api/index/v2/content?contentId={cid}&type=1",
]

for path in paths:
    url = urljoin("https://www.jiandanxinli.com", path)
    try:
        r = Fetcher.get(url, timeout=10)
        if r.status == 200 and len(r.body) > 5000:
            print(f"✅ {url}: {r.status}, {len(r.body)}b")
            body = r.body.decode('utf-8', errors='replace')
            # 看有内容吗
            import re
            text = re.sub(r'<[^>]+>', '', body)
            text = re.sub(r'\s+', ' ', text).strip()
            print(f"  文本: {text[:200]}")
        elif r.status != 404:
            print(f"   {url}: {r.status}, {len(r.body)}b")
    except:
        pass

# 浏览器加载文章URL
from scrapling.fetchers import DynamicFetcher
DynamicFetcher.configure(adaptive=True, huge_tree=True)

def check(page):
    import time, json
    time.sleep(5)
    r = page.evaluate("""() => {
        return {
            title: document.title,
            textLen: document.body.innerText.length,
            links: document.querySelectorAll('a').length
        };
    }""")
    print(f"  浏览器: {json.dumps(r, ensure_ascii=False)}")

DynamicFetcher.fetch("https://www.jiandanxinli.com/news/69645",
    headless=True, timeout=30000, disable_resources=False,
    network_idle=True, load_dom=True, page_action=check)
