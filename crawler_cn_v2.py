"""
中国心理学站点爬虫 v2 (修复版)
===========================
基于 Scrapling + Playwright，爬取中国心理学站点新闻/文章内容。
修复内容：
- 移除强制代理（可用但非必须）
- 修复各站点正文选择器
- 新增 Playwright 处理 SPA 站点
- 新增 SSL 降级处理
- 新增 GBK 编码支持
- 新增之前成功爬取的站点（北大、北师大、华南师大）

站点列表:
1. 轻工业出版社     http://www.chlip.com.cn
2. 华师大出版社     https://www.ecnupress.com.cn
3. 中科院心理所     https://www.psych.ac.cn (SSL降级)
4. 中国心理学会     https://www.cpsbeijing.org (GBK编码)
5. 简单心理         https://www.jiandanxinli.com (SPA, Playwright)
6. 壹心理           https://www.xinli001.com (SPA, Playwright)
7. 北师大心理学部   https://psych.bnu.edu.cn
8. 北大心理学院     https://www.psy.pku.edu.cn
9. 华南师大心理学院 https://psy.scnu.edu.cn
10. 人邮出版社      https://www.ptpress.com.cn (限制访问, 尽力)
"""

import json, os, re, sys, time
from datetime import datetime
from urllib.parse import urljoin
from scrapling.fetchers import Fetcher

OUTPUT_DIR = "output"
REQUEST_TIMEOUT = 20
REQUEST_RETRIES = 2
DETAIL_DELAY = 0.5

Fetcher.configure(adaptive=True, huge_tree=True)

# ============================================================
# 工具函数
# ============================================================

def safe_get(url, **kwargs):
    params = {
        "timeout": REQUEST_TIMEOUT,
        "retries": REQUEST_RETRIES,
        "follow_redirects": True,
    }
    params.update(kwargs)
    try:
        resp = Fetcher.get(url, **params)
        return resp
    except Exception as e:
        return None

def fetch_ssl_fallback(url):
    """SSL 降级获取"""
    resp = safe_get(url, verify=True)
    if resp is None:
        resp = safe_get(url, verify=False)
    return resp

def extract_body(resp, selectors, remove_selectors=None):
    """通用正文提取"""
    if resp is None:
        return "", 0, []
    for sel in selectors:
        els = resp.css(sel)
        if els:
            el = els[0]
            if remove_selectors:
                for r in remove_selectors:
                    try:
                        el.css(r).remove()
                    except: pass
            text = el.get_all_text(strip=True, separator="\n\n")
            text = re.sub(r'\n{3,}', '\n\n', text).strip()
            if len(text) > 50:
                # 提取图片
                images = []
                for img in el.css("img"):
                    src = img.attrib.get("src", "").strip()
                    alt = img.attrib.get("alt", "")
                    if src:
                        full = src if src.startswith("http") else urljoin(resp.url, src)
                        images.append({"src": full, "alt": alt})
                return text, len(text), images
    return "", 0, []

def save(name, articles):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"cn_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    wb = sum(1 for a in articles if a.get("body_text"))
    print(f"  💾 已保存: {path} ({len(articles)} 条, {wb} 含正文)")

def make_article(title, url, source):
    return {
        "title": title.strip(),
        "url": url,
        "source": source,
        "body_text": "",
        "body_text_length": 0,
        "body_images": [],
        "scraped_at": datetime.now().isoformat(),
    }

# ============================================================
# 站点 1: 轻工业出版社
# ============================================================
def crawl_chlip():
    print(f"\n{'='*50}\n  站点 1: 轻工业出版社 (chlip)\n{'='*50}")
    base = "http://www.chlip.com.cn"
    articles = []

    resp = safe_get(base + "/news/index.php")
    if resp is None or resp.status != 200:
        print("  ❌ 无法访问列表页")
        return articles

    raw_links = resp.css("a[href*='show.php']")
    seen = set()
    for link in raw_links:
        href = link.attrib.get("href", "").strip()
        text = link.get_all_text(strip=True)
        if not href or not text or len(text) < 5:
            continue
        full = urljoin(base, href)
        if full in seen: continue
        seen.add(full)
        articles.append(make_article(text, full, "轻工业出版社"))

    print(f"  列表页: {len(articles)} 篇")
    return _fetch_details(articles, ["#show_left", "#show", "body"],
                           ["script","style","nav",".header","#header","#footer",
                            ".footer","#news_index_right",".bdsharebuttonbox",
                            "#header_nav","#header_logo","#header_search",
                            ".index_title",".black14"])

