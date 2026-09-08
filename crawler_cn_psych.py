"""
中国心理学站点新闻爬虫
====================
基于 Scrapling 库，爬取 8 个中国心理学/出版站点的新闻内容。
每个站点独立处理，输出到 output/cn_站点名.json

站点列表：
1. 轻工业出版社 http://www.chlip.com.cn
2. 华师大出版社 https://www.ecnupress.com.cn
3. 中科院心理所 https://www.psych.ac.cn
4. 中国心理学会 https://www.cpsbeijing.org
5. 简单心理 https://www.jiandanxinli.com
6. 壹心理 https://www.xinli001.com
7. 人邮出版社 https://www.ptpress.com.cn
8. 浙江教育出版 http://www.zjeph.com
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs

from scrapling.fetchers import Fetcher

# ============================================================
# 全局配置
# ============================================================
PROXY = "http://127.0.0.1:7897"
OUTPUT_DIR = "output"
REQUEST_TIMEOUT = 30
REQUEST_RETRIES = 3
DETAIL_DELAY = 1.0  # 详情页请求间隔（秒）

Fetcher.configure(adaptive=True, huge_tree=True)

# ============================================================
# 工具函数
# ============================================================

def safe_get(url, **kwargs):
    """安全发起 GET 请求，统一处理异常"""
    params = {
        "proxy": PROXY,
        "timeout": REQUEST_TIMEOUT,
        "retries": REQUEST_RETRIES,
        "follow_redirects": True,
    }
    params.update(kwargs)
    try:
        resp = Fetcher.get(url, **params)
        return resp
    except Exception as e:
        print(f"    ⚠️ 请求异常: {e}")
        return None


def fetch_with_verify_fallback(url, **kwargs):
    """先用 verify=True 请求，SSL 错误时降级为 verify=False"""
    resp = safe_get(url, verify=True, **kwargs)
    if resp is None:
        # SSL 错误或连接失败，重试 verify=False
        print(f"    ⚠️ 尝试 verify=False 重试...")
        resp = safe_get(url, verify=False, **kwargs)
    return resp


def extract_text(element, default=""):
    """从 Scrapling 元素提取纯文本"""
    if element:
        return element.get_all_text(strip=True)
    return default


def extract_attr(element, attr, default=""):
    """从 Scrapling 元素提取属性"""
    if element and len(element) > 0:
        return element[0].attrib.get(attr, default)
    return default


def extract_images(element):
    """从元素中提取所有图片信息"""
    images = []
    if not element:
        return images
    imgs = element.css("img")
    seen = set()
    for img in imgs:
        src = img.attrib.get("src", "").strip()
        if src and src not in seen:
            seen.add(src)
            alt = img.attrib.get("alt", "")
            images.append({"src": src, "alt": alt})
    return images


def save_results(site_name, articles):
    """保存站点爬取结果为 JSON"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, f"cn_{site_name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"  💾 已保存: {os.path.abspath(filepath)} ({len(articles)} 条)")
    return filepath


# ============================================================
# 站点 1: 轻工业出版社
# ============================================================

