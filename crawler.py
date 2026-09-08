"""
Psychology Today News Crawler
==============================
基于 Scrapling 的自适应爬虫
- 自动适应网站结构变化（自愈选择器）
- 通过代理 (127.0.0.1:7897) 访问
- 支持多页爬取列表 + 文章正文详情
- 数据输出为 JSON
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

from scrapling.fetchers import Fetcher

# ============================================================
#  配置区
# ============================================================
BASE_URL = "https://www.psychologytoday.com/us/news"
PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "psychology_today_news.json")
MAX_PAGES = 5               # 最大爬取页数，None 表示不限
FETCH_DETAIL = True         # 是否爬取文章正文
DETAIL_DELAY = 1.0          # 详情页请求间隔（秒），避免被 ban
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

# 自适应配置：开启后 Scrapling 会在网站改版时自动重定位选择器
Fetcher.configure(
    adaptive=True,
    huge_tree=True,
)


# ============================================================
#  第一阶段：列表页爬取
# ============================================================

def fetch_page(url: str, page_num: int = 1) -> tuple:
    """获取单页内容并解析文章列表。返回 (articles, has_next)"""
    full_url = url if page_num == 1 else f"{url}?page={page_num}"
    print(f"  [列表 第{page_num}页] 正在获取: {full_url}")

    resp = Fetcher.get(
        full_url,
        proxy=PROXY,
        timeout=REQUEST_TIMEOUT,
        retries=REQUEST_RETRIES,
    )

    if resp.status != 200:
        print(f"  [列表 第{page_num}页] HTTP {resp.status}，跳过")
        return [], None

    article_cards = resp.css("article.teaser")
    print(f"  [列表 第{page_num}页] 找到 {len(article_cards)} 篇文章卡片")

    articles_data = []
    for card in article_cards:
        article = parse_article_card(card)
        if article:
            articles_data.append(article)

    # 检查是否有下一页
    next_link = resp.css("a.page-link.next")
    has_next = len(next_link) > 0

    return articles_data, has_next


def parse_article_card(card) -> dict | None:
    """解析单篇文章卡片，返回结构化数据字典"""
    links = card.css("a[href]")

    if not links:
        return None

    # --- 智能识别各链接的角色 ---
    title_link = None
    category_link = None
    author_link = None
    blog_link = None

    for lnk in links:
        href = lnk.attrib.get("href", "")
        # 文章正文链接（路径包含 /us/blog/ + 至少5段 = 有日期）
        if href.startswith("/us/blog/") and not href.startswith("/us/blog/trending"):
            if len(href.split("/")) >= 5:
                title_link = lnk
        # 基础分类
        elif href.startswith("/us/basics/"):
            category_link = lnk
        # 贡献者
        elif href.startswith("/us/contributors/"):
            author_link = lnk

    # fallback: 找不到 title_link 时用排除法
    if not title_link:
        for lnk in links:
            href = lnk.attrib.get("href", "")
            if (href.startswith("/us/blog/") or href.startswith("/")) and not href.startswith("#"):
                if not href.startswith("/us/basics/") and not href.startswith("/us/contributors/"):
                    title_link = lnk

    # --- 提取字段 ---
    title = title_link.get_all_text(strip=True) if title_link else ""

    url = ""
    if title_link:
        url = urljoin("https://www.psychologytoday.com", title_link.attrib.get("href", ""))

    category_name = category_link.get_all_text(strip=True) if category_link else ""
    category_url = ""
    if category_link:
        category_url = urljoin("https://www.psychologytoday.com", category_link.attrib.get("href", ""))

    author_name = author_link.get_all_text(strip=True) if author_link else ""
    author_url = ""
    if author_link:
        author_url = urljoin("https://www.psychologytoday.com", author_link.attrib.get("href", ""))

    # 博客名称：找 /us/blog/xxx（4段）的链接
    if not blog_link:
        for lnk in links:
            href = lnk.attrib.get("href", "")
            if href.startswith("/us/blog/") and len(href.split("/")) == 4:
                blog_link = lnk
                break
    blog_name = blog_link.get_all_text(strip=True) if blog_link else ""

    # 图片
    img_src = ""
    img_alt = ""
    img = card.css("img")
    if img:
        img_src = img[0].attrib.get("src", "")
        img_alt = img[0].attrib.get("alt", "")

    # 摘要（第二个 p 标签）
    summary = ""
    ps = card.css("p")
    if len(ps) >= 2:
        summary = ps[1].get_all_text(strip=True)
    elif ps:
        summary = ps[0].get_all_text(strip=True)

    # data-nid
    nid = card.attrib.get("data-nid", "")

    # 日期（从段落文本提取 "on Month DD, YYYY"）
    published_date = ""
    if ps:
        p0_text = ps[0].get_all_text(strip=False)
        date_match = re.search(r'on\s+(\w+\s+\d+,\s+\d{4})', p0_text)
        if date_match:
            published_date = date_match.group(1)

    article = {
        "id": nid,
        "title": title,
        "url": url,
        "summary": summary,
        "category": category_name,
        "category_url": category_url,
        "author": author_name,
        "author_url": author_url,
        "blog": blog_name,
        "image_url": img_src,
        "image_alt": img_alt,
        "published_date": published_date,
        # 以下字段由第二阶段填充
        "body_text": "",
        "body_text_length": 0,
        "key_points": "",
        "reviewed_by": "",
        "topics": [],
        "references": "",
        "scraped_at": datetime.now().isoformat(),
    }

    return article


def crawl_news_list(max_pages: int | None = MAX_PAGES) -> list:
    """爬取新闻列表"""
    all_articles = []
    page = 1

    print(f"📋 第一阶段：爬取文章列表")
    print(f"   目标: {BASE_URL}")
    print(f"   代理: {PROXY}")
    print(f"   最大页数: {max_pages or '不限'}")
    print()

    while True:
        if max_pages and page > max_pages:
            print(f"\n✅ 已达到最大页数限制 ({max_pages})，停止列表爬取")
            break

        articles, has_next = fetch_page(BASE_URL, page)
        all_articles.extend(articles)
        print(f"   ✔ 累计: {len(all_articles)} 篇文章\n")

        if not has_next:
            print(f"📄 没有更多页了")
            break

        page += 1

    return all_articles


# ============================================================
#  第二阶段：文章详情爬取
# ============================================================

def fetch_article_detail(url: str) -> dict:
    """
    获取文章详情页，提取正文内容。
    返回包含 body_text, key_points, reviewed_by, topics, references 的字典。
    如失败则返回空字段。
    """
    result = {
        "body_text": "",
        "body_text_length": 0,
        "key_points": "",
        "reviewed_by": "",
        "topics": [],
        "references": "",
    }

    try:
        resp = Fetcher.get(
            url,
            proxy=PROXY,
            timeout=REQUEST_TIMEOUT,
            retries=REQUEST_RETRIES,
        )
    except Exception as e:
        print(f"      ❌ 请求失败: {e}")
        return result

    if resp.status != 200:
        print(f"      ❌ HTTP {resp.status}")
        return result

    # --- 1. 正文文本 (.field-name-body) ---
    body_field = resp.css(".field-name-body")
    if body_field:
        # 获取全部文本（过滤掉明显的广告/推荐区块）
        body_text = body_field[0].get_all_text(strip=True, separator="\n\n")
        # 清理多余空行
        body_text = re.sub(r'\n{3,}', '\n\n', body_text).strip()
        result["body_text"] = body_text
        result["body_text_length"] = len(body_text)

    # --- 2. 关键要点 (.blog_entry__key-points) ---
    key_points_el = resp.css(".blog_entry__key-points")
    if key_points_el:
        result["key_points"] = key_points_el[0].get_all_text(strip=True, separator="\n")

    # --- 3. 审阅者 ---
    date_el = resp.css("p.blog-entry__date--full")
    if date_el:
        date_text = date_el[0].get_all_text(strip=False)
        reviewed_match = re.search(r'Reviewed by\s+(.+?)(?:\||$)', date_text)
        if reviewed_match:
            result["reviewed_by"] = reviewed_match.group(1).strip()

    # --- 4. 分类标签 ---
    topics = resp.css(".field--name-field-topics a")
    result["topics"] = [
        t.get_all_text(strip=True) for t in topics if t.get_all_text(strip=True)
    ]

    # --- 5. 参考文献 ---
    refs_el = resp.css(".blog-entry-references")
    if refs_el:
        refs_text = refs_el[0].get_all_text(strip=True, separator="\n")
        # 去掉 "References" 标题行
        refs_text = re.sub(r'^References\s*\n', '', refs_text).strip()
        result["references"] = refs_text

    return result


def enrich_articles_with_detail(articles: list) -> list:
    """遍历文章列表，逐篇获取详情"""
    total = len(articles)
    print(f"\n📖 第二阶段：爬取文章正文 ({total} 篇)")
    print(f"   请求间隔: {DETAIL_DELAY}s")
    print()

    enriched = []
    for idx, article in enumerate(articles, 1):
        if not article["url"]:
            print(f"  [{idx}/{total}] ⏭️ 跳过（无 URL）: {article['title'][:50]}")
            enriched.append(article)
            continue

        print(f"  [{idx}/{total}] 获取正文: {article['title'][:60]}...", end="")
        detail = fetch_article_detail(article["url"])
        article.update(detail)

        status = "✅"
        if article["body_text"]:
            status += f" ({article['body_text_length']} chars)"
        print(f"\r  [{idx}/{total}] {status}: {article['title'][:60]}")

        enriched.append(article)

        # 请求间隔，避免被 ban
        if idx < total:
            time.sleep(DETAIL_DELAY)

    return enriched


# ============================================================
#  保存
# ============================================================

def save_results(articles: list):
    """保存结果为 JSON + Markdown 摘要"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # --- JSON ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    # --- Markdown 摘要 ---
    summary_file = os.path.join(OUTPUT_DIR, "psychology_today_news_summary.md")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"# Psychology Today News 爬取结果\n\n")
        f.write(f"- **爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **文章总数**: {len(articles)}\n")
        articles_with_body = [a for a in articles if a.get("body_text")]
        f.write(f"- **含正文**: {len(articles_with_body)} 篇\n\n")

        f.write("| # | 标题 | 分类 | 作者 | 日期 | 正文长度 |\n")
        f.write("|---|------|------|------|------|----------|\n")
        for i, a in enumerate(articles, 1):
            body_len = a.get("body_text_length", 0)
            body_str = f"{body_len} chars" if body_len else "-"
            f.write(
                f"| {i} | [{a['title']}]({a['url']})"
                f" | {a['category']} | {a['author']}"
                f" | {a['published_date']} | {body_str} |\n"
            )

    print(f"\n💾 详细数据已保存: {os.path.abspath(OUTPUT_FILE)}")
    print(f"💾 摘要已保存: {os.path.abspath(summary_file)}")
    print(f"   文章总数: {len(articles)}")
    print(f"   含正文: {len(articles_with_body)} 篇")


# ============================================================
#  Main
# ============================================================

def main():
    print("=" * 60)
    print("  Psychology Today News 爬虫")
    print("  引擎: Scrapling (自适应模式)")
    print("=" * 60)
    print()

    start_time = time.time()

    try:
        # 第一阶段：列表
        articles = crawl_news_list(max_pages=MAX_PAGES)
        if not articles:
            print("⚠️ 没有获取到任何文章，退出")
            sys.exit(1)

        # 第二阶段：详情
        if FETCH_DETAIL:
            articles = enrich_articles_with_detail(articles)
        else:
            print("\n⏭️ 跳过正文爬取 (FETCH_DETAIL=False)")

        # 保存
        save_results(articles)

        elapsed = time.time() - start_time
        print(f"\n🎉 全部完成！耗时 {elapsed:.1f} 秒")

    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断爬取")
        # 中断时保存已爬取的数据
        if articles:
            print("💾 保存已爬取的数据...")
            save_results(articles)
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 爬取出错: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
