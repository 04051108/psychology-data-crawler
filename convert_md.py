# -*- coding: utf-8 -*-
"""
处理流程：
1. 删除基本无正文的部分（正文 < 50 字），记录删除清单
2. 将保留的"正常数据"从 JSON 转为 Markdown
3. 下载正文/封面图片到本地并嵌入 Markdown
4. 生成处理总结记录
"""
import json, os, re, sys, time, shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from scrapling.fetchers import Fetcher

# ---------------- 配置 ----------------
PROXY = "http://127.0.0.1:7897"
ROOT = "output"
DIR_CLEAN = "output_clean"
DIR_MD = "output_md"
DIR_REC = "记录"
MIN_BODY = 50                      # 正文低于此字数视为"基本无正文"

Fetcher.configure(adaptive=True, huge_tree=True)
os.makedirs(DIR_CLEAN, exist_ok=True)
os.makedirs(DIR_REC, exist_ok=True)

# 图片垃圾过滤关键字
JUNK_KEYS = ("nav", "logo", "icon", "banner", "button", "bg_", "sprite",
             "favicon", "header", "qrcode", "二维码", "wechat", "share")

# 站点配置: (文件名, 显示名, 封面字段, 日期字段, 作者字段, 分类字段, 类型, 需代理)
#   类型: normal=普通列表; vw=article_cards; wechat=账号字典
#   需代理: 国际站点图片有 Cloudflare/WAF 需走代理; 中国站点直连即可
SOURCES = [
    ("psychology_today_news.json",   "Psychology Today 今日心理学",      "image_url", "published_date", "author", "category", "normal", True),
    ("verywellmind_therapy.json",    "Verywell Mind 非常健康心理",        "thumbnail", "published_date", "author", None, "vw", True),
    ("simplypsychology_news.json",   "Simply Psychology 简明心理学",      "image_url", "published_date", "author", "category", "normal", True),
    ("apa_press_releases.json",      "APA.org 美国心理学会",              None,        "date",           None,    None,      "normal", True),
    ("bps_news.json",                "BPS 英国心理学会",                  "image_url", "published_date", None,    "topics",  "normal", True),
    ("nimh_science_updates.json",    "NIMH 美国国家心理卫生研究院",        None,        "published_date", None,    "article_type", "normal", True),
    ("psychological_science_news.json", "Psychological Science 心理科学", "image_url", "published_date", "author", "category", "normal", True),
    ("psychology_news_org.json",     "Psychology News 心理新闻",          None,        None,             None,    None,      "normal", True),
    ("cn_psy_pku.json",              "北京大学心理与认知科学学院",        None,        None,             None,    None,      "normal", False),
    ("cn_psych_bnu.json",            "北京师范大学心理学部",              None,        None,             None,    None,      "normal", False),
    ("cn_psy_scnu.json",             "华南师范大学心理学院",              None,        None,             None,    None,      "normal", False),
    ("cn_chlip.json",                "中国轻工业出版社·心理",             None,        None,             None,    None,      "normal", False),
    ("cn_ecnupress.json",            "华东师范大学出版社·心理",           None,        None,             None,    None,      "normal", False),
    ("cn_psych_ac.json",             "中科院心理研究所",                  None,        None,             None,    None,      "normal", False),
    ("cn_xinli001.json",             "壹心理",                            None,        None,             None,    None,      "normal", False),
    ("cn_ptpress.json",              "人民邮电出版社",                    None,        None,             None,    None,      "normal", False),
    ("cn_cpsbeijing.json",           "中国心理学会",                      None,        None,             None,    None,      "normal", False),
    ("cn_wzhxlx.json",               "武志红心理",                        None,        None,             None,    None,      "normal", False),
    ("cn_zengqifeng.json",           "曾奇峰心理",                        None,        None,             None,    None,      "normal", False),
    ("wechat_channel_articles.json", "微信公众号·频道抓取（6个号）",       None,        None,             None,    "account", "wechat", False),
    ("wechat_target_articles.json",  "微信公众号·定向抓取（2个号）",       None,        None,             None,    "account", "wechat", False),
]

# 完全无正文的整文件（保留但仅记录，不生成 MD）
DROP_WHOLE = {
    "cn_jiandanxinli.json": "简单心理（40篇仅元数据，正文接口404）",
    "cn_knowyourself.json": "KnowYourself（2篇无正文，SPA无公开API）",
    "cn_bnup.json":         "北京师范大学出版社（2篇无正文）",
}


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