def crawl_chlip():
    """
    轻工业出版社 http://www.chlip.com.cn
    新闻列表: /news/index.php
    文章链接: /news/show.php/id-XXX.html
    正文: .content 或 .article 选择器
    """
    print("\n" + "=" * 60)
    print("  站点 1/8: 轻工业出版社 (www.chlip.com.cn)")
    print("=" * 60)

    base = "http://www.chlip.com.cn"
    list_url = urljoin(base, "/news/index.php")

    # 获取列表页
    resp = safe_get(list_url)
    if resp is None or resp.status != 200:
        print(f"  ❌ 无法访问列表页，状态码: {getattr(resp, 'status', 'N/A')}")
        return []

    # 提取文章链接 - 匹配 /news/show.php/id-XXX.html
    articles_data = []
    links = resp.css("a[href*='/news/show.php/']")

    # 如果没找到，尝试其他模式
    if not links:
        links = resp.css("a[href*='show.php']")

    print(f"  找到 {len(links)} 个文章链接")

    seen_urls = set()
    for link in links:
        href = link.attrib.get("href", "").strip()
        if not href:
            continue

        full_url = urljoin(base, href)

        # 去重
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title = link.get_all_text(strip=True)
        if not title or len(title) < 5:
            continue

        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "轻工业出版社",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  去重后: {len(articles_data)} 篇文章")

    # 获取详情
    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"])
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌ HTTP {getattr(resp, 'status', 'N/A')}: {article['title'][:50]}")
            continue

        # 尝试多种选择器提取正文
        body_el = resp.css(".content")
        if not body_el:
            body_el = resp.css(".article")
        if not body_el:
            body_el = resp.css(".main-content")
        if not body_el:
            body_el = resp.css("#content")
        if not body_el:
            body_el = resp.css("article")

        if body_el:
            # 移除不需要的元素
            for unwanted in body_el[0].css("script, style, .nav, .menu, .header, .footer, .sidebar"):
                unwanted.remove()

            article["body_text"] = body_el[0].get_all_text(strip=True, separator="\n\n")
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', article["body_text"]).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        body_len = article["body_text_length"]
        img_count = len(article["body_images"])
        print(f"\r  [{idx}/{total}] ✅ ({body_len} chars, {img_count} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("chlip", articles_data)
    return articles_data


# ============================================================
# 站点 2: 华师大出版社
# ============================================================

def crawl_ecnupress():
    """
    华师大出版社 https://www.ecnupress.com.cn
    新闻资讯URL含 news_id=
    """
    print("\n" + "=" * 60)
    print("  站点 2/8: 华师大出版社 (www.ecnupress.com.cn)")
    print("=" * 60)

    base = "https://www.ecnupress.com.cn"
    articles_data = []

    # 尝试常见新闻列表路径
    list_paths = ["/news/", "/xwzx/", "/News/", "/article/"]
    found_links = []

    for path in list_paths:
        list_url = urljoin(base, path)
        resp = safe_get(list_url, verify=True)
        if resp is None:
            resp = safe_get(list_url, verify=False)
        if resp is None or resp.status != 200:
            continue

        # 查找包含 news_id= 的链接
        links = resp.css("a[href*='news_id=']")
        if links:
            found_links = links
            print(f"  在 {path} 找到 {len(links)} 个含 news_id= 的链接")
            break

        # 也找其他链接模式
        links = resp.css("a[href*='.html']")
        if links:
            found_links = links
            print(f"  在 {path} 找到 {len(links)} 个 .html 链接")
            break

    if not found_links:
        # 尝试直接在首页查找
        resp = safe_get(base, verify=True)
        if resp is None:
            resp = safe_get(base, verify=False)
        if resp and resp.status == 200:
            found_links = resp.css("a[href*='news_id=']")
            if not found_links:
                found_links = resp.css("a[href*='.html']")
            print(f"  首页找到 {len(found_links)} 个链接")

    if not found_links:
        print("  ❌ 未找到任何文章链接")
        save_results("ecnupress", [])
        return []

    seen_urls = set()
    for link in found_links:
        href = link.attrib.get("href", "").strip()
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue

        full_url = urljoin(base, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title = link.get_all_text(strip=True)
        if not title or len(title) < 4:
            continue

        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "华师大出版社",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  总计 {len(articles_data)} 篇文章")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"], verify=True)
        if resp is None:
            resp = safe_get(article["url"], verify=False)
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        # 尝试多个选择器
        body_el = resp.css(".content") or resp.css(".article") or resp.css(".maintext")
        body_el = body_el or resp.css(".news-content") or resp.css("#content") or resp.css("article")

        if body_el:
            for unwanted in body_el[0].css("script, style, .nav, .menu, .header, .footer, .sidebar"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("ecnupress", articles_data)
    return articles_data


# ============================================================
# 站点 3: 中科院心理所
# ============================================================

def crawl_psych_ac():
    """
    中科院心理所 https://www.psych.ac.cn
    SSL 错误时尝试 verify=False
    """
    print("\n" + "=" * 60)
    print("  站点 3/8: 中科院心理所 (www.psych.ac.cn)")
    print("=" * 60)

    base = "https://www.psych.ac.cn"
    articles_data = []

    # 尝试多个新闻路径
    list_paths = [
        "/xwzx/", "/xwdt/", "/tzgg/", "/news/",
        "/xwzx/jxky/", "/xwzx/zhxw/", "/xwzx/mtjj/",
        "/xwdt/zhxw/", "/xwdt/mtjj/",
    ]

    all_links = []
    for path in list_paths:
        url = urljoin(base, path)
        resp = fetch_with_verify_fallback(url)
        if resp is None or resp.status != 200:
            continue

        # 找所有链接
        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(base, href)
            # 过滤：是文章链接（含路径且不是根路径，不含#）
            if base in full_url and full_url != base and "#" not in full_url:
                title = link.get_all_text(strip=True)
                if title and len(title) >= 4:
                    all_links.append((full_url, title, path))

        print(f"  在 {path} 找到页面，继续...")
        break  # 只取第一个成功的路径

    # 如果上面的路径都没找到，尝试爬取首页
    if not all_links:
        resp = fetch_with_verify_fallback(base)
        if resp and resp.status == 200:
            for link in resp.css("a[href]"):
                href = link.attrib.get("href", "").strip()
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue
                full_url = urljoin(base, href)
                if base in full_url and full_url != base:
                    # 过滤掉明显的导航/分类页
                    path = urlparse(full_url).path
                    if path.count("/") >= 2:
                        title = link.get_all_text(strip=True)
                        if title and len(title) >= 4:
                            all_links.append((full_url, title, "home"))

    seen_urls = set()
    for full_url, title, _ in all_links:
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "中科院心理所",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  找到 {len(articles_data)} 个链接")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = fetch_with_verify_fallback(article["url"])
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        body_el = (resp.css(".content") or resp.css(".article") or resp.css(".main")
                   or resp.css(".TRS_Editor") or resp.css("#content") or resp.css("article"))

        if body_el:
            for unwanted in body_el[0].css("script, style, .nav, .menu, .header, .footer, .sidebar"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("psych_ac", articles_data)
    return articles_data


# ============================================================
# 站点 4: 中国心理学会
# ============================================================

def crawl_cpsbeijing():
    """
    中国心理学会 https://www.cpsbeijing.org
    少量内容，提取所有链接
    """
    print("\n" + "=" * 60)
    print("  站点 4/8: 中国心理学会 (www.cpsbeijing.org)")
    print("=" * 60)

    base = "https://www.cpsbeijing.org"
    articles_data = []

    # 尝试多个路径
    paths_to_try = [
        "/", "/news/", "/xwzx/", "/xwdt/", "/tzgg/",
        "/pub/", "/cps/", "/index.php",
    ]

    all_links = set()
    for path in paths_to_try:
        url = urljoin(base, path)
        resp = safe_get(url, verify=False)
        if resp is None:
            resp = safe_get(url, verify=True)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(base, href)
            # 只取本站链接
            if base.replace("https://", "http://") in full_url or base in full_url:
                title = link.get_all_text(strip=True)
                if title and len(title) >= 4:
                    all_links.add((full_url, title))

        print(f"  在 {path} 找到 {len(all_links)} 个链接")

    # 去重
    seen = set()
    for full_url, title in all_links:
        if full_url in seen:
            continue
        seen.add(full_url)

        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "中国心理学会",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  去重后: {len(articles_data)} 条")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"], verify=False)
        if resp is None:
            resp = safe_get(article["url"], verify=True)
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        body_el = (resp.css(".content") or resp.css(".article") or resp.css(".main")
                   or resp.css(".TRS_Editor") or resp.css("#content") or resp.css("article")
                   or resp.css("body"))

        if body_el:
            for unwanted in body_el[0].css("script, style, .nav, .menu, .header, .footer, .sidebar, nav, .banner, .top"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("cpsbeijing", articles_data)
    return articles_data


# ============================================================
# 站点 5: 简单心理
# ============================================================

def crawl_jiandanxinli():
    """
    简单心理 https://www.jiandanxinli.com/news
    """
    print("\n" + "=" * 60)
    print("  站点 5/8: 简单心理 (www.jiandanxinli.com)")
    print("=" * 60)

    base = "https://www.jiandanxinli.com"
    articles_data = []

    # 尝试多页
    for page_num in range(1, 6):  # 最多 5 页
        if page_num == 1:
            url = f"{base}/news"
        else:
            url = f"{base}/news?page={page_num}"

        print(f"  [列表 第{page_num}页] {url}")
        resp = safe_get(url)
        if resp is None or resp.status != 200:
            print(f"  [列表 第{page_num}页] ❌ 状态码: {getattr(resp, 'status', 'N/A')}")
            break

        # 找文章链接
        links = resp.css("a[href*='/news/']")
        if not links:
            links = resp.css("a[href*='/article/']")
        if not links:
            links = resp.css("a[href]")
            # 过滤
            filtered = []
            for l in links:
                h = l.attrib.get("href", "")
                if h and "/" in h and not h.startswith("#") and not h.startswith("javascript"):
                    filtered.append(l)
            links = filtered

        found = 0
        for link in links:
            href = link.attrib.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(base, href)
            title = link.get_all_text(strip=True)
            if not title or len(title) < 4:
                continue

            # 去重
            if any(a["url"] == full_url for a in articles_data):
                continue

            articles_data.append({
                "title": title,
                "url": full_url,
                "source": "简单心理",
                "body_text": "",
                "body_text_length": 0,
                "body_images": [],
                "scraped_at": datetime.now().isoformat(),
            })
            found += 1

        print(f"  第{page_num}页新发现: {found} 条")

        # 检测是否有下一页
        next_btn = resp.css("a:contains('下一页')") or resp.css("a:contains('next')")
        if not next_btn and found == 0:
            break

    print(f"  总计: {len(articles_data)} 条")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"])
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        body_el = (resp.css(".content") or resp.css(".article") or resp.css(".post-content")
                   or resp.css(".entry-content") or resp.css("#content") or resp.css("article"))

        if body_el:
            for unwanted in body_el[0].css("script, style, nav, .nav, .menu, .sidebar, .footer, .header"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("jiandanxinli", articles_data)
    return articles_data


# ============================================================
# 站点 6: 壹心理
# ============================================================

def crawl_xinli001():
    """
    壹心理 https://www.xinli001.com
    """
    print("\n" + "=" * 60)
    print("  站点 6/8: 壹心理 (www.xinli001.com)")
    print("=" * 60)

    base = "https://www.xinli001.com"
    articles_data = []

    # 尝试多个新闻/文章路径
    paths_to_try = [
        "/info/", "/article/", "/news/",
        "/column/", "/focus/",
    ]

    all_links = set()
    for path in paths_to_try:
        url = urljoin(base, path)
        resp = safe_get(url)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(base, href)
            if base in full_url:
                title = link.get_all_text(strip=True)
                if title and len(title) >= 4:
                    all_links.add((full_url, title))
        print(f"  在 {path} 找到 {len(all_links)} 个链接")

    # 也试试首页
    if not all_links:
        resp = safe_get(base)
        if resp and resp.status == 200:
            for link in resp.css("a[href]"):
                href = link.attrib.get("href", "").strip()
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue
                full_url = urljoin(base, href)
                if base in full_url:
                    title = link.get_all_text(strip=True)
                    if title and len(title) >= 4:
                        all_links.add((full_url, title))
            print(f"  首页找到 {len(all_links)} 个链接")

    seen = set()
    for full_url, title in all_links:
        if full_url in seen:
            continue
        seen.add(full_url)
        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "壹心理",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  总计: {len(articles_data)} 条")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"])
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        body_el = (resp.css(".content") or resp.css(".article") or resp.css(".post-content")
                   or resp.css(".entry-content") or resp.css(".detail-content")
                   or resp.css("#content") or resp.css("article"))

        if body_el:
            for unwanted in body_el[0].css("script, style, nav, .nav, .menu, .sidebar, .footer, .header"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("xinli001", articles_data)
    return articles_data


# ============================================================
# 站点 7: 人邮出版社
# ============================================================

def crawl_ptpress():
    """
    人邮出版社 https://www.ptpress.com.cn
    """
    print("\n" + "=" * 60)
    print("  站点 7/8: 人邮出版社 (www.ptpress.com.cn)")
    print("=" * 60)

    base = "https://www.ptpress.com.cn"
    articles_data = []

    # 尝试多个路径
    paths_to_try = [
        "/news/", "/xwzx/", "/xwdt/",
        "/media/", "/press/news/",
    ]

    all_links = set()
    for path in paths_to_try:
        url = urljoin(base, path)
        resp = safe_get(url, verify=False)
        if resp is None:
            resp = safe_get(url, verify=True)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(base, href)
            if base in full_url:
                title = link.get_all_text(strip=True)
                if title and len(title) >= 4:
                    all_links.add((full_url, title))
        print(f"  在 {path} 找到 {len(all_links)} 个链接")
        break

    # 如果上面的路径都找不到，爬首页
    if not all_links:
        resp = safe_get(base, verify=False)
        if resp is None:
            resp = safe_get(base, verify=True)
        if resp and resp.status == 200:
            for link in resp.css("a[href]"):
                href = link.attrib.get("href", "").strip()
                if not href or href.startswith("#") or href.startswith("javascript"):
                    continue
                full_url = urljoin(base, href)
                if base in full_url:
                    title = link.get_all_text(strip=True)
                    if title and len(title) >= 4:
                        all_links.add((full_url, title))
            print(f"  首页找到 {len(all_links)} 个链接")

    seen = set()
    for full_url, title in all_links:
        if full_url in seen:
            continue
        seen.add(full_url)
        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "人邮出版社",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  总计: {len(articles_data)} 条")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"], verify=False)
        if resp is None:
            resp = safe_get(article["url"], verify=True)
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        body_el = (resp.css(".content") or resp.css(".article") or resp.css(".main-content")
                   or resp.css(".text") or resp.css("#content") or resp.css("article"))

        if body_el:
            for unwanted in body_el[0].css("script, style, nav, .nav, .menu, .sidebar, .footer, .header"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("ptpress", articles_data)
    return articles_data


# ============================================================
# 站点 8: 浙江教育出版
# ============================================================

def crawl_zjeph():
    """
    浙江教育出版 http://www.zjeph.com
    如果返回 412 则跳过
    """
    print("\n" + "=" * 60)
    print("  站点 8/8: 浙江教育出版 (www.zjeph.com)")
    print("=" * 60)

    base = "http://www.zjeph.com"
    articles_data = []

    # 先测试是否能访问
    resp = safe_get(base)
    if resp is None:
        print("  ❌ 无法访问，跳过")
        save_results("zjeph", [])
        return []

    if resp.status == 412:
        print("  ❌ HTTP 412 (Precondition Failed)，跳过此站点")
        save_results("zjeph", [])
        return []

    # 尝试多个路径
    paths_to_try = [
        "/", "/news/", "/xwzx/", "/xwdt/",
        "/zx/", "/jyxw/",
    ]

    all_links = set()
    for path in paths_to_try:
        url = urljoin(base, path)
        resp = safe_get(url)
        if resp is None or resp.status != 200:
            continue

        for link in resp.css("a[href]"):
            href = link.attrib.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            full_url = urljoin(base, href)
            if base in full_url:
                title = link.get_all_text(strip=True)
                if title and len(title) >= 4:
                    all_links.add((full_url, title))
        print(f"  在 {path} 找到 {len(all_links)} 个链接")
        break

    if not all_links:
        print("  ⚠️ 未找到任何链接")
        save_results("zjeph", [])
        return []

    seen = set()
    for full_url, title in all_links:
        if full_url in seen:
            continue
        seen.add(full_url)
        articles_data.append({
            "title": title,
            "url": full_url,
            "source": "浙江教育出版",
            "body_text": "",
            "body_text_length": 0,
            "body_images": [],
            "scraped_at": datetime.now().isoformat(),
        })

    print(f"  总计: {len(articles_data)} 条")

    total = len(articles_data)
    for idx, article in enumerate(articles_data, 1):
        print(f"  [{idx}/{total}] {article['title'][:50]}...", end="")
        sys.stdout.flush()

        resp = safe_get(article["url"])
        if resp is None or resp.status != 200:
            print(f"\r  [{idx}/{total}] ❌: {article['title'][:50]}")
            continue

        body_el = (resp.css(".content") or resp.css(".article") or resp.css(".main-content")
                   or resp.css(".text") or resp.css("#content") or resp.css("article")
                   or resp.css(".neirong") or resp.css(".detail"))

        if body_el:
            for unwanted in body_el[0].css("script, style, nav, .nav, .menu, .sidebar, .footer, .header"):
                unwanted.remove()
            article["body_text"] = re.sub(r'\n{3,}', '\n\n', body_el[0].get_all_text(strip=True, separator="\n\n")).strip()
            article["body_text_length"] = len(article["body_text"])
            article["body_images"] = extract_images(body_el[0])

        print(f"\r  [{idx}/{total}] ✅ ({article['body_text_length']} chars, {len(article['body_images'])} imgs): {article['title'][:50]}")

        if idx < total:
            time.sleep(DETAIL_DELAY)

    save_results("zjeph", articles_data)
    return articles_data


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  中国心理学站点新闻爬虫")
    print("  引擎: Scrapling (自适应模式)")
    print(f"  代理: {PROXY}")
    print(f"  输出: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 60)

    # 站点映射 name -> (func, display_name)
    sites = [
        ("chlip", crawl_chlip, "轻工业出版社"),
        ("ecnupress", crawl_ecnupress, "华师大出版社"),
        ("psych_ac", crawl_psych_ac, "中科院心理所"),
        ("cpsbeijing", crawl_cpsbeijing, "中国心理学会"),
        ("jiandanxinli", crawl_jiandanxinli, "简单心理"),
        ("xinli001", crawl_xinli001, "壹心理"),
        ("ptpress", crawl_ptpress, "人邮出版社"),
        ("zjeph", crawl_zjeph, "浙江教育出版"),
    ]

    results = {}
    start_time = time.time()

    for site_key, crawl_func, site_name in sites:
        site_start = time.time()
        try:
            articles = crawl_func()
            elapsed = time.time() - site_start
            count = len(articles)
            with_body = sum(1 for a in articles if a.get("body_text"))
            print(f"\n  ✅ {site_name} 完成: {count} 条, {with_body} 条含正文, 耗时 {elapsed:.1f}s")
            results[site_key] = {"count": count, "with_body": with_body, "time": elapsed}
        except KeyboardInterrupt:
            print(f"\n\n⚠️ 用户中断，退出")
            break
        except Exception as e:
            elapsed = time.time() - site_start
            print(f"\n  ❌ {site_name} 失败: {e}, 耗时 {elapsed:.1f}s")
            import traceback
            traceback.print_exc()
            results[site_key] = {"error": str(e), "time": elapsed}

    # 输出总结
    total_time = time.time() - start_time
    print("\n" + "=" * 60)
    print("  爬取完成！总结")
    print("=" * 60)
    total_articles = 0
    total_with_body = 0
    for site_key, func, site_name in sites:
        r = results.get(site_key, {})
        if "error" in r:
            print(f"  ❌ {site_name}: 失败 - {r['error']} ({r['time']:.1f}s)")
        else:
            print(f"  ✅ {site_name}: {r.get('count', 0)} 条, {r.get('with_body', 0)} 条含正文 ({r.get('time', 0):.1f}s)")
            total_articles += r.get("count", 0)
            total_with_body += r.get("with_body", 0)
    print(f"\n  总计: {total_articles} 条, {total_with_body} 条含正文")
    print(f"  总耗时: {total_time:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
