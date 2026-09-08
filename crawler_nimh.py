"""
NIMH Science Updates 爬虫
==========================
通过年份和主题分类获取所有文章 + 正文 + 图片
"""
import json, os, re, sys, time
from datetime import datetime
from urllib.parse import urljoin
from scrapling.fetchers import Fetcher

PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "nimh_science_updates.json")
FETCH_DETAIL = True
DETAIL_DELAY = 0.5

BASE = "https://www.nimh.nih.gov"
LIST_URL = "https://www.nimh.nih.gov/news/science-updates"

Fetcher.configure(adaptive=True, huge_tree=True)

# 所有年份和主题
YEARS = ["", "2025", "2024", "2023"]  # "" = 当前（2026）
TOPICS = [
    "anxiety-disorders", "attention-deficit-hyperactivity-disorder-adhd",
    "autism-spectrum-disorder-asd", "bipolar-disorder", "covid-19",
    "depression", "disruptive-mood-dysregulation-disorder-dmdd",
    "eating-disorders", "hiv-aids", "obsessive-compulsive-disorder-ocd",
    "post-traumatic-stress-disorder-ptsd", "psychosis", "schizophrenia",
    "stress", "substance-use", "suicide", "traumatic-events",
]


def fetch_list(url: str, label: str) -> list:
    """获取单页文章列表"""
    try:
        resp = Fetcher.get(url, proxy=PROXY, timeout=30, retries=3)
    except:
        return []
    if resp.status != 200:
        return []

    articles = []
    # 文章在 DT.aggregated_news_term 中
    items = resp.css("dt.aggregated_news_term")
    for item in items:
        link = item.css("a[href]")
        if not link:
            continue
        href = link[0].attrib.get("href", "")
        title = link[0].get_all_text(strip=True)
        if not title or not href:
            continue
        if href.startswith("/"):
            href = urljoin(BASE, href)

        articles.append({
            "title": title,
            "url": href,
            "source": label,
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "published_date": "",
            "article_type": "",
        })

    return articles


def collect_all_articles() -> list:
    """收集所有来源的文章"""
    all_articles = []

    # 1. 年份
    print("📋 年份:")
    for year in YEARS:
        url = LIST_URL if not year else f"{LIST_URL}/{year}"
        label = "2026" if not year else year
        arts = fetch_list(url, f"year:{label}")
        print(f"   {label}: {len(arts)} 篇")
        all_articles.extend(arts)

    # 2. 主题
    print("\n📋 主题:")
    for topic in TOPICS:
        url = f"{LIST_URL}/{topic}"
        label = topic.replace("-", " ").title()
        arts = fetch_list(url, f"topic:{topic}")
        if arts:
            print(f"   {label}: {len(arts)} 篇")
            all_articles.extend(arts)

    # 去重
    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    print(f"\n📊 总计: {len(all_articles)} 条, 去重后: {len(unique)} 条")
    return unique


def fetch_article(url: str) -> dict:
    """获取正文和图片"""
    result = {"body_text": "", "body_text_length": 0, "body_images": [],
              "published_date": "", "article_type": ""}

    try:
        resp = Fetcher.get(url, proxy=PROXY, timeout=30, retries=3)
    except:
        return result
    if resp.status != 200:
        return result

    article = resp.css("article")
    if not article:
        return result

    # 日期和类型
    pagestamp = article[0].css("p.pagestamp_news_wrap")
    if pagestamp:
        txt = pagestamp[0].get_all_text(strip=True)
        parts = txt.split("•")
        if parts:
            result["published_date"] = parts[0].strip()
        if len(parts) > 1:
            result["article_type"] = parts[1].strip()

    # 正文: article 的 h2, p, ul 子元素（跳过前3个: div, titleblock, pagestamp）
    body_parts = []
    children = article[0].xpath("./*")
    for child in children[3:]:
        tag = child.tag
        txt = child.get_all_text(strip=True)
        if not txt:
            continue
        # 跳过 references 和 grants 部分
        if tag == "h2" and txt.lower() in ("references", "nih grants"):
            break
        if tag == "h2":
            body_parts.append(f"\n## {txt}\n")
        elif tag == "p":
            body_parts.append(txt)
        elif tag == "ul":
            for li in child.css("li"):
                lt = li.get_all_text(strip=True)
                if lt:
                    body_parts.append(f"  • {lt}")
        elif tag in ("h3", "h4"):
            body_parts.append(f"\n### {txt}\n")

    result["body_text"] = "\n\n".join(body_parts)
    result["body_text_length"] = len(result["body_text"])

    # 图片（article 内非 icon/logo 的图片）
    seen = set()
    imgs = []
    for img in article[0].css("img[src]"):
        src = img.attrib.get("src", "")
        alt = img.attrib.get("alt", "")
        if not src.startswith("http") or "icon" in src.lower() or "logo" in src.lower():
            continue
        key = src.split("?")[0].rsplit("/", 1)[-1][:60]
        if key not in seen:
            seen.add(key)
            imgs.append({"src": src, "alt": alt or ""})
    result["body_images"] = imgs

    return result


def enrich(articles: list) -> list:
    total = len(articles)
    print(f"\n📖 获取正文 ({total} 篇)...")
    enriched = []
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:55]}...", end="", flush=True)
        detail = fetch_article(a["url"])
        a.update(detail)
        s = "✅"
        if a["body_text"]:
            s += f" ({a['body_text_length']}c"
            if a["body_images"]: s += f", {len(a['body_images'])}img"
            s += ")"
        print(f"\r  [{i}/{total}] {s}: {a['title'][:55]}")
        enriched.append(a)
        if i < total: time.sleep(DETAIL_DELAY)
    return enriched


def save(articles: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {os.path.abspath(OUTPUT_FILE)}")
    wb = sum(1 for a in articles if a.get("body_text"))
    ti = sum(len(a.get("body_images", [])) for a in articles)
    print(f"   文章: {len(articles)}, 含正文: {wb}, 图片: {ti}")


def main():
    print("=" * 55)
    print("  NIMH Science Updates")
    print("=" * 55)
    t0 = time.time()

    articles = collect_all_articles()
    if not articles:
        print("❌ 无数据"); return

    if FETCH_DETAIL:
        articles = enrich(articles)

    save(articles)
    print(f"⏱ {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
