"""
Psychology News 爬虫
"""
import json, os, re, sys, time
from datetime import datetime
from urllib.parse import urlparse
from scrapling.fetchers import DynamicFetcher, Fetcher

PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "psychology_news_org.json")
FETCH_DETAIL = True
DETAIL_DELAY = 0.5
TEMP_FILE = "_pn_links.json"

DynamicFetcher.configure(adaptive=True, huge_tree=True)
Fetcher.configure(adaptive=True, huge_tree=True)


def collect_links():
    print(f"📋 浏览器加载: https://www.psychology-news.org/")

    def extract(page):
        import time, json
        time.sleep(3)

        # 点击 More news 確保各分類也載入
        for i in range(3):
            btns = page.query_selector_all('.sj-more-news, .morenews, .cc-more-news')
            clicked = False
            for btn in btns:
                try:
                    if btn.is_visible():
                        btn.click(); clicked = True; time.sleep(1.5); break
                except: continue
            if not clicked: break

        time.sleep(2)

        result = page.evaluate("""
            () => {
                const seen = new Set();
                const items = [];

                // 1. complete-listing (完整列表)
                document.querySelectorAll('.complete-listing a').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const text = a.textContent.trim();
                    if (text && href.startsWith('http') && !seen.has(href)) {
                        seen.add(href);
                        items.push({ title: text, url: href, source: 'complete' });
                    }
                });

                // 2. 分类 listing 中不在 complete 里的
                document.querySelectorAll('.sj-listing a, .climate-listing a, .other-listing a').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const text = a.textContent.trim();
                    if (text && href.startsWith('http') && !seen.has(href)) {
                        seen.add(href);
                        items.push({ title: text, url: href, source: 'category' });
                    }
                });

                return items;
            }
        """)

        with open(TEMP_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"  收集到 {len(result)} 篇")

    DynamicFetcher.fetch(
        'https://www.psychology-news.org/',
        headless=True, timeout=60000,
        disable_resources=False, network_idle=True, load_dom=True,
        page_action=extract,
    )

    if os.path.exists(TEMP_FILE):
        with open(TEMP_FILE, 'r', encoding='utf-8') as f:
            items = json.load(f)
        os.remove(TEMP_FILE)
        for i in items:
            i["body_text"] = ""
            i["body_text_length"] = 0
            i["body_images"] = []
        return items
    return []


def fetch_article(url: str) -> dict:
    result = {"body_text": "", "body_text_length": 0, "body_images": []}
    try:
        resp = Fetcher.get(url, proxy=PROXY, timeout=30, retries=2)
    except:
        return result
    if resp.status != 200:
        return result

    best_text = ""
    best_len = 0
    for sel in ["article", ".entry-content", ".post-content", ".article-content",
                 ".story-body", ".content", "[itemprop='articleBody']", "main", ".post"]:
        els = resp.css(sel)
        for el in els:
            t = el.get_all_text(strip=True)
            if len(t) > best_len and len(t) < 100000:
                best_text = t; best_len = len(t)

    if best_text:
        result["body_text"] = re.sub(r'\n{3,}', '\n\n', best_text).strip()
        result["body_text_length"] = len(result["body_text"])

    seen = set()
    imgs = []
    for img in resp.css("img[src]"):
        src = img.attrib.get("src", "")
        alt = img.attrib.get("alt", "")
        if src.startswith("http") and "icon" not in src.lower() and "logo" not in src.lower():
            k = src.split("?")[0].rsplit("/", 1)[-1][:60]
            if k not in seen:
                seen.add(k)
                imgs.append({"src": src, "alt": alt or ""})
    result["body_images"] = imgs
    return result


def main():
    print("=" * 55)
    print("  Psychology News (More news + 正文)")
    print("=" * 55)
    t0 = time.time()

    articles = collect_links()
    if not articles:
        print("❌ 无数据"); return
    print(f"📋 共 {len(articles)} 篇")

    if FETCH_DETAIL:
        total = len(articles)
        print(f"\n📖 获取正文 ({total} 篇)...")
        for i, a in enumerate(articles, 1):
            print(f"  [{i}/{total}] {a['title'][:50]}...", end="", flush=True)
            detail = fetch_article(a["url"])
            a.update(detail)
            s = "✅"
            if a["body_text"]:
                s += f" ({a['body_text_length']}c" + (f", {len(a['body_images'])}img)" if a["body_images"] else ")")
            print(f"\r  [{i}/{total}] {s}: {a['title'][:50]}")
            if i < total: time.sleep(DETAIL_DELAY)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {os.path.abspath(OUTPUT_FILE)}")
    wb = sum(1 for a in articles if a.get("body_text"))
    ti = sum(len(a.get("body_images", [])) for a in articles)
    print(f"   文章: {len(articles)}, 含正文: {wb}, 图片: {ti}")
    print(f"⏱ {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
