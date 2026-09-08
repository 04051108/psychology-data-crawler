"""
中国心理学站点爬虫 v3 (精准修复版)
===========================
针对已知问题做精准修复，不重复已成功的爬取。
"""
import json, os, re, sys, time, ssl
from datetime import datetime
from urllib.parse import urljoin
import urllib.request

from scrapling.fetchers import Fetcher
Fetcher.configure(adaptive=True, huge_tree=True)

OUTPUT_DIR = "output"
DETAIL_DELAY = 0.3

def save(name, articles):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"cn_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    wb = sum(1 for a in articles if a.get("body_text"))
    ti = sum(len(a.get("body_images", [])) for a in articles)
    print(f"  💾 {path} ({len(articles)}条, {wb}含正文, {ti}张图)")

def make_article(title, url, source):
    return {"title": title.strip(), "url": url, "source": source,
            "body_text": "", "body_text_length": 0, "body_images": [],
            "scraped_at": datetime.now().isoformat()}

# ================================================================
# 修复1: 壹心理 - 用 Playwright 提取正文
# ================================================================
def fix_xinli001():
    print(f"\n{'='*50}")
    print("  修复: 壹心理正文提取 (Playwright)")
    print(f"{'='*50}")

    # 读取已有数据（只有标题和URL）
    input_path = os.path.join(OUTPUT_DIR, "cn_xinli001.json")
    if not os.path.exists(input_path):
        print("  ❌ 找不到 cn_xinli001.json")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"  加载 {len(articles)} 篇文章，将用 Playwright 提取正文")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ❌ 需要 playwright")
        return

    success = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        for idx, article in enumerate(articles, 1):
            title_short = article["title"][:40]
            print(f"  [{idx}/{len(articles)}] {title_short}...", end="", flush=True)

            try:
                page = context.new_page()
                page.goto(article["url"], wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                # 提取正文 - 使用 JS 提取主体内容并清理导航
                body_text = page.evaluate("""() => {
                    // 尝试常见正文容器
                    const selectors = ['.yxl-editor', '.article-body-m', '.article-content-m',
                        '.yxl-editor-article', '.main-left-container', '.detail-article',
                        '.article-detail', '.rich-content', '.content-article'];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) return el.innerText;
                    }
                    // 全文降级：移除 header/footer/nav/sidebar 后取 body
                    const body = document.body.cloneNode(true);
                    for (const sel of ['header', 'footer', 'nav', '.header', '.footer', '.nav',
                            '.sidebar', '.recommend', '.comment', '.related',
                            'script', 'style', '.letter-modal', '.footer-PC']) {
                        body.querySelectorAll(sel).forEach(el => el.remove());
                    }
                    return body.innerText;
                }""")

                if body_text and len(body_text.strip()) > 50:
                    body_text = re.sub(r'\n{4,}', '\n\n', body_text.strip())
                    article["body_text"] = body_text
                    article["body_text_length"] = len(body_text)

                    # 提取图片
                    try:
                        imgs = page.evaluate("""() => {
                            const container = document.querySelector('.yxl-editor, .article-body-m, .article-content-m');
                            if (!container) return [];
                            return Array.from(container.querySelectorAll('img')).filter(x => x.src && !x.src.includes('data:')).map(e => ({src: e.src, alt: e.alt || ''}));
                        }""")
                        article["body_images"] = imgs or []
                    except:
                        pass

                    success += 1
                    print(f"\r  [{idx}/{len(articles)}] ✅ ({article['body_text_length']}c, {len(article['body_images'])}img): {title_short}")
                else:
                    print(f"\r  [{idx}/{len(articles)}] ❌ (no body): {title_short}")

                page.close()

            except Exception as e:
                print(f"\r  [{idx}/{len(articles)}] ❌ {e}: {title_short}")

            if idx < len(articles):
                time.sleep(DETAIL_DELAY)

        browser.close()

    print(f"\n  完成: {success}/{len(articles)} 篇成功提取正文")
    save("xinli001", articles)

# ================================================================
# 修复2: 中科院心理所 - 用 urllib 绕过 SSL
# ================================================================
def fix_psych_ac():
    print(f"\n{'='*50}")
    print("  修复: 中科院心理所 SSL (urllib)")
    print(f"{'='*50}")

    base = "https://www.psych.ac.cn"
    articles = []

    # 创建不验证证书的 SSL 上下文
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def ssl_fetch(url):
        try:
            return urllib.request.urlopen(url, context=ctx, timeout=15)
        except Exception as e:
            return None

    def ssl_fetch_text(url):
        resp = ssl_fetch(url)
        if resp:
            try:
                return resp.read().decode("utf-8", errors="replace")
            except:
                return None
        return None

    # 先取首页获取新闻链接
    html = ssl_fetch_text(base)
    if not html:
        print("  ❌ 无法访问首页")
        return

    # 找新闻路径
    news_paths = set()
    for m in re.finditer(r'href=["\']([^"\']*?(?:xwzx|xwdt|tzgg|news)[^"\']*)["\']', html, re.I):
        path = m.group(1)
        if not path.startswith("http"):
            path = urljoin(base, path)
        if base.replace("https://", "http://") in path or base in path:
            news_paths.add(path)

    # 也尝试已知路径
    for p in ["/xwzx/", "/xwdt/", "/tzgg/", "/news/"]:
        news_paths.add(base + p)

    print(f"  发现 {len(news_paths)} 个新闻路径")

    # 从新闻路径提取文章链接
    all_links = {}
    for np in list(news_paths)[:5]:
        html = ssl_fetch_text(np)
        if not html:
            continue
        for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
            href, text = m.group(1).strip(), re.sub(r'\s+', ' ', m.group(2)).strip()
            if not href or not text or len(text) < 6:
                continue
            if href.startswith("#") or href.startswith("javascript"):
                continue
            full = urljoin(base, href)
            if (base.replace("https://","http://") in full or base in full) and full != base + "/":
                if full not in all_links:
                    all_links[full] = text
        print(f"  {np}: {len(all_links)} 链接")

    for url, title in all_links.items():
        articles.append(make_article(title, url, "中科院心理所"))

    print(f"  总计: {len(articles)} 篇")

    # 提取详情 (使用 urllib SSL bypass)
    total = len(articles)
    for idx, article in enumerate(articles, 1):
        title_short = article["title"][:40]
        print(f"  [{idx}/{total}] {title_short}...", end="", flush=True)

        html = ssl_fetch_text(article["url"])
        if not html:
            print(f"\r  [{idx}/{total}] ❌: {title_short}")
            continue

        # 用 regex 提取正文 (不需要解析器)
        # 找常见正文容器
        for pattern in [
            r'<div[^>]*class=["\'](?:content|article|main|TRS_Editor|con_text|news_text)["\'][^>]*>(.*?)</div>',
            r'<article[^>]*>(.*?)</article>',
            r'<div[^>]*id=["\'](?:content|zoom|main|article)["\'][^>]*>(.*?)</div>',
        ]:
            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m:
                body_html = m.group(1)
                body_text = re.sub(r'<[^>]+>', ' ', body_html)
                body_text = re.sub(r'<script[^>]*>.*?</script>', '', body_text, flags=re.DOTALL)
                body_text = re.sub(r'<style[^>]*>.*?</style>', '', body_text, flags=re.DOTALL)
                body_text = re.sub(r'\s+', ' ', body_text).strip()
                body_text = re.sub(r'\n{3,}', '\n\n', body_text)
                if len(body_text) > 50:
                    article["body_text"] = body_text
                    article["body_text_length"] = len(body_text)
                    break

        if article["body_text"]:
            print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']}c): {title_short}")
        else:
            print(f"\r  [{idx}/{total}] ❌ (no body): {title_short}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save("psych_ac", articles)

# ================================================================
# 修复3: 华师大出版社 - 修复链接提取
# ================================================================
def fix_ecnupress():
    print(f"\n{'='*50}")
    print("  修复: 华师大出版社链接提取")
    print(f"{'='*50}")

    base = "https://www.ecnupress.com.cn"
    articles = []
    all_links = {}

    # 从 about 页面获取新闻列表 (s=7 是 "关于我们" 的子页面)
    list_paths = [
        "/custom/index/nl/1588746689?s=7",
        "/custom/index/nl/1588746689?s=10",
    ]

    for path in list_paths:
        try:
            resp = Fetcher.get(base + path, timeout=15, retries=2, follow_redirects=True)
        except:
            continue
        if resp is None or resp.status != 200:
            continue

        html = resp.body.decode("utf-8", errors="replace")

        # 用正则找所有包含 news_id= 的链接
        for m in re.finditer(r'<a[^>]*href=["\']([^"\']*news_id=(\d+)[^"\']*)["\'][^>]*>', html):
            href = m.group(1).strip()
            full = urljoin(base, href)
            if full in all_links:
                continue

            # 找标题文本 - 可能在 <a> 的父元素中
            start = max(0, m.start() - 500)
            snippet = html[start:m.end()]
            # 尝试在附近找文本
            title = ""
            title_m = re.search(r'>([^<]{10,120})<', snippet)
            if title_m:
                t = re.sub(r'\s+', ' ', title_m.group(1)).strip()
                if len(t) > 8:
                    title = t

            if title:
                all_links[full] = title

        print(f"  {path}: 找到 {len(all_links)} 个链接")

    # 也尝试从 sitemap 找
    for link_href, title in all_links.items():
        articles.append(make_article(title, link_href, "华师大出版社"))

    print(f"  总计: {len(articles)} 篇")
    return _fetch_details_urllib(articles)

# ================================================================
# 修复4: 中国心理学会 - 用 requests 处理 GBK 编码
# ================================================================
def fix_cpsbeijing():
    print(f"\n{'='*50}")
    print("  修复: 中国心理学会 (GBK编码)")
    print(f"{'='*50}")

    base = "https://www.cpsbeijing.org"
    articles = []

    try:
        import urllib.request
        resp = urllib.request.urlopen(base, timeout=15)
        raw = resp.read()
        # 尝试 GBK 解码
        try:
            html = raw.decode("gbk")
        except:
            html = raw.decode("gb2312", errors="replace")
    except Exception as e:
        # 尝试使用 Fetcher
        try:
            resp2 = Fetcher.get(base, timeout=15, verify=False)
            if resp2 and resp2.status == 200:
                raw = resp2.body
                try:
                    html = raw.decode("gbk")
                except:
                    html = raw.decode("utf-8", errors="replace")
            else:
                print(f"  ❌ {e}")
                return
        except:
            print(f"  ❌ {e}")
            return

    print(f"  HTML 大小: {len(html)} 字节")

    # 提取所有链接
    for m in re.finditer(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        href, text = m.group(1).strip(), re.sub(r'\s+', ' ', m.group(2)).strip()
        if not href or not text or len(text) < 4:
            continue
        if href.startswith("#") or href.startswith("javascript"):
            continue
        full = urljoin(base, href)
        if "cpsbeijing" in full:
            articles.append(make_article(text, full, "中国心理学会"))

    print(f"  找到 {len(articles)} 个链接")
    return _fetch_details_urllib(articles)

# ================================================================
# 通用: 用 urllib 提取详情
# ================================================================
def _fetch_details_urllib(articles, selectors=None):
    """用 urllib 方式提取文章正文（无 SSL 限制）"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    total = len(articles)
    for idx, article in enumerate(articles, 1):
        title_short = article["title"][:40]
        print(f"  [{idx}/{total}] {title_short}...", end="", flush=True)

        try:
            resp = urllib.request.urlopen(article["url"], context=ctx, timeout=15)
            html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            # 尝试 Scrapling
            try:
                resp2 = Fetcher.get(article["url"], timeout=15, verify=False)
                if resp2 and resp2.status == 200:
                    html = resp2.body.decode("utf-8", errors="replace")
                else:
                    print(f"\r  [{idx}/{total}] ❌ {e}: {title_short}")
                    continue
            except:
                print(f"\r  [{idx}/{total}] ❌ {e}: {title_short}")
                continue

        # 通用正文提取
        body_text = ""
        for sel in ["article", ".content", ".article", ".main", ".TRS_Editor",
                     ".Custom_UnionStyle", ".con_text", ".news_text",
                     ".entry-content", ".post-content", ".detail",
                     ".show_content", "#content", "#zoom"]:
            sel_css = sel.replace(".", "").replace("#", "")
            if sel.startswith("."):
                pattern = rf'<div[^>]*class=["\'][^"\']*{re.escape(sel_css)}[^"\']*["\'][^>]*>(.*?)</div>'
            elif sel.startswith("#"):
                pattern = rf'<div[^>]*id=["\']{re.escape(sel_css)}["\'][^>]*>(.*?)</div>'
            elif sel == "article":
                pattern = r'<article[^>]*>(.*?)</article>'
            else:
                continue

            m = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
            if m:
                body_html = m.group(1)
                body_text = re.sub(r'<[^>]+>', ' ', body_html)
                body_text = re.sub(r'<script[^>]*>.*?</script>', '', body_text, flags=re.DOTALL)
                body_text = re.sub(r'<style[^>]*>.*?</style>', '', body_text, flags=re.DOTALL)
                body_text = re.sub(r'\s+', ' ', body_text).strip()
                if len(body_text) > 50:
                    break

        # fallback: 取 body 文本
        if not body_text or len(body_text) < 50:
            body_text = re.sub(r'<[^>]+>', ' ', html)
            body_text = re.sub(r'\s+', ' ', body_text).strip()

        article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_text).strip()
        article["body_text_length"] = len(article["body_text"])

        if article["body_text_length"] > 50:
            print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']}c): {title_short}")
        else:
            print(f"\r  [{idx}/{total}] ⚠️ (short {article['body_text_length']}c): {title_short}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    return articles

# ================================================================
# 主流程
# ================================================================
def main():
    print("=" * 50)
    print("  中国心理学站点爬虫 v3 (精准修复)")
    print("=" * 50)

    # 只修复有问题的站点
    fixes = [
        ("壹心理正文提取", fix_xinli001),
        ("中科院心理所SSL", fix_psych_ac),
        ("华师大出版社", fix_ecnupress),
        ("中国心理学会", fix_cpsbeijing),
    ]

    results = {}
    start = time.time()

    for name, func in fixes:
        t0 = time.time()
        try:
            func()
            elapsed = time.time() - t0
            print(f"  ⏱ {elapsed:.0f}s")
        except KeyboardInterrupt:
            print("\n  用户中断")
            break
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ❌ {name}: {e} ({elapsed:.0f}s)")
            import traceback; traceback.print_exc()

    total_t = time.time() - start
    print(f"\n{'='*50}")
    print(f"  修复完成! 总耗时 {total_t:.0f}s")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