# ============================================================
# 站点 2: 华师大出版社
# ============================================================
def crawl_ecnupress():
    print(f"\n{'='*50}\n  站点 2: 华师大出版社 (ecnupress)\n{'='*50}")
    base = "https://www.ecnupress.com.cn"
    articles = []

    # 新闻公告页 - 需要从列表页抓取
    list_urls = [
        "/custom/index/nl/1588746689?s=7",
        "/custom/index/nl/1588746689?s=10",
        "/custom/index/nl/1588746689?ls=1&s=7",
    ]

    all_links = {}
    for path in list_urls:
        resp = fetch_ssl_fallback(base + path)
        if resp is None or resp.status != 200:
            continue
        # 找新闻链接 (news_id=)
        for link in resp.css("a[href*='news_id=']"):
            href = link.attrib.get("href", "").strip()
            if not href or 'news_id=' not in href:
                continue
            full = urljoin(base, href)
            # 文本可能在父元素中
            text = link.get_all_text(strip=True)
            if not text or len(text) < 4:
                # 尝试取父 li 中的文本
                parent = link.parent()
                if parent:
                    text = parent.get_all_text(strip=True)
            if text and len(text) > 4 and '查看更多' not in text:
                if full not in all_links:
                    all_links[full] = text
        print(f"  {path}: {len(all_links)} 链接")
        if all_links:
            break

    for url, title in all_links.items():
        articles.append(make_article(title, url, "华师大出版社"))

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details(articles, [".content", ".article", ".maintext",
                                      ".news-content", "#content", "article",
                                      ".custom-section", "main", ".detail"])

# ============================================================
# 站点 3: 中科院心理所 (SSL 降级)
# ============================================================
def crawl_psych_ac():
    print(f"\n{'='*50}\n  站点 3: 中科院心理所 (SSL降级)\n{'='*50}")
    base = "https://www.psych.ac.cn"
    articles = []

    paths = ["/xwzx/", "/xwdt/", "/tzgg/", "/news/", "/"]
    all_urls = {}

    for path in paths:
        resp = fetch_ssl_fallback(base + path)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            text = link.get_all_text(strip=True)
            if not href or not text or len(text) < 6:
                continue
            if href.startswith("#") or href.startswith("javascript"):
                continue
            full = urljoin(base, href)
            if base.replace("https://","http://") in full or base in full:
                # 过滤非文章页面（导航、分类页）
                path_part = full.replace(base, "").replace("http://", "").replace("https://", "")
                # 文章页通常有较深的路径或 .html
                if path_part.count("/") >= 2 and '#' not in full:
                    if full not in all_urls:
                        all_urls[full] = text

        print(f"  {path}: 找到 {len(all_urls)} 个链接")
        break  # 只用一个有效路径

    for url, title in all_urls.items():
        articles.append(make_article(title, url, "中科院心理所"))

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details(articles, [".content", ".article", ".main",
                                      ".TRS_Editor", "#content", "article",
                                      ".Custom_UnionStyle", ".con_text",
                                      ".news_text", "body"],
                           ["script","style","nav",".nav",".header","#header",
                            ".footer","#footer",".sidebar",".banner"])

