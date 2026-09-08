"""
中国心理学剩余站点 - 最终完整爬虫
逐个爬取，输出进度
"""
import json, os, re, sys, time
from urllib.parse import urljoin
from scrapling.fetchers import Fetcher

OUT = "output"
Fetcher.configure(adaptive=True, huge_tree=True)
os.makedirs(OUT, exist_ok=True)
PROXY = "http://127.0.0.1:7897"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def extract_body(resp):
    """从响应中提取正文"""
    best, blen = "", 0
    for sel in ["article", ".article", ".content", ".main-content", ".detail",
                 ".news-content", ".field-item", "#content", ".article-content",
                 "main", ".detail-content", ".entry-content", ".post-content",
                 ".xxy-content", ".news-detail", ".text", ".TRS_Editor",
                 ".Custom_UnionStyle", ".con_text", ".news_text", ".articleBox",
                 ".show_content", "#zoom", ".content_article", ".con_content",
                 ".text-content", ".page-content"]:
        for el in resp.css(sel):
            t = el.get_all_text(strip=True)
            if len(t) > blen and len(t) < 100000:
                best, blen = t, len(t)
    return best


def extract_images(resp, base_url):
    """提取图片"""
    seen, imgs = set(), []
    for img in resp.css("img[src]"):
        src = img.attrib.get("src", "")
        alt = img.attrib.get("alt", "")
        if src:
            full = src if src.startswith("http") else urljoin(base_url, src)
            if any(k in full.lower() for k in ['icon', 'logo', 'banner', 'button', 'bg_']):
                continue
            key = full.split("?")[0].rsplit("/", 1)[-1][:60]
            if key not in seen and len(key) > 5:
                seen.add(key)
                imgs.append({"src": full, "alt": alt or ""})
    return imgs


def process_article(url, source=""):
    """处理单篇文章"""
    try:
        resp = Fetcher.get(url, timeout=15)
    except:
        return {"body_text": "", "body_text_length": 0, "body_images": []}
    if resp.status != 200:
        return {"body_text": "", "body_text_length": 0, "body_images": []}
    body = extract_body(resp)
    imgs = extract_images(resp, url)
    return {"body_text": body or "", "body_text_length": len(body or ""), "body_images": imgs}


def save(name, articles):
    path = os.path.join(OUT, f"cn_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    wb = sum(1 for a in articles if a.get("body_text"))
    ti = sum(len(a.get("body_images", [])) for a in articles)
    log(f"💾 {name}: {len(articles)}篇 正文{wb} 图片{ti}")


# ======== 1. 轻工业出版社 - 修复正文 ========
def crawl_chlip():
    log("="*40)
    log("1/8 轻工业出版社")
    log("="*40)
    articles = []
    try:
        resp = Fetcher.get("http://www.chlip.com.cn/news/index.php", proxy=PROXY, timeout=15)
    except:
        return []
    html = resp.body.decode("utf-8", errors="replace") if resp.status == 200 else ""
    if not html:
        return []

    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1).strip(), re.sub(r'\s+', ' ', m.group(2)).strip()
        if len(text) > 8 and 'show.php' in href:
            articles.append({"title": text, "url": urljoin("http://www.chlip.com.cn", href), "source": "轻工业出版社"})

    log(f"发现 {len(articles)} 篇，开始获取正文...")
    total = len(articles)
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:40]}...", end="", flush=True)
        detail = process_article(a["url"])
        a.update(detail)
        s = "✅" + (f" ({a['body_text_length']}c)" if a["body_text"] else "")
        print(f"\r  [{i}/{total}] {s}: {a['title'][:40]}")
        if i < total: time.sleep(0.3)
    return articles


# ======== 2. 华师大出版社 ========
def crawl_ecnupress():
    log("="*40)
    log("2/8 华师大出版社")
    log("="*40)
    base = "https://www.ecnupress.com.cn"
    articles = []

    # 尝试不同的新闻列表URL
    urls = [
        "/custom/index/nl/1588746689?s=7",
        "/custom/index/nl/1588746689?s=10",
        "/news/list",
    ]
    for path in urls:
        try:
            resp = Fetcher.get(base + path, proxy=PROXY, timeout=15)
        except:
            continue
        if resp.status != 200:
            continue
        html = resp.body.decode("utf-8", errors="replace")
        for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
            href, text = m.group(1).strip(), re.sub(r'\s+', ' ', m.group(2)).strip()
            if len(text) > 10 and 'news_id=' in href and '查看更多' not in text:
                articles.append({"title": text, "url": urljoin(base, href), "source": "华师大出版社"})
        if articles:
            log(f"从 {path} 找到 {len(articles)} 篇")
            break
        time.sleep(0.3)

    if not articles:
        log("❌ 未找到新闻")
        return []

    total = len(articles)
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:40]}...", end="", flush=True)
        detail = process_article(a["url"])
        a.update(detail)
        s = "✅" + (f" ({a['body_text_length']}c)" if a["body_text"] else "")
        print(f"\r  [{i}/{total}] {s}: {a['title'][:40]}")
        if i < total: time.sleep(0.3)
    return articles


