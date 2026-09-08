"""
Simply Psychology 新闻爬虫
=============================
基于 Scrapling 的自适应爬虫
- 通过 WordPress REST API 获取所有新闻（含正文全文）
- 提取正文文本 + 正文中图片
- 通过代理 (127.0.0.1:7897) 访问
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
from scrapling.parser import Selector  # 用于解析 HTML 内容

# ============================================================
#  配置区
# ============================================================
API_URL = "https://www.simplypsychology.org/wp-json/wp/v2/posts"
CATEGORY_ID = "224"          # "News" 分类 ID
PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "simplypsychology_news.json")
PER_PAGE = 100               # 一次性获取全部（最大 100）
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3

Fetcher.configure(adaptive=True, huge_tree=True)


def fetch_all_posts_via_api() -> list:
    """通过 WordPress REST API 获取所有新闻文章"""
    print(f"📋 通过 API 获取文章列表: {API_URL}")
    print(f"   分类: {CATEGORY_ID}, 每页: {PER_PAGE}")

    all_posts = []
    page = 1

    while True:
        print(f"   请求第 {page} 页...", end="")
        try:
            resp = Fetcher.get(
                API_URL,
                proxy=PROXY,
                timeout=REQUEST_TIMEOUT,
                retries=REQUEST_RETRIES,
                params={
                    'page': str(page),
                    'categories': CATEGORY_ID,
                    'per_page': str(PER_PAGE),
                    '_embed': 'true',
                },
            )
        except Exception as e:
            print(f" ❌ {e}")
            break

        if resp.status != 200:
            print(f" ❌ HTTP {resp.status}")
            break

        total = resp.headers.get('x-wp-total', '?')
        total_pages = resp.headers.get('x-wp-totalpages', '?')
        posts = json.loads(resp.body)

        if not posts:
            print(" ❌ 无数据")
            break

        print(f" ✅ {len(posts)} 篇 (总计 {total} 篇, 共 {total_pages} 页)")
        all_posts.extend(posts)

        if int(total_pages) <= page:
            break
        page += 1

    print(f"\n   API 共获取: {len(all_posts)} 篇原始数据\n")
    return all_posts


def parse_post(raw: dict) -> dict:
    """解析单篇 API 返回的文章"""
    title = raw.get('title', {}).get('rendered', '')
    # 清理 HTML 标签
    title = re.sub(r'<[^>]+>', '', title).strip()

    link = raw.get('link', '')
    slug = raw.get('slug', '')
    post_id = raw.get('id', '')

    # 发布日期
    date_raw = raw.get('date', '')
    published_date = ""
    if date_raw:
        try:
            dt = datetime.fromisoformat(date_raw.replace('Z', '+00:00'))
            published_date = dt.strftime('%B %d, %Y')
        except:
            published_date = date_raw[:10]

    # 分类
    # 通常在 _embedded 的 wp:term 中
    category = ""
    embedded = raw.get('_embedded', {})
    terms = embedded.get('wp:term', [])
    for term_list in terms:
        for term in term_list:
            if term.get('taxonomy') == 'category':
                name = term.get('name', '')
                if name and name.lower() != 'news':
                    category = name
                elif name and name.lower() == 'news' and not category:
                    category = name

    # 特色图片
    image_url = ""
    image_alt = ""
    media = embedded.get('wp:featuredmedia', [])
    if media:
        sizes = media[0].get('media_details', {}).get('sizes', {})
        # 优先 medium_large，其次 medium，再 full
        for pref in ['medium_large', 'medium', 'large', 'full']:
            if pref in sizes:
                image_url = sizes[pref].get('source_url', '')
                if image_url:
                    break
        if not image_url:
            image_url = media[0].get('source_url', '')
        image_alt = media[0].get('alt_text', '')

    # --- 正文 ---
    content_html = raw.get('content', {}).get('rendered', '')
    body_text = ""
    body_images = []

    if content_html:
        # 用 Selector 解析 HTML
        sel = Selector(content_html, adaptive=True, huge_tree=True)
        body_text = sel.get_all_text(strip=True, separator="\n\n")
        body_text = re.sub(r'\n{3,}', '\n\n', body_text).strip()

        # 提取正文中的图片（排除 sidebar/carousel）
        seen_srcs = set()
        for img in sel.css("img[src]"):
            src = img.attrib.get("src", "")
            alt = img.attrib.get("alt", "")
            if not src.startswith("http"):
                continue
            if "logo" in src.lower() or "icon" in src.lower() or "emoji" in src.lower():
                continue

            src_key = src.split("?")[0].rsplit("/", 1)[-1][:80]
            if src_key not in seen_srcs:
                seen_srcs.add(src_key)
                body_images.append({"src": src, "alt": alt or ""})

    # 摘要
    excerpt_html = raw.get('excerpt', {}).get('rendered', '')
    summary = re.sub(r'<[^>]+>', '', excerpt_html).strip() if excerpt_html else ""

    # 作者
    author_name = ""
    authors = embedded.get('author', [])
    if authors:
        author_name = authors[0].get('name', '')

    # 手动从正文提取审阅者
    reviewed_by = ""
    if body_text:
        rm = re.search(r'Reviewed by\s+(.+?)(?:\n|$)', body_text)
        if rm:
            reviewed_by = rm.group(1).strip()
            # 从正文中移除审阅者行
            body_text = re.sub(r'^.*?Reviewed by\s+(.+?)(?:\n|$)', '', body_text, count=1).strip()

    return {
        "id": str(post_id),
        "title": title,
        "url": link,
        "slug": slug,
        "summary": summary,
        "category": category,
        "reviewed_by": reviewed_by,
        "image_url": image_url,
        "image_alt": image_alt,
        "author": author_name,
        "published_date": published_date,
        "body_text": body_text,
        "body_text_length": len(body_text),
        "body_images": body_images,
        "body_image_count": len(body_images),
        "scraped_at": datetime.now().isoformat(),
    }


def save_results(articles: list):
    """保存 JSON + Markdown 摘要"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    summary_file = os.path.join(OUTPUT_DIR, "simplypsychology_news_summary.md")
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write("# Simply Psychology News 爬取结果\n\n")
        f.write(f"- **爬取方式**: WordPress REST API\n")
        f.write(f"- **爬取时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- **文章总数**: {len(articles)}\n")
        with_body = sum(1 for a in articles if a.get("body_text"))
        total_imgs = sum(a.get("body_image_count", 0) for a in articles)
        f.write(f"- **含正文**: {with_body} 篇\n")
        f.write(f"- **正文图片**: {total_imgs} 张\n\n")

        f.write("| # | 标题 | 日期 | 作者 | 正文长度 | 图片 |\n")
        f.write("|---|------|------|------|----------|------|\n")
        for i, a in enumerate(articles, 1):
            body_len = a.get("body_text_length", 0) or "-"
            img_count = a.get("body_image_count", 0)
            f.write(
                f"| {i} | [{a['title'][:50]}]({a['url']})"
                f" | {a.get('published_date', '')}"
                f" | {a.get('author', '')[:20]}"
                f" | {body_len} | {img_count} |\n"
            )

    print(f"\n💾 数据已保存: {os.path.abspath(OUTPUT_FILE)}")
    print(f"💾 摘要已保存: {os.path.abspath(summary_file)}")
    print(f"   文章总数: {len(articles)}")
    print(f"   含正文: {with_body} 篇")
    print(f"   正文图片: {total_imgs} 张")


def main():
    print("=" * 60)
    print("  Simply Psychology 新闻爬虫 (API 版)")
    print("  引擎: Scrapling + WordPress REST API")
    print("=" * 60)
    print()

    start_time = time.time()

    try:
        # 通过 API 获取所有文章（含 HTML 正文）
        raw_posts = fetch_all_posts_via_api()
        if not raw_posts:
            print("⚠️ 没有获取到文章")
            sys.exit(1)

        # 解析每篇文章
        print("📝 解析文章数据...")
        articles = []
        for i, raw in enumerate(raw_posts, 1):
            article = parse_post(raw)
            articles.append(article)
            img_info = f" ({article['body_image_count']} img)" if article['body_image_count'] else ""
            print(f"  [{i}/{len(raw_posts)}] {article['title'][:60]}... ✅ ({article['body_text_length']} chars{img_info})")

        save_results(articles)

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