# ============================================================
# 站点 4: 中国心理学会 (GBK编码)
# ============================================================
def crawl_cpsbeijing():
    print(f"\n{'='*50}\n  站点 4: 中国心理学会 (GBK编码)\n{'='*50}")
    base = "https://www.cpsbeijing.org"
    articles = []

    resp = safe_get(base, verify=False)
    if resp is None or resp.status != 200:
        resp = safe_get(base, verify=True)
    if resp is None or resp.status != 200:
        print("  ❌ 无法访问")
        return articles

    # 尝试用 GBK 解码
    try:
        raw = resp.body
        html = raw.decode("gbk", errors="replace")
    except:
        try:
            html = raw.decode("utf-8", errors="replace")
        except:
            html = str(raw)

    # 用正则提取链接
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1).strip(), re.sub(r'\s+', ' ', m.group(2)).strip()
        if not href or not text or len(text) < 4:
            continue
        if href.startswith("#") or href.startswith("javascript"):
            continue
        full = urljoin(base, href)
        if base in full:
            articles.append(make_article(text, full, "中国心理学会"))

    print(f"  总共: {len(articles)} 个链接")

    # 没有更好的选择器，用 body
    return _fetch_details(articles, ["body"],
                           ["script","style","nav",".header","#header",
                            ".footer","#footer","aside",".sidebar"])