# ======== 3. 中科院心理所 ========
def crawl_psych_ac():
    log("="*40)
    log("3/8 中科院心理所")
    log("="*40)
    articles = []
    try:
        resp = Fetcher.get("https://www.psych.ac.cn", proxy=PROXY, timeout=15)
    except Exception as e:
        log(f"SSL错误: {e}，尝试不验证证书...")
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        try:
            resp = Fetcher.get("https://www.psych.ac.cn", proxy=PROXY, timeout=15)
        except Exception as e2:
            log(f"仍失败: {e2}")
            return []

    if resp.status != 200:
        return []
    html = resp.body.decode("utf-8", errors="replace")
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1).strip(), m.group(2).strip()
        if len(text) > 6 and any(k in href.lower() for k in ['xw', 'tz', 'news', 'content', '20']):
            articles.append({"title": text, "url": urljoin("https://www.psych.ac.cn", href), "source": "中科院心理所"})

    if not articles:
        # 尝试从所有链接中提取
        for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
            href, text = m.group(1).strip(), m.group(2).strip()
            if len(text) > 8 and not href.startswith('#') and 'javascript' not in href:
                articles.append({"title": text, "url": urljoin("https://www.psych.ac.cn", href), "source": "中科院心理所"})

    log(f"发现 {len(articles)} 篇")
    total = len(articles)
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:40]}...", end="", flush=True)
        detail = process_article(a["url"])
        a.update(detail)
        s = "✅" + (f" ({a['body_text_length']}c)" if a["body_text"] else "")
        print(f"\r  [{i}/{total}] {s}: {a['title'][:40]}")
        if i < total: time.sleep(0.3)
    return articles


# ======== 4. 中国心理学会 ========
def crawl_cpsbeijing():
    log("="*40)
    log("4/8 中国心理学会")
    log("="*40)
    articles = []
    try:
        resp = Fetcher.get("https://www.cpsbeijing.org", proxy=PROXY, timeout=15)
    except:
        return []
    if len(resp.body) < 500:
        log("页面空白，尝试其他页面...")
        for path in ["/news", "/article", "/list", "/index.php", "/"]:
            try:
                r = Fetcher.get(f"https://www.cpsbeijing.org{path}", proxy=PROXY, timeout=10)
                if r.status == 200 and len(r.body) > 500:
                    resp = r
                    log(f"从 {path} 获取到内容 ({len(r.body)}b)")
                    break
            except:
                continue
            time.sleep(0.3)
        else:
            log("❌ 无法获取内容")
            return []

    html = resp.body.decode("utf-8", errors="replace")
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1).strip(), m.group(2).strip()
        if len(text) > 6 and not href.startswith('#') and 'javascript' not in href:
            articles.append({"title": text, "url": urljoin("https://www.cpsbeijing.org", href), "source": "中国心理学会"})

    log(f"发现 {len(articles)} 篇")
    total = len(articles)
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:40]}...", end="", flush=True)
        detail = process_article(a["url"])
        a.update(detail)
        s = "✅" + (f" ({a['body_text_length']}c)" if a["body_text"] else "")
        print(f"\r  [{i}/{total}] {s}: {a['title'][:40]}")
        if i < total: time.sleep(0.3)
    return articles


# ======== 5. 简单心理 ========
def crawl_jiandanxinli():
    log("="*40)
    log("5/8 简单心理")
    log("="*40)
    articles = []
    try:
        resp = Fetcher.get("https://www.jiandanxinli.com/news", proxy=PROXY, timeout=15)
    except:
        return []
    if len(resp.body) < 5000:
        log("❌ 页面需JS渲染")
        return []
    html = resp.body.decode("utf-8", errors="replace")
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1), m.group(2).strip()
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > 6 and href.startswith('/news/') and '/news/' != href:
            articles.append({"title": text, "url": f"https://www.jiandanxinli.com{href}", "source": "简单心理"})
    log(f"发现 {len(articles)} 篇")
    total = len(articles)
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:40]}...", end="", flush=True)
        detail = process_article(a["url"])
        a.update(detail)
        s = "✅" + (f" ({a['body_text_length']}c)" if a["body_text"] else "")
        print(f"\r  [{i}/{total}] {s}: {a['title'][:40]}")
        if i < total: time.sleep(0.3)
    return articles


