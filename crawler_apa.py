"""
APA Press Room 爬虫 (含 Load More 翻页)
"""
import json, os, sys, time
from datetime import datetime
from scrapling.fetchers import DynamicFetcher

BASE_URL = "https://www.apa.org/news/press"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "apa_press_releases.json")
FETCH_DETAIL = True

DynamicFetcher.configure(adaptive=True, huge_tree=True)
TEMP = "_apa_tmp.json"


def fetch_all_releases():
    """
    通过浏览器加载页面 + JS 内循环调用 /api/more 获取全部新闻。
    所有 API 调用在浏览器 JS 上下文中完成，复用 Incapsula session。
    """
    print(f"📋 获取全部新闻列表...")

    def collect(page):
        import time, json
        time.sleep(3)

        result = page.evaluate("""
            async () => {
                const seen = new Set();
                const allItems = [];

                // 1. 收集页面已加载的
                document.querySelectorAll('a.module-link').forEach(link => {
                    const href = link.getAttribute('href') || '';
                    if (!href.includes('/news/press/releases/')) return;
                    if (seen.has(href)) return;
                    seen.add(href);
                    allItems.push({
                        title: link.querySelector('.title')?.textContent?.trim() || '',
                        date: link.querySelector('em')?.textContent?.trim() || '',
                        desc: link.querySelector('.wysiwyg')?.textContent?.trim() || '',
                        url: href.startsWith('http') ? href : 'https://www.apa.org' + href,
                    });
                });

                // 2. 从 JS 中读取初始 cursor
                let cursor = 'MTA=';
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const m = s.textContent.match(/cursor\\s*=\\s*'([^']+)'/);
                    if (m) { cursor = m[1]; break; }
                }

                // 3. 循环调用 API
                let pages = 0;
                while (cursor !== '0' && pages < 50) {
                    try {
                        const params = new URLSearchParams({
                            pageId: '21727', entityId: '303002',
                            maxItems: '50', sortBy: 'date desc',
                            cursor: cursor, perPage: '10',
                            entityType: 'DX003', displayImage: '',
                        });
                        const resp = await fetch('/api/more?' + params.toString(), {
                            credentials: 'same-origin',
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        if (!resp.ok) break;
                        const data = await resp.json();
                        cursor = data.cursor || '0';

                        const div = document.createElement('div');
                        div.innerHTML = data.content || '';
                        div.querySelectorAll('a.module-link').forEach(link => {
                            const href = link.getAttribute('href') || '';
                            if (!href.includes('/news/press/releases/')) return;
                            if (seen.has(href)) return;
                            seen.add(href);
                            allItems.push({
                                title: link.querySelector('.title')?.textContent?.trim() || '',
                                date: link.querySelector('em')?.textContent?.trim() || '',
                                desc: link.querySelector('.wysiwyg')?.textContent?.trim() || '',
                                url: href.startsWith('http') ? href : 'https://www.apa.org' + href,
                            });
                        });
                        pages++;
                    } catch(e) { break; }
                }
                return { total: allItems.length, pages, items: allItems };
            }
        """)

        with open(TEMP, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"  {result.get('total', 0)} 篇 (API调了 {result.get('pages', 0)} 次)")

    DynamicFetcher.fetch(BASE_URL, headless=True, timeout=60000,
                         disable_resources=False, network_idle=True,
                         load_dom=True, page_action=collect)

    if os.path.exists(TEMP):
        with open(TEMP, 'r', encoding='utf-8') as f:
            data = json.load(f)
        os.remove(TEMP)
        articles = data.get("items", [])
        for a in articles:
            a.update({"body_text": "", "body_images": []})
        return articles
    return []


def fetch_article(url: str) -> dict:
    """通过浏览器获取单篇正文"""
    result = {"body_text": "", "body_images": []}

    def do(page):
        import time, json
        time.sleep(2)
        data = page.evaluate("""
            () => {
                const clone = document.body.cloneNode(true);
                clone.querySelectorAll('header, footer, nav, .sidebar, .breadcrumbs, ' +
                    'script, style, noscript, iframe, [class*="ad"], [class*="nav"], ' +
                    '[class*="footer"], [class*="sidebar"]').forEach(el => el.remove());
                let best = { text: '', len: 0 };
                clone.querySelectorAll('section, article, div, main').forEach(el => {
                    const t = el.textContent.trim();
                    if (t.length > best.len && t.length < 50000)
                        best = { text: t, len: t.length };
                });
                const imgs = [];
                document.querySelectorAll('[class*="article"] img, article img, .content img').forEach(img => {
                    const src = img.getAttribute('src') || '';
                    if (src && src.startsWith('http') && !src.includes('icon') && !src.includes('logo'))
                        if (!imgs.find(i => i.src === src))
                            imgs.push({ src, alt: img.getAttribute('alt') || '' });
                });
                return { bodyText: best.text, bodyImages: imgs };
            }
        """)
        with open(TEMP, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    try:
        DynamicFetcher.fetch(url, headless=True, timeout=60000,
                             disable_resources=False, network_idle=True,
                             load_dom=True, page_action=do)
        if os.path.exists(TEMP):
            with open(TEMP, 'r', encoding='utf-8') as f:
                data = json.load(f)
            os.remove(TEMP)
            if data:
                result["body_text"] = data.get("bodyText", "")
                result["body_images"] = data.get("bodyImages", [])
    except:
        pass
    return result


def main():
    print("=" * 50)
    print("  APA Press Room (含 Load More)")
    print("=" * 50)

    articles = fetch_all_releases()
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
                s += f" ({len(a['body_text'])}c"
                if a["body_images"]: s += f", {len(a['body_images'])}img"
                s += ")"
            print(f"\r  [{i}/{total}] {s}: {a['title'][:50]}")
            if i < total: time.sleep(2)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    t0 = time.time()
    main()
    print(f"⏱ {time.time()-t0:.0f}s")