# ============================================================
# 站点 5: 简单心理 (Playwright)
# ============================================================
def crawl_jiandanxinli():
    print(f"\n{'='*50}\n  站点 5: 简单心理 (Playwright)\n{'='*50}")
    articles = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 需要 playwright: pip install playwright")
        return articles

    base = "https://www.jiandanxinli.com"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 尝试 /news 页面
        try:
            page.goto(base + "/news", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  ❌ 加载失败: {e}")
            browser.close()
            return articles

        # 提取文章链接
        articles_data = page.eval_on_selector_all("a[href]", """
            els => els.map(e => ({
                href: e.href,
                text: e.textContent.trim()
            })).filter(x => x.text && x.text.length > 10 && x.href.includes('jiandanxinli.com'))
        """)

        seen = set()
        for a in articles_data:
            href = a['href']
            text = a['text']
            if not href or not text or len(text) < 10:
                continue
            if href in seen:
                continue
            seen.add(href)
            # 排除非文章页面
            if any(k in href for k in ['/user/', '/consultation', '/experts',
                                       '/uni', '/forest', '/hotline',
                                       '/test', '/landings', '/intake',
                                       '/learns', '/psychiatrists']):
                continue
            articles.append(make_article(text[:100], href, "简单心理"))

        print(f"  找到 {len(articles)} 个链接")

        # 提取详情 (用requests模式获取，但简单心理是SPA，可能不行)
        browser.close()

    # 用常规方式提取正文 (可能无法获得正文，但至少保留标题和URL)
    return _fetch_details(articles, ["article", ".content", ".article",
                                      ".post-content", ".entry-content",
                                      "#content", "main", ".detail"])

# ============================================================
# 站点 6: 壹心理 (Playwright)
# ============================================================
def crawl_xinli001():
    print(f"\n{'='*50}\n  站点 6: 壹心理 (Playwright)\n{'='*50}")
    articles = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 需要 playwright")
        return articles

    base = "https://www.xinli001.com"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 访问文章列表页
        try:
            page.goto(base + "/info", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"  ❌ 加载失败: {e}")
            browser.close()
            return articles

        # 提取文章链接
        article_links = page.eval_on_selector_all("a[href*='/info/']", """
            els => els.map(e => ({
                href: e.href,
                text: e.textContent.trim()
            })).filter(x => x.text && x.text.length > 5
                && /\\/info\\/\\d+/.test(x.href)
                && !x.href.includes('tag') && !x.href.includes('theme'))
        """)

        seen = set()
        for a in article_links:
            if a['href'] not in seen:
                seen.add(a['href'])
                articles.append(make_article(a['text'], a['href'], "壹心理"))

        print(f"  找到 {len(articles)} 篇文章")

        # 尝试加载更多页面 (翻页)
        for page_num in range(2, 6):
            try:
                page.goto(f"{base}/info?page={page_num}", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
                more = page.eval_on_selector_all("a[href*='/info/']", """
                    els => els.map(e => ({
                        href: e.href,
                        text: e.textContent.trim()
                    })).filter(x => x.text && x.text.length > 5
                        && /\\/info\\/\\d+/.test(x.href)
                        && !x.href.includes('tag') && !x.href.includes('theme'))
                """)
                new_count = 0
                for a in more:
                    if a['href'] not in seen:
                        seen.add(a['href'])
                        articles.append(make_article(a['text'], a['href'], "壹心理"))
                        new_count += 1
                print(f"  第{page_num}页: +{new_count} 篇")
                if new_count == 0:
                    break
            except:
                break

        browser.close()

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details(articles, ["article", ".content", ".article",
                                      ".detail-content", ".info-content",
                                      ".post-content", "#content", "main",
                                      ".entry-content", ".con_content"])

# ============================================================
# 站点 7: 北师大心理学部
# ============================================================
def crawl_psych_bnu():
    print(f"\n{'='*50}\n  站点 7: 北师大心理学部\n{'='*50}")
    base = "https://psych.bnu.edu.cn"
    articles = []

    news_paths = [
        "/xwzx/xwdt/index.htm",
        "/xwzx/tzgg/index.htm",
        "/xwzx/hdyg/index.htm",
    ]

    all_urls = {}
    for path in news_paths:
        resp = safe_get(base + path)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            text = link.get_all_text(strip=True)
            if not href or not text or len(text) < 6:
                continue
            full = urljoin(base, href)
            # 只取本站 + 有具体文章路径的
            if base in full and full != base + "/" and full != base:
                if any(k in full for k in ['.htm', '.shtml']):
                    if full not in all_urls:
                        all_urls[full] = text
        print(f"  {path}: {len(all_urls)} 链接")

    for url, title in all_urls.items():
        articles.append(make_article(title, url, "北师大心理学部"))

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details(articles, [".content", ".article", ".main",
                                      ".TRS_Editor", "#content", "article",
                                      ".Custom_UnionStyle", ".con_text",
                                      ".v_news_content", "body"],
                           ["script","style","nav",".nav",".header","#header",
                            ".footer","#footer",".sidebar",".banner",
                            ".top",".bottom",".related"])

# ============================================================
# 站点 8: 北大心理学院
# ============================================================
def crawl_psy_pku():
    print(f"\n{'='*50}\n  站点 8: 北大心理学院\n{'='*50}")
    base = "https://www.psy.pku.edu.cn"
    articles = []

    news_paths = [
        "/xwzx/xyxw/index.htm",
        "/xwzx/tzgg/index.htm",
        "/xwzx/xsbg/index.htm",
    ]

    all_urls = {}
    for path in news_paths:
        resp = safe_get(base + path)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            text = link.get_all_text(strip=True)
            if not href or not text or len(text) < 6:
                continue
            full = urljoin(base, href)
            if base in full and full != base + "/" and full != base:
                if '.htm' in full:
                    if full not in all_urls:
                        all_urls[full] = text
        print(f"  {path}: {len(all_urls)} 链接")

    for url, title in all_urls.items():
        articles.append(make_article(title, url, "北大心理学院"))

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details(articles, [".content", ".article", ".main",
                                      ".TRS_Editor", "#content", "article",
                                      ".Custom_UnionStyle", ".con_text",
                                      ".v_news_content", ".detail",
                                      ".entry-content", "body"],
                           ["script","style","nav",".nav",".header","#header",
                            ".footer","#footer",".sidebar",".banner",
                            ".top",".bottom",".related"])

# ============================================================
# 站点 9: 华南师大心理学院
# ============================================================
def crawl_psy_scnu():
    print(f"\n{'='*50}\n  站点 9: 华南师大心理学院\n{'='*50}")
    base = "http://psy.scnu.edu.cn"
    articles = []

    news_paths = [
        "/xinwenzixun/xueyuanxinwen/",
        "/xinwenzixun/tongzhigonggao/",
        "/xinwenzixun/xuegongdongtai/",
    ]

    all_urls = {}
    for path in news_paths:
        resp = safe_get(base + path)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            text = link.get_all_text(strip=True)
            if not href or not text or len(text) < 6:
                continue
            full = urljoin(base, href)
            if base in full:
                if '.html' in full and '查看更多' not in text:
                    if full not in all_urls:
                        all_urls[full] = text
        print(f"  {path}: {len(all_urls)} 链接")

    for url, title in all_urls.items():
        articles.append(make_article(title, url, "华南师大心理学院"))

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details(articles, [".content", ".article", ".main",
                                      "#content", "article",
                                      ".con_text", ".detail",
                                      ".entry-content", ".news-content",
                                      ".show_content", "body"],
                           ["script","style","nav",".nav",".header","#header",
                            ".footer","#footer",".sidebar",".banner",
                            ".top",".bottom",".related"])

# ============================================================
# 详情页批量提取
# ============================================================
def _fetch_details(articles, selectors, remove_selectors=None):
    """批量提取文章详情"""
    total = len(articles)
    for idx, article in enumerate(articles, 1):
        title_short = article['title'][:40]
        print(f"  [{idx}/{total}] {title_short}...", end="", flush=True)

        url = article['url']
        resp = safe_get(url)
        if resp is None or resp.status != 200:
            # 对 HTTPS 站点尝试 SSL 降级
            if url.startswith("https://"):
                resp = fetch_ssl_fallback(url)
            if resp is None or resp.status != 200:
                print(f"\r  [{idx}/{total}] ❌ {title_short}")
                continue

        body_text, body_len, body_images = extract_body(resp, selectors, remove_selectors)
        article['body_text'] = body_text
        article['body_text_length'] = body_len
        article['body_images'] = body_images

        status = "✅"
        if body_text:
            status += f" ({body_len}c"
            status += f",{len(body_images)}img)" if body_images else ")"
        else:
            status += " (no body)"
        print(f"\r  [{idx}/{total}] {status}: {title_short}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    return articles

# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 50)
    print("  中国心理学站点爬虫 v2 (修复版)")
    print(f"  输出: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 50)

    sites = [
        # (key, func, name)
        ("chlip", crawl_chlip, "轻工业出版社"),
        ("ecnupress", crawl_ecnupress, "华师大出版社"),
        ("psych_ac", crawl_psych_ac, "中科院心理所"),
        ("cpsbeijing", crawl_cpsbeijing, "中国心理学会"),
        ("jiandanxinli", crawl_jiandanxinli, "简单心理"),
        ("xinli001", crawl_xinli001, "壹心理"),
        ("psych_bnu", crawl_psych_bnu, "北师大心理学部"),
        ("psy_pku", crawl_psy_pku, "北大心理学院"),
        ("psy_scnu", crawl_psy_scnu, "华南师大心理学院"),
    ]

    results = {}
    start = time.time()

    for key, func, name in sites:
        t0 = time.time()
        try:
            arts = func()
            elapsed = time.time() - t0
            wb = sum(1 for a in arts if a.get("body_text"))
            print(f"\n  ✅ {name}: {len(arts)} 条, {wb} 含正文 ({elapsed:.0f}s)\n")
            results[key] = {"count": len(arts), "with_body": wb, "time": elapsed}
            if arts:
                save(key, arts)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n  ❌ {name} 失败: {e} ({elapsed:.0f}s)")
            import traceback; traceback.print_exc()
            results[key] = {"error": str(e), "time": elapsed}

    # 总结
    total_t = time.time() - start
    print(f"\n{'='*50}")
    print("  爬取完成！总结")
    print(f"{'='*50}")
    total_a = total_b = 0
    for key, func, name in sites:
        r = results.get(key, {})
        if "error" in r:
            print(f"  ❌ {name}: {r['error'][:40]} ({r['time']:.0f}s)")
        else:
            print(f"  ✅ {name}: {r.get('count',0)} 条, {r.get('with_body',0)} 含正文 ({r.get('time',0):.0f}s)")
            total_a += r.get("count", 0)
            total_b += r.get("with_body", 0)
    print(f"\n  总计: {total_a} 条, {total_b} 含正文, 耗时 {total_t:.0f}s")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