def flatten(d, kind):
    """把原始 JSON 拉平为文章列表"""
    items = []
    if kind == "vw":
        if isinstance(d, dict) and isinstance(d.get("article_cards"), list):
            items = list(d["article_cards"])
    elif kind == "wechat":
        if isinstance(d, dict):
            for acct, arts in d.items():
                if isinstance(arts, list):
                    for a in arts:
                        if isinstance(a, dict):
                            a = dict(a)
                            a.setdefault("account", acct)
                            items.append(a)
        elif isinstance(d, list):
            items = list(d)
    elif isinstance(d, list):
        items = list(d)
    elif isinstance(d, dict):
        items = list(d.values())
    return items


def dedup(items):
    seen, out = set(), []
    for a in items:
        k = a.get("url") or a.get("id") or a.get("href")
        if k is None:
            out.append(a)
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(a)
    return out


def body_ok(a):
    bt = (a.get("body_text") or "").strip()
    return len(bt) >= MIN_BODY, bt


def is_junk_img(url):
    if not isinstance(url, str):
        return True
    u = url.lower()
    if u.startswith("data:") or u.startswith("javascript:"):
        return True
    if not u.startswith("http"):
        return True
    for k in JUNK_KEYS:
        if k in u:
            return True
    return False


def ext_for(url):
    url = str(url or "")
    path = url.split("?")[0].lower()
    for e in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".avif"):
        if path.endswith(e):
            return e
    return ".jpg"


def sanitize(name):
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:120]


