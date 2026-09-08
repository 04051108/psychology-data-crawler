# -*- coding: utf-8 -*-
"""
把 output_clean 中的每篇文章单独保存为一个 .txt（Markdown 格式）文件
结构：
  output_txt/
    <站点显示名>/
      images/                # 从 output_md 复制该站点已下载的图片
      <序号>_<标题>.txt       # 每篇一文件
"""
import json, os, re, shutil

DIR_CLEAN = "output_clean"
DIR_MD = "output_md"
DIR_TXT = "output_txt"

os.makedirs(DIR_TXT, exist_ok=True)

# 站点配置: (文件名, 显示名, 封面字段, 日期字段, 作者字段, 分类字段)
SOURCES = [
    ("psychology_today_news.json",   "Psychology Today 今日心理学",      "image_url", "published_date", "author", "category"),
    ("verywellmind_therapy.json",    "Verywell Mind 非常健康心理",        "thumbnail", "published_date", "author", None),
    ("simplypsychology_news.json",   "Simply Psychology 简明心理学",      "image_url", "published_date", "author", "category"),
    ("apa_press_releases.json",      "APA.org 美国心理学会",              None,        "date",           None,    None),
    ("bps_news.json",                "BPS 英国心理学会",                  "image_url", "published_date", None,    "topics"),
    ("nimh_science_updates.json",    "NIMH 美国国家心理卫生研究院",        None,        "published_date", None,    "article_type"),
    ("psychological_science_news.json", "Psychological Science 心理科学", "image_url", "published_date", "author", "category"),
    ("psychology_news_org.json",     "Psychology News 心理新闻",          None,        None,             None,    None),
    ("cn_psy_pku.json",              "北京大学心理与认知科学学院",        None,        None,             None,    None),
    ("cn_psych_bnu.json",            "北京师范大学心理学部",              None,        None,             None,    None),
    ("cn_psy_scnu.json",             "华南师范大学心理学院",              None,        None,             None,    None),
    ("cn_chlip.json",                "中国轻工业出版社·心理",             None,        None,             None,    None),
    ("cn_ecnupress.json",            "华东师范大学出版社·心理",           None,        None,             None,    None),
    ("cn_psych_ac.json",             "中科院心理研究所",                  None,        None,             None,    None),
    ("cn_xinli001.json",             "壹心理",                            None,        None,             None,    None),
    ("cn_ptpress.json",              "人民邮电出版社",                    None,        None,             None,    None),
    ("cn_cpsbeijing.json",           "中国心理学会",                      None,        None,             None,    None),
    ("cn_zengqifeng.json",           "曾奇峰心理",                        None,        None,             None,    None),
    ("wechat_channel_articles.json", "微信公众号·频道抓取（6个号）",       None,        None,             None,    "account"),
    ("wechat_target_articles.json",  "微信公众号·定向抓取（2个号）",       None,        None,             None,    "account"),
]


def fmt_meta(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x)
    return str(v) if v is not None else ""


def safe_name(s, maxlen=60):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s[:maxlen] or "无标题"


total_files = 0
total_imgs_copied = 0

for fname, cname, cover_f, date_f, author_f, cat_f in SOURCES:
    src = os.path.join(DIR_CLEAN, fname)
    if not os.path.exists(src):
        continue
    arts = json.load(open(src, encoding="utf-8"))
    if not arts:
        continue

    src_key = fname.replace(".json", "")
    # 站点输出目录
    site_dir = os.path.join(DIR_TXT, cname)
    os.makedirs(site_dir, exist_ok=True)

    # 复制图片目录（output_md 中该站点已下载的图片）
    img_src = os.path.join(DIR_MD, src_key, "images")
    img_dst = os.path.join(site_dir, "images")
    copied = 0
    if os.path.isdir(img_src):
        if not os.path.isdir(img_dst):
            shutil.copytree(img_src, img_dst)
            copied = len(os.listdir(img_dst))
        else:
            copied = len(os.listdir(img_dst))
    total_imgs_copied += copied

    n = 0
    for ai, a in enumerate(arts, 1):
        title = (a.get("title") or "").strip() or "(无标题)"
        lines = []
        lines.append(f"# {title}")
        lines.append("")
        meta = []
        if cat_f and a.get(cat_f):
            meta.append(f"分类: {fmt_meta(a[cat_f])}")
        if date_f and a.get(date_f):
            meta.append(f"日期: {fmt_meta(a[date_f])}")
        if author_f and a.get(author_f):
            meta.append(f"作者: {fmt_meta(a[author_f])}")
        if a.get("source"):
            meta.append(f"来源: {a['source']}")
        if meta:
            lines.append("> " + " | ".join(meta))
        url = a.get("url") or ""
        if url:
            lines.append(f"> 原文: {url}")
        lines.append("")

        # 封面图
        if os.path.isdir(img_dst):
            covers = [f for f in os.listdir(img_dst) if f.startswith(f"a{ai:03d}_cover")]
            if covers:
                covers.sort()
                lines.append(f"![封面](images/{covers[0]})")
                lines.append("")

        # 正文
        body = (a.get("body_text") or "").strip()
        if body:
            lines.append(body)
            lines.append("")

        # 正文图片（按文件名排序）
        if os.path.isdir(img_dst):
            imgs = sorted(f for f in os.listdir(img_dst)
                          if f.startswith(f"a{ai:03d}_") and "_cover" not in f)
            if imgs:
                for im in imgs:
                    lines.append(f"![image](images/{im})")
                lines.append("")

        txt_path = os.path.join(site_dir, f"{ai:03d}_{safe_name(title)}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        n += 1
        total_files += 1

    print(f"  {cname}: {n} 篇 | 图片 {copied}")

print(f"\n✅ 完成！共 {total_files} 个文件, 复制图片 {total_imgs_copied} 张")
print(f"  输出目录: {os.path.abspath(DIR_TXT)}")
