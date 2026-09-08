"""
BPS News 爬虫
==============
通过 GraphQL API 获取文章列表 + 逐篇提取正文
"""
import json, os, re, sys, time
from datetime import datetime
from urllib.parse import urljoin
from scrapling.fetchers import Fetcher
from scrapling.parser import Selector

PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "bps_news.json")
FETCH_DETAIL = True
DETAIL_DELAY = 0.3
MAX_PAGES = 94  # API 返回 94 页

GQL_URL = "https://cms.bps.org.uk/graphql"
GQL_QUERY = """
query SearchNews($keyword: String!, $page: Int!, $sortBy: String!, $pageSize: Int!, $type: [String!], $topics: [Int], $year: Int, $month: Int, $showExcludedNews: Boolean) {
  search(keyword: $keyword, page: $page, sortBy: $sortBy, pageSize: $pageSize, type: $type, topics: $topics, year: $year, month: $month, showExcludedNews: $showExcludedNews) {
    total totalPages page result_list {
      url media: image { url altText __typename }
      type title datePublished formattedDatePublished summary topics __typename
    }
  }
}
"""

Fetcher.configure(adaptive=True, huge_tree=True)


# ============================================================
#  第一阶段：GraphQL API 获取列表
# ============================================================

def fetch_page_via_api(page: int) -> list:
    """通过 GraphQL 获取单页文章列表"""
    try:
        resp = Fetcher.post(
            GQL_URL,
            proxy=PROXY,
            timeout=15,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "operationName": "SearchNews",
                "variables": {
                    "keyword": "", "sortBy": "desc", "page": page,
                    "pageSize": 12, "type": ["news_article"],
                    "topics": [], "month": 0, "year": 0,
                },
                "query": GQL_QUERY,
            },
        )
    except Exception as e:
        return []

    if resp.status != 200:
        return []

    try:
        data = json.loads(resp.body)
    except:
        return []
    results = data.get("data", {}).get("search", {}).get("result_list", [])
    return results


def collect_all_articles() -> list:
    """获取全部文章"""
    all_articles = []

    for page in range(MAX_PAGES):
        results = fetch_page_via_api(page)
        if not results:
            print(f"  第{page+1}页: 无结果, 停止")
            break

        for r in results:
            url = r.get("url", "")
            if not url:
                continue
            # 确保完整 URL
            if url.startswith("/"):
                url = f"https://www.bps.org.uk{url}"

            media = r.get("media", {}) or {}
            all_articles.append({
                "title": r.get("title", ""),
                "url": url,
                "summary": r.get("summary", ""),
                "published_date": r.get("formattedDatePublished", ""),
                "date_timestamp": r.get("datePublished", ""),
                "topics": r.get("topics", []),
                "image_url": media.get("url", ""),
                "image_alt": media.get("altText", ""),
                "body_text": "",
                "body_text_length": 0,
                "body_images": [],
            })

        print(f"  第{page+1}/{MAX_PAGES}页: {len(results)} 条 (累计 {len(all_articles)})")
        time.sleep(0.3)

    return all_articles


# ============================================================
#  第二阶段：逐篇获取正文
# ============================================================

def fetch_article_body(url: str) -> dict:
    """从文章页提取正文和图片（从 SSR JSON 中提取）"""
    result = {"body_text": "", "body_text_length": 0, "body_images": []}

    try:
        resp = Fetcher.get(url, proxy=PROXY, timeout=30, retries=3)
    except:
        return result
    if resp.status != 200:
        return result

    html = resp.body.decode("utf-8", errors="replace")

    # 从 SSR JSON 中提取 content 数组
    # 找 "content":[ 并用括号计数找到匹配的 ]
    idx = html.find('"content":[')
    if idx >= 0:
        depth = 0
        start = idx + len('"content":[') - 1  # 指向 [
        for end in range(start, min(start + 50000, len(html))):
            ch = html[end]
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    # 找到匹配的 ]
                    content_str = html[start:end+1]
                    try:
                        content_list = json.loads(content_str)
                        body_parts = []
                        for item in content_list:
                            c = item.get("content", {})
                            proc = c.get("processed", "")
                            if proc:
                                sel = Selector(proc, adaptive=True, huge_tree=True)
                                body_parts.append(sel.get_all_text(strip=True, separator="\n\n"))
                        if body_parts:
                            result["body_text"] = re.sub(r'\n{3,}', '\n\n', "\n\n".join(body_parts)).strip()
                            result["body_text_length"] = len(result["body_text"])
                    except:
                        pass
                    break

    # 图片
    imgs = []
    seen = set()
    for img in resp.css("img[src]"):
        src = img.attrib.get("src", "")
        alt = img.attrib.get("alt", "")
        if src.startswith("http") and "icon" not in src.lower() and "logo" not in src.lower():
            key = src.split("?")[0].rsplit("/", 1)[-1][:60]
            if key not in seen:
                seen.add(key)
                imgs.append({"src": src, "alt": alt or ""})
    result["body_images"] = imgs

    return result


def enrich_articles(articles: list) -> list:
    total = len(articles)
    print(f"\n📖 获取正文 ({total} 篇)...")
    enriched = []
    for i, a in enumerate(articles, 1):
        print(f"  [{i}/{total}] {a['title'][:55]}...", end="", flush=True)
        detail = fetch_article_body(a["url"])
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


# ============================================================
#  保存
# ============================================================

def save(articles: list):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n💾 {os.path.abspath(OUTPUT_FILE)}")
    wb = sum(1 for a in articles if a.get("body_text"))
    ti = sum(len(a.get("body_images", [])) for a in articles)
    print(f"   文章: {len(articles)}, 含正文: {wb}, 图片: {ti}")


# ============================================================
#  Main
# ============================================================

def main():
    print("=" * 55)
    print("  BPS News (GraphQL + 正文)")
    print("=" * 55)
    t0 = time.time()

    print("\n📋 第一阶段: GraphQL API 获取文章列表...")
    articles = collect_all_articles()
    if not articles:
        print("❌ 无数据"); return
    print(f"  总计: {len(articles)} 篇")

    if FETCH_DETAIL and articles:
        articles = enrich_articles(articles)

    save(articles)
    print(f"⏱ {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