def domain_of(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return m.group(1) if m else ""


def _fetch_ok(url, referer, proxy):
    r = Fetcher.get(url, proxy=proxy if proxy else None, timeout=30, headers={"Referer": referer})
    if r.status == 200 and len(r.body) > 500 and r.body[:2] != b"<!DOCTYPE" and r.body[:2] != b"<!":
        return r.body
    return None


def download_image(url, referer, dest, use_proxy):
    """下载图片，返回 True/False。
    优先按 use_proxy 指定方式，失败后回退另一种方式（兼容热链保护/代理故障）。
    已存在的文件跳过（支持断点续跑）。
    """
    if os.path.exists(dest) and os.path.getsize(dest) > 500:
        return True
    orders = ([True, False] if use_proxy else [False, True])
    for proxy in orders:
        for attempt in range(2):
            try:
                body = _fetch_ok(url, referer, proxy)
                if body:
                    with open(dest, "wb") as f:
                        f.write(body)
                    return True
            except Exception:
                pass
            time.sleep(0.5)
    return False


# ---------------- 主流程 ----------------
records = []          # 删除记录
md_report = []        # 每个源的处理结果
total_kept = 0
total_removed = 0
total_imgs_ok = 0
total_imgs_fail = 0
fail_log = []         # 下载失败的图片

# 预计算整站删除
for fname, reason in DROP_WHOLE.items():
    if os.path.exists(os.path.join(ROOT, fname)):
        records.append({"文件": fname, "站点": reason.split("（")[0], "状态": "整站删除",
                        "篇数": len(load(fname)), "原因": reason})
        total_removed += len(load(fname))

for fname, cname, cover_f, date_f, author_f, cat_f, kind, use_proxy in SOURCES:
    src_path = os.path.join(ROOT, fname)
    if not os.path.exists(src_path):
        continue
    d = load(fname)
    items = dedup(flatten(d, kind))

    kept, removed = [], []
    for a in items:
        ok, bt = body_ok(a)
        if ok:
            kept.append(a)
        else:
            removed.append(a)

    total_kept += len(kept)
    total_removed += len(removed)

    if kept:
        removed_titles = [a.get("title", "")[:60] for a in removed[:15]]
        records.append({"文件": fname, "站点": cname, "状态": "部分删除",
                        "原始": len(items), "保留": len(kept), "删除": len(removed),
                        "删除标题示例": removed_titles,
                        "说明": "" if len(removed) <= 15 else f"共删除{len(removed)}条，仅列出前15条"})
    else:
        records.append({"文件": fname, "站点": cname, "状态": "整站删除",
                        "原始": len(items), "保留": 0, "删除": len(items),
                        "删除标题示例": [a.get("title", "")[:60] for a in removed[:15]],
                        "说明": "全部无正文"})
        if items:
            records[-1]["原因"] = "全部条目正文不足{}字".format(MIN_BODY)
        continue

    # 保存清理后的 JSON
    clean_path = os.path.join(DIR_CLEAN, fname)
    with open(clean_path, "w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)

    # ---- 收集图片任务 ----
    site_dir = os.path.join(DIR_MD, fname.replace(".json", ""))
    img_dir = os.path.join(site_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    referer = f"https://{domain_of(items[0].get('url',''))}/" if items and items[0].get("url") else ""

    tasks = []   # (img_idx, url, alt, dest, article_idx)
    mapping = {} # task index -> (url, local_name or None)
    counter = 0
    for ai, a in enumerate(kept, 1):
        # 封面
        cover = a.get(cover_f) if cover_f else None
        if isinstance(cover, str) and cover and not is_junk_img(cover):
            tasks.append([counter, cover, "封面", os.path.join(img_dir, f"a{ai:03d}_cover{ext_for(cover)}"), ai])
            counter += 1
        # 正文图片
        for bi in a.get("body_images", []) or []:
            src = bi.get("src") if isinstance(bi, dict) else None
            if not src:
                continue
            if is_junk_img(src):
                continue
            base = os.path.basename(src.split("?")[0])
            if len(base) < 4:
                base = "img"
            tasks.append([counter, src, bi.get("alt", ""), os.path.join(img_dir, f"a{ai:03d}_{counter:03d}_{sanitize(base)}"), ai])
            counter += 1

    # 去重任务（相同目标文件名）
    seen_tasks = {}
    uniq_tasks = []
    for t in tasks:
        if t[3] not in seen_tasks:
            seen_tasks[t[3]] = t
            uniq_tasks.append(t)
    tasks = uniq_tasks

    # ---- 下载图片（并发） ----
    ok_map, fail_map = {}, {}
    print(f"  [{cname}] 下载 {len(tasks)} 张图片 (代理={'是' if use_proxy else '否'})...", flush=True)
    if tasks:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(download_image, t[1], referer, t[3], use_proxy): t for t in tasks}
            done = 0
            for fut in as_completed(futs):
                t = futs[fut]
                ok = fut.result()
                if ok:
                    ok_map[t[3]] = t
                else:
                    fail_map[t[3]] = t
                    fail_log.append({"url": t[1], "dest": t[3]})
                done += 1
                if done % 50 == 0:
                    print(f"      {done}/{len(tasks)}", flush=True)
    total_imgs_ok += len(ok_map)
    total_imgs_fail += len(fail_map)

    # ---- 生成 Markdown ----
    md_lines = []
    md_lines.append(f"# {cname}")
    md_lines.append("")
    md_lines.append(f"> 数据来源: {cname} | 文章数: {len(kept)} | 图片: {len(ok_map)}（下载成功）")
    md_lines.append("")
    md_lines.append(f"> 原始文件: `{fname}` → 清理后: `{DIR_CLEAN}/{fname}`")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    for ai, a in enumerate(kept, 1):
        title = (a.get("title") or "").strip() or "(无标题)"
        md_lines.append(f"## {ai}. {title}")
        md_lines.append("")
        # 元信息
        meta = []
        if cat_f and a.get(cat_f):
            v = a[cat_f]
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            meta.append(f"分类: {v}")
        if date_f and a.get(date_f):
            meta.append(f"日期: {a[date_f]}")
        if author_f and a.get(author_f):
            meta.append(f"作者: {a[author_f]}")
        if a.get("source"):
            meta.append(f"来源: {a['source']}")
        url = a.get("url") or ""
        if meta:
            md_lines.append("> " + " | ".join(meta))
        if url:
            md_lines.append(f"> 原文: {url}")
        md_lines.append("")

        # 封面图
        cover_local = os.path.join(img_dir, f"a{ai:03d}_cover{ext_for(a.get(cover_f) or '')}") if cover_f and a.get(cover_f) else None
        if cover_local and cover_local in ok_map:
            md_lines.append(f"![封面](images/{os.path.basename(cover_local)})")
            md_lines.append("")

        # 正文
        body = (a.get("body_text") or "").strip()
        md_lines.append(body)
        md_lines.append("")

        # 正文图片（非封面）
        imgs_local = []
        for t in tasks:
            if t[4] == ai and t[2] != "封面":
                imgs_local.append(t)
        if imgs_local:
            for t in imgs_local:
                local = t[3]
                if local in ok_map:
                    md_lines.append(f"![{t[2] or 'image'}](images/{os.path.basename(local)})")
                else:
                    md_lines.append(f"![{t[2] or 'image'}]({t[1]})")
            md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    md_path = os.path.join(site_dir, fname.replace(".json", "") + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    md_report.append({
        "站点": cname, "文件": fname, "保留": len(kept), "删除": len(removed),
        "图片任务": len(tasks), "图片成功": len(ok_map), "图片失败": len(fail_map),
        "markdown": md_path, "清理JSON": clean_path,
    })
    print(f"  ✅ {cname}: 保留{len(kept)} 删除{len(removed)} 图片{len(ok_map)}/{len(tasks)}", flush=True)

# ---------------- 记录文件 ----------------
with open(os.path.join(DIR_REC, "删除记录.json"), "w", encoding="utf-8") as f:
    json.dump(records, f, ensure_ascii=False, indent=2)

with open(os.path.join(DIR_REC, "图片下载失败.json"), "w", encoding="utf-8") as f:
    json.dump(fail_log, f, ensure_ascii=False, indent=2)

# 删除记录 markdown
rm_lines = ["# 删除记录（基本无正文部分）", "",
            f"> 处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
            f"> 判定标准: 正文少于 {MIN_BODY} 字的条目视为'基本无正文'，予以删除",
            "", "## 删除清单", "", "| 站点 | 状态 | 原始 | 保留 | 删除 |", "|---|---|---|---|---|"]
for r in records:
    rm_lines.append(f"| {r['站点']} | {r['状态']} | {r.get('原始', r.get('篇数',''))} | {r.get('保留','-')} | {r.get('删除', r.get('篇数',''))} |")
rm_lines.append("")
rm_lines.append("## 明细")
rm_lines.append("")
for r in records:
    rm_lines.append(f"### {r['站点']}（{r['状态']}）")
    if r.get("原因"):
        rm_lines.append(f"- 原因: {r['原因']}")
    if r.get("说明"):
        rm_lines.append(f"- {r['说明']}")
    if r.get("删除标题示例"):
        rm_lines.append("- 删除条目示例:")
        for t in r["删除标题示例"]:
            rm_lines.append(f"  - {t}")
    rm_lines.append("")
with open(os.path.join(DIR_REC, "删除记录.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(rm_lines))

# 处理总结
sum_lines = ["# 处理总结", "",
             f"> 处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
             f"- 总原始条目: {total_kept + total_removed}", f"- 保留条目: {total_kept}",
             f"- 删除条目: {total_removed}", f"- 图片下载成功: {total_imgs_ok}",
             f"- 图片下载失败: {total_imgs_fail}", "", "## 各站点处理结果", "",
             "| 站点 | 保留 | 删除 | 图片成功/任务 | Markdown |", "|---|---|---|---|---|"]
for r in md_report:
    rel_md = r["markdown"].replace("\\", "/")
    sum_lines.append(f"| {r['站点']} | {r['保留']} | {r['删除']} | {r['图片成功']}/{r['图片任务']} | {rel_md} |")
sum_lines.append("")
sum_lines.append(f"## 整站删除（无正文）")
sum_lines.append("")
for r in records:
    if r["状态"] == "整站删除":
        sum_lines.append(f"- {r['站点']}: {r.get('原因', '')}")
sum_lines.append("")
sum_lines.append(f"## 图片下载失败（{total_imgs_fail}）")
sum_lines.append("")
if fail_log:
    for fl in fail_log[:50]:
        sum_lines.append(f"- {fl['url']}")
    if len(fail_log) > 50:
        sum_lines.append(f"- ... 共{len(fail_log)}条")
else:
    sum_lines.append("无")
with open(os.path.join(DIR_REC, "处理总结.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(sum_lines))

print("\n" + "=" * 50)
print(f"总保留: {total_kept}  总删除: {total_removed}")
print(f"图片成功: {total_imgs_ok}  图片失败: {total_imgs_fail}")
print(f"记录: {DIR_REC}/  | 清理JSON: {DIR_CLEAN}/  | Markdown: {DIR_MD}/")
print("完成!")