# ======== 6. 壹心理 ========
def crawl_xinli001():
    log("="*40)
    log("6/8 壹心理")
    log("="*40)
    articles = []
    for url in ["https://www.xinli001.com", "https://www.xinli001.com/article"]:
        try:
            resp = Fetcher.get(url, proxy=PROXY, timeout=15)
        except:
            continue
        if len(resp.body) < 5000:
            log(f"  {url}: 内容过少 ({len(resp.body)}b)")
            continue
        html = resp.body.decode("utf-8", errors="replace")
        count = 0
        for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
            href, text = m.group(1).strip(), m.group(2).strip()
            if len(text) > 6 and ('article' in href or 'post' in href or 'info' in href):
                articles.append({"title": text, "url": urljoin("https://www.xinli001.com", href), "source": "壹心理"})
                count += 1
        log(f"  {url}: 找到 {count} 篇")
        time.sleep(0.3)

    if not articles:
        log("❌ 壹心理可能全JS渲染")
        return []

    total = len(articles)
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:40]}...", end="", flush=True)
        detail = process_article(a["url"])
        a.update(detail)
        s = "✅" + (f" ({a['body_text_length']}c)" if a["body_text"] else "")
        print(f"\r  [{i}/{total}] {s}: {a['title'][:40]}")
        if i < total: time.sleep(0.3)
    return articles


# ======== 7. 人邮出版社 ========
def crawl_ptpress():
    log("="*40)
    log("7/8 人邮出版社")
    log("="*40)
    articles = []
    try:
        resp = Fetcher.get("https://www.ptpress.com.cn", proxy=PROXY, timeout=15)
    except:
        return []
    if len(resp.body) < 3000:
        log("❌ 需JS渲染")
        return []
    html = resp.body.decode("utf-8", errors="replace")
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1).strip(), m.group(2).strip()
        if len(text) > 6:
            articles.append({"title": text, "url": urljoin("https://www.ptpress.com.cn", href), "source": "人邮出版社"})
    log(f"发现 {len(articles)} 篇")
    return articles


# ======== 8. 浙江教育出版/武志红/曾奇峰 ========
def crawl_others():
    log("="*40)
    log("8/8 其他站点")
    log("="*40)

    sites = [
        ("zjeph", "浙江教育出版", "http://www.zjeph.com", False),
        ("wzhxlx", "武志红", "https://www.wzhxlx.com", False),
        ("zengqifeng", "曾奇峰", "https://www.zengqifeng.com", False),
    ]

    for fname, sname, url, _ in sites:
        log(f"  {sname}: {url}")
        try:
            r = Fetcher.get(url, proxy=PROXY, timeout=10)
            log(f"    HTTP {r.status} ({len(r.body)}b)")
            if r.status == 200 and len(r.body) > 1000:
                html = r.body.decode("utf-8", errors="replace")
                articles = []
                for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
                    href, text = m.group(1).strip(), m.group(2).strip()
                    if len(text) > 8:
                        articles.append({"title": text, "url": urljoin(url, href), "source": sname})
                if articles:
                    save(fname, articles)
        except Exception as e:
            log(f"    ❌ {type(e).__name__}")


# ======== Main ========
log("🚀 开始爬取剩余中国心理学站点")
log(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
t0 = time.time()

crawlers = [
    ("chlip", crawl_chlip),
    ("ecnupress", crawl_ecnupress),
    ("psych_ac", crawl_psych_ac),
    ("cpsbeijing", crawl_cpsbeijing),
    ("jiandanxinli", crawl_jiandanxinli),
    ("xinli001", crawl_xinli001),
    ("ptpress", crawl_ptpress),
]

for fname, fn in crawlers:
    try:
        arts = fn()
        if arts:
            save(fname, arts)
    except Exception as e:
        log(f"❌ {fname}: {e}")
    log(f"⏱ 累计: {time.time()-t0:.0f}s\n")

# 其他站点
crawl_others()

log(f"\n{'='*40}")
log(f"🏁 全部完成！总耗时: {time.time()-t0:.0f}s")
