"""
Psychological Science 最新研究爬虫
"""
import json, os, re, sys, time
from datetime import datetime
from urllib.parse import urljoin
from scrapling.fetchers import Fetcher

BASE_URL = "https://www.psychologicalscience.org/latest-research"
PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "psychological_science_news.json")
MAX_PAGES = 3               # 每页100条，3页=300条
FETCH_DETAIL = True
DETAIL_DELAY = 0.5

Fetcher.configure(adaptive=True, huge_tree=True)


# ============================================================
#  第一阶段：列表页
# ============================================================

def fetch_list_page(url: str) -> list:
    """获取单页列表"""
    print(f"  [列表] {url}")
    resp = Fetcher.get(url, proxy=PROXY, timeout=30, retries=3)
    if resp.status != 200:
        print(f"    ❌ HTTP {resp.status}")
        return []

    items = resp.css(".article-list.wrap li")
    articles = []
    for item in items:
        a = parse_list_item(item)
        if a:
            articles.append(a)
    return articles


def parse_list_item(item) -> dict | None:
    """解析列表中的一篇文章"""
    link_el = item.css("article > a[href]")
    if not link_el:
        return None
    href = link_el[0].attrib.get("href", "")

    # h3 标题
    h3 = item.css("h3")
    title = h3[0].get_all_text(strip=True) if h3 else ""

    # 摘要 p
    desc = ""
    ps = item.css("p")
    if ps:
        desc = ps[0].get_all_text(strip=True)

    # 缩略图
    img_src = ""
    img_alt = ""
    imgs = item.css("img")
    for img in imgs:
        src = img.attrib.get("src", "")
        if src and "logo" not in src.lower() and "icon" not in src.lower():
            img_src = src
            img_alt = img.attrib.get("alt", "")
            break

    # 分类
    article_el = item.css("article")
    article_class = article_el[0].attrib.get("class", "") if article_el else ""
    category = ""
    for cat in ["releases", "news", "observer", "feature"]:
        if f"category-{cat}" in article_class:
            category = cat
            break

    # 完整 URL
    if href.startswith("/"):
        href = urljoin("https://www.psychologicalscience.org", href)

    return {
        "title": title,
        "url": href,
        "summary": desc,
        "category": category,
        "image_url": img_src,
        "image_alt": img_alt,
        "body_text": "",
        "body_text_length": 0,
        "body_images": [],
        "author": "",
        "published_date": "",
    }


def crawl_all_lists(max_pages: int = MAX_PAGES) -> list:
    """爬取所有列表页"""
    print(f"📋 第一阶段：爬取列表 (最多 {max_pages} 页)")

    all_articles = []

    for page in range(1, max_pages + 1):
        url = BASE_URL if page == 1 else f"{BASE_URL}/page/{page}/"
        articles = fetch_list_page(url)
        if not articles:
            print(f"  [第{page}页] 无内容，停止")
            break
        all_articles.extend(articles)
        print(f"   ✔ 累计: {len(all_articles)} 条")
        if page < max_pages:
            time.sleep(0.5)

    # 去重
    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    print(f"  去重后: {len(unique)} 条")
    return unique


# ============================================================
#  第二阶段：文章详情
# ============================================================

def fetch_article_detail(url: str) -> dict:
    """获取正文和图片"""
    result = {"body_text": "", "body_text_length": 0, "body_images": [], "author": "", "published_date": ""}

    try:
        resp = Fetcher.get(url, proxy=PROXY, timeout=30, retries=3)
    except:
        return result
    if resp.status != 200:
        return result

    # 正文 (.main-content 或 article)
    content = resp.css(".main-content") or resp.css("article.post")
    if content:
        body = content[0].get_all_text(strip=True, separator="\n\n")
        body = re.sub(r'\n{3,}', '\n\n', body).strip()
        result["body_text"] = body
        result["body_text_length"] = len(body)

        # 图片（正文内的）
        seen = set()
        imgs = []
        for img in content[0].css("img[src]"):
            src = img.attrib.get("src", "")
            alt = img.attrib.get("alt", "")
            if src.startswith("http") and "logo" not in src.lower() and "icon" not in src.lower():
                key = src.split("?")[0].rsplit("/", 1)[-1][:60]
                if key not in seen:
                    seen.add(key)
                    imgs.append({"src": src, "alt": alt or ""})
        result["body_images"] = imgs

    # 日期
    for sel in ["time", ".date", '[class*="date"]', ".entry-date"]:
        el = resp.css(sel)
        if el:
            dt = el[0].attrib.get("datetime", "") or el[0].get_all_text(strip=True)
            if dt:
                result["published_date"] = dt.strip()
                break

    return result


def enrich_articles(articles: list) -> list:
    """逐篇获取正文"""
    total = len(articles)
    print(f"\n📖 第二阶段：获取正文 ({total} 篇)")

    enriched = []
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:55]}...", end="", flush=True)
        detail = fetch_article_detail(a["url"])
        a.update(detail)
        s = "✅"
        if a["body_text"]:
            s += f" ({a['body_text_length']}c"
            if a["body_images"]: s += f", {len(a['body_images'])}img"
            s += ")"
        print(f"\r  [{i}/{total}] {s}: {a['title'][:55]}")
        enriched.append(a)
        if i < total:
            time.sleep(DETAIL_DELAY)

    return enriched


# ============================================================
#  保存
# ============================================================

def save(articles: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {os.path.abspath(OUTPUT_FILE)}")
    with_body = sum(1 for a in articles if a.get("body_text"))
    total_imgs = sum(len(a.get("body_images", [])) for a in articles)
    print(f"   文章: {len(articles)}, 含正文: {with_body}, 图片: {total_imgs}")


# ============================================================
#  Main
# ============================================================

def main():
    print("=" * 55)
    print("  Psychological Science 最新研究")
    print("=" * 55)
    t0 = time.time()

    articles = crawl_all_lists(max_pages=MAX_PAGES)
    if not articles:
        print("❌ 无数据"); return

    if FETCH_DETAIL:
        articles = enrich_articles(articles)

    save(articles)
    print(f"⏱ {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
