"""
Verywell Mind 主题页面爬虫（含子文章正文）
=========================================
基于 Scrapling 的自适应爬虫
- 提取主题页介绍 + FAQ
- 提取子文章卡片列表
- 逐篇爬取子文章正文 + 正文图片
- 通过代理 (127.0.0.1:7897) 访问
"""

import json
import os
import re
import sys
import time
from datetime import datetime

from scrapling.fetchers import Fetcher

# ============================================================
#  配置区
# ============================================================
TARGET_URL = "https://www.verywellmind.com/therapy-4581775"
PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "verywellmind_therapy.json")
FETCH_DETAIL = True          # 是否爬取子文章正文
DETAIL_DELAY = 1.0           # 详情请求间隔（秒）
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

Fetcher.configure(adaptive=True, huge_tree=True)


# ============================================================
#  第一阶段：主题页（列表）爬取
# ============================================================

def fetch_page(url: str):
    """获取页面内容"""
    print(f"📋 获取主题页: {url}")
    resp = Fetcher.get(url, proxy=PROXY, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
    if resp.status != 200:
        print(f"  ❌ HTTP {resp.status}")
        return None
    print(f"  ✅ {len(resp.body)} bytes")
    return resp


def extract_intro(resp) -> dict:
    """提取页面头部介绍内容"""
    result = {"title": "", "intro_paragraphs": [], "intro_text": ""}

    h1 = resp.css("h1")
    if h1:
        result["title"] = h1[0].get_all_text(strip=True)

    header = resp.css("#mntl-taxonomysc-header_1-0")
    if header:
        intro_div = header[0].css(".mntl-taxonomysc-intro")
        if intro_div:
            ps = intro_div[0].css("p")
            for p in ps:
                txt = p.get_all_text(strip=True)
                if txt:
                    result["intro_paragraphs"].append(txt)
            result["intro_text"] = "\n\n".join(result["intro_paragraphs"])

    return result


def extract_faq(resp) -> list:
    """提取 FAQ 问答对"""
    faqs = []
    faq_content = resp.css("ul.mntl-sc-block-universal-faq__content")
    if not faq_content:
        return faqs
    items = faq_content[0].css("li.accordion__item")
    for item in items:
        q_el = item.css(".accordion__header")
        q_text = q_el[0].get_all_text(strip=True) if q_el else ""
        a_el = item.css(".accordion__body")
        a_text = a_el[0].get_all_text(strip=True, separator="\n") if a_el else ""
        if q_text and a_text:
            faqs.append({"question": q_text, "answer": a_text})
    return faqs


def extract_article_cards(resp) -> list:
    """提取页面中的所有子文章卡片（含图片）"""
    cards = []
    seen_urls = set()

    card_selectors = [
        "article.mntl-document-card",
        ".mntl-document-card",
        ".mntl-universal-card",
        '[class*="mntl-document-card"]',
        '[class*="mntl-card"]',
    ]

    for sel in card_selectors:
        found_cards = resp.css(sel)
        for card in found_cards:
            link = card.css("a")
            if not link:
                continue
            href = link[0].attrib.get("href", "")
            if href in seen_urls or not href.startswith("http"):
                continue

            title = link[0].get_all_text(strip=True) or card.get_all_text(strip=True)[:100]

            images = []
            for img in card.css("img[src]"):
                src = img.attrib.get("src", "")
                alt = img.attrib.get("alt", "")
                if src.startswith("http") and "icon" not in src.lower():
                    images.append({"src": src, "alt": alt or ""})

            card_data = {
                "title": title,
                "url": href,
                "thumbnail": images[0] if images else None,
                # 以下由第二阶段填充
                "body_text": "",
                "body_text_length": 0,
                "body_images": [],
                "author": "",
                "published_date": "",
                "reviewed_by": "",
            }

            if href not in seen_urls:
                seen_urls.add(href)
                cards.append(card_data)

    return cards


# ============================================================
#  第二阶段：文章详情爬取
# ============================================================

def fetch_article_detail(url: str) -> dict:
    """获取单篇文章详情 — 正文、图片、作者、日期"""
    result = {
        "body_text": "",
        "body_text_length": 0,
        "body_images": [],
        "author": "",
        "published_date": "",
        "reviewed_by": "",
    }

    try:
        resp = Fetcher.get(url, proxy=PROXY, timeout=REQUEST_TIMEOUT, retries=REQUEST_RETRIES)
    except Exception as e:
        return result

    if resp.status != 200:
        return result

    # --- 正文 (.mntl-sc-page) ---
    sc_page = resp.css(".mntl-sc-page")
    if sc_page:
        body = sc_page[0].get_all_text(strip=True, separator="\n\n")
        body = re.sub(r'\n{3,}', '\n\n', body).strip()
        result["body_text"] = body
        result["body_text_length"] = len(body)

    # --- 正文图片（article-content 中的 img-placeholder，排除作者头像） ---
    seen_srcs = set()
    for img in resp.css(".loc.article-content img[src]"):
        src = img.attrib.get("src", "")
        alt = img.attrib.get("alt", "")
        if not src.startswith("http") or "icon" in src.lower() or "logo" in src.lower():
            continue
        # 排除 200x200 作者头像
        if "/200x200/" in src or "/200x0/" in src:
            continue
        src_key = src.split("?")[0].rsplit("/", 1)[-1][:80]
        if src_key not in seen_srcs:
            seen_srcs.add(src_key)
            result["body_images"].append({"src": src, "alt": alt or ""})

    # --- 元数据（从 header 提取）---
    header_text = ""
    header = resp.css(".loc.article-header")
    if header:
        header_text = header[0].get_all_text(strip=False)

    if header_text:
        # 作者: "By Name"
        m = re.search(r'By\s+(.+?)(?:\n|$)', header_text)
        if m:
            result["author"] = m.group(1).strip().rstrip(',')

        # 日期: "Updated on Month DD, YYYY" 或 "Updated Month DD, YYYY"
        m = re.search(r'Updated\s+(?:on\s+)?(\w+\s+\d+,\s+\d{4})', header_text)
        if m:
            result["published_date"] = m.group(1)

        # 审阅者: "Medically reviewed by Name" 或 "Reviewed by Name"
        m = re.search(r'(?:Medically\s+)?Reviewed\s+by\s+(.+?)(?:\n|$)', header_text)
        if m:
            result["reviewed_by"] = m.group(1).strip().rstrip(',')

    return result


def enrich_articles(cards: list) -> list:
    """遍历卡片列表，逐篇获取详情"""
    total = len(cards)
    print(f"\n📖 第二阶段：爬取文章正文 ({total} 篇)")
    print(f"   请求间隔: {DETAIL_DELAY}s\n")

    enriched = []
    for idx, card in enumerate(cards, 1):
        url = card["url"]
        print(f"  [{idx}/{total}] {card['title'][:60]}...", end="")

        detail = fetch_article_detail(url)
        card.update(detail)

        status = "✅"
        if card["body_text"]:
            status += f" ({card['body_text_length']} chars"
            if card["body_images"]:
                status += f", {len(card['body_images'])} img"
            status += ")"
        print(f"\r  [{idx}/{total}] {status}: {card['title'][:60]}")

        enriched.append(card)
        if idx < total:
            time.sleep(DETAIL_DELAY)

    return enriched


# ============================================================
#  入口
# ============================================================

def crawl_page(url: str) -> dict:
    """完整爬取流程"""
    resp = fetch_page(url)
    if not resp:
        return {}

    print("\n📝 提取主题页内容...")

    intro = extract_intro(resp)
    print(f"  标题: {intro['title']}")
    print(f"  介绍段落: {len(intro['intro_paragraphs'])}")

    faqs = extract_faq(resp)
    print(f"  FAQ 问答: {len(faqs)}")

    cards = extract_article_cards(resp)
    print(f"  子文章卡片: {len(cards)}")

    # 第二阶段：爬正文
    if FETCH_DETAIL and cards:
        cards = enrich_articles(cards)

    result = {
        "url": url,
        "title": intro["title"],
        "intro_text": intro["intro_text"],
        "intro_paragraphs": intro["intro_paragraphs"],
        "faq": faqs,
        "article_cards": cards,
        "article_card_count": len(cards),
        "faq_count": len(faqs),
        "scraped_at": datetime.now().isoformat(),
    }

    return result


def save_result(data: dict):
    """保存结果"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    summary_file = os.path.join(OUTPUT_DIR, "verywellmind_therapy_summary.md")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"# Verywell Mind - {data['title']}\n\n")
        f.write(f"- **URL**: {data['url']}\n")
        f.write(f"- **爬取时间**: {data['scraped_at']}\n")
        f.write(f"- **介绍段落**: {len(data['intro_paragraphs'])}\n")
        f.write(f"- **FAQ Q&A**: {data['faq_count']}\n")
        f.write(f"- **子文章**: {data['article_card_count']}\n")

        with_body = sum(1 for c in data.get("article_cards", []) if c.get("body_text"))
        total_imgs = sum(len(c.get("body_images", [])) for c in data.get("article_cards", []))
        f.write(f"- **含正文**: {with_body} 篇\n")
        f.write(f"- **正文图片**: {total_imgs} 张\n\n")

        if data["intro_paragraphs"]:
            f.write("## 介绍\n\n")
            for p in data["intro_paragraphs"]:
                f.write(f"{p}\n\n")

        if data["faq"]:
            f.write("## FAQ\n\n")
            for faq in data["faq"]:
                f.write(f"### {faq['question']}\n\n{faq['answer']}\n\n")

        if data["article_cards"]:
            f.write("## 子文章\n\n")
            f.write("| # | 标题 | 作者 | 日期 | 正文长度 | 图片 |\n")
            f.write("|---|------|------|------|----------|------|\n")
            for i, c in enumerate(data["article_cards"], 1):
                bl = c.get("body_text_length", 0) or "-"
                ic = len(c.get("body_images", []))
                f.write(f"| {i} | [{c['title'][:45]}]({c['url']}) | {c.get('author', '')[:18]} | {c.get('published_date', '')} | {bl} | {ic} |\n")

    print(f"\n💾 数据已保存: {os.path.abspath(OUTPUT_FILE)}")
    print(f"💾 摘要已保存: {os.path.abspath(summary_file)}")
    print(f"   文章总数: {data['article_card_count']}")
    print(f"   含正文: {with_body} 篇")


def main():
    print("=" * 60)
    print("  Verywell Mind 爬虫（含正文）")
    print("  引擎: Scrapling (自适应模式)")
    print("=" * 60)
    print()

    start_time = time.time()

    try:
        result = crawl_page(TARGET_URL)
        if result and result.get("article_cards"):
            save_result(result)
        else:
            print("⚠️ 爬取失败")
            sys.exit(1)

        elapsed = time.time() - start_time
        print(f"\n🎉 完成！耗时 {elapsed:.1f} 秒")

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
