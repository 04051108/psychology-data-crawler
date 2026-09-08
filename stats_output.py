# -*- coding: utf-8 -*-
"""
统计 output/ 目录下所有爬取结果
"""
import json, os

OUT = "output"


def load(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt(n):
    return f"{n:,}"


def count_text_images(items, img_fields=("body_images",)):
    """统计正文数量、正文长度、图片数
    img_fields: 图片字段名，body_images 是列表，其他如 image_url/thumbnail/cover 是单个字符串或列表
    """
    wb = 0
    chars = 0
    imgs = 0
    for a in items:
        bt = a.get("body_text", "") or ""
        if bt:
            wb += 1
            chars += len(bt)
        for f in img_fields:
            v = a.get(f)
            if isinstance(v, list):
                imgs += len(v)
            elif isinstance(v, str) and v.strip() and v.startswith(("http", "/")):
                imgs += 1
    return wb, chars, imgs


def collect_flat(d):
    """把 dict/list 结构拉平成文章列表（递归处理 article_cards / account dict）"""
    items = []
    if isinstance(d, dict):
        if "article_cards" in d and isinstance(d["article_cards"], list):
            items.extend(d["article_cards"])
        for v in d.values():
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict) and ("body_text" in x or "title" in x):
                        items.append(x)
    elif isinstance(d, list):
        for x in d:
            if isinstance(x, dict):
                items.append(x)
    return items


def dedup(items, key="url"):
    seen = set()
    out = []
    for a in items:
        k = a.get(key) or a.get("id") or a.get("href")
        if k is None:
            out.append(a)  # 无标识字段，保留
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(a)
    return out


rows = []

# ================= 国际站 =================
print("=" * 72)
print("【国际心理学资讯站点】")
print("=" * 72)

pt = load(os.path.join(OUT, "psychology_today_news.json"))
if pt:
    wb, chars, imgs = count_text_images(pt, img_fields=("image_url",))
    rows.append(("Psychology Today (今日心理学)", len(pt), wb, chars, imgs))
    print(f"  Psychology Today (今日心理学)   : {fmt(len(pt))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

vw = load(os.path.join(OUT, "verywellmind_therapy.json"))
if vw:
    cards = vw.get("article_cards", [])
    wb, chars, imgs = count_text_images(cards, img_fields=("thumbnail", "body_images"))
    rows.append(("Verywell Mind (非常健康心理)", len(cards), wb, chars, imgs))
    print(f"  Verywell Mind (非常健康心理)    : {fmt(len(cards))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

sp = load(os.path.join(OUT, "simplypsychology_news.json"))
if sp:
    wb, chars, imgs = count_text_images(sp)
    rows.append(("Simply Psychology (简明心理学)", len(sp), wb, chars, imgs))
    print(f"  Simply Psychology (简明心理学)   : {fmt(len(sp))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

apa = load(os.path.join(OUT, "apa_press_releases.json"))
if apa:
    wb, chars, imgs = count_text_images(apa)
    rows.append(("APA.org (美国心理学会)", len(apa), wb, chars, imgs))
    print(f"  APA.org (美国心理学会)           : {fmt(len(apa))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

bps = load(os.path.join(OUT, "bps_news.json"))
if bps:
    wb, chars, imgs = count_text_images(bps)
    rows.append(("BPS (英国心理学会)", len(bps), wb, chars, imgs))
    print(f"  BPS (英国心理学会)               : {fmt(len(bps))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

nimh = load(os.path.join(OUT, "nimh_science_updates.json"))
if nimh:
    wb, chars, imgs = count_text_images(nimh)
    rows.append(("NIMH (美国国家心理卫生研究院)", len(nimh), wb, chars, imgs))
    print(f"  NIMH (美国家心理卫生研究院)      : {fmt(len(nimh))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

ps = load(os.path.join(OUT, "psychological_science_news.json"))
if ps:
    wb, chars, imgs = count_text_images(ps)
    rows.append(("Psychological Science (心理科学)", len(ps), wb, chars, imgs))
    print(f"  Psychological Science (心理科学)  : {fmt(len(ps))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

pn = load(os.path.join(OUT, "psychology_news_org.json"))
if pn:
    wb, chars, imgs = count_text_images(pn)
    rows.append(("Psychology News (心理新闻)", len(pn), wb, chars, imgs))
    print(f"  Psychology News (心理新闻)        : {fmt(len(pn))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

# ================= 中国站 =================
print()
print("=" * 72)
print("【中国心理学站点】")
print("=" * 72)

cn_sites = [
    ("cn_psy_pku.json",      "北京大学心理与认知科学学院"),
    ("cn_psych_bnu.json",    "北京师范大学心理学部"),
    ("cn_psy_scnu.json",     "华南师范大学心理学院"),
    ("cn_chlip.json",        "中国轻工业出版社·心理"),
    ("cn_ecnupress.json",    "华东师范大学出版社·心理"),
    ("cn_psych_ac.json",     "中科院心理研究所"),
    ("cn_xinli001.json",     "壹心理"),
    ("cn_jiandanxinli.json", "简单心理"),
    ("cn_ptpress.json",      "人民邮电出版社"),
    ("cn_cpsbeijing.json",   "中国心理学会"),
    ("cn_wzhxlx.json",       "武志红心理"),
    ("cn_knowyourself.json", "KnowYourself"),
    ("cn_bnup.json",         "北京师范大学出版社"),
    ("cn_zengqifeng.json",   "曾奇峰心理"),
]

for fname, cname in cn_sites:
    d = load(os.path.join(OUT, fname))
    if not d:
        continue
    items = collect_flat(d)
    items = dedup(items)
    extra_img = ("cover",) if fname == "cn_jiandanxinli.json" else ()
    wb, chars, imgs = count_text_images(items, img_fields=("body_images",) + extra_img)
    rows.append((cname, len(items), wb, chars, imgs))
    flag = ""
    if len(items) == 0:
        flag = " [空]"
    elif wb == 0:
        flag = " [仅元数据]"
    print(f"  {cname:<22}: {fmt(len(items))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}{flag}")

# ================= 微信公众号 =================
print()
print("=" * 72)
print("【微信公众号】")
print("=" * 72)

wx_channel = load(os.path.join(OUT, "wechat_channel_articles.json"))
wx_all_items = []
if isinstance(wx_channel, dict):
    for acct, arts in wx_channel.items():
        if isinstance(arts, list):
            wx_all_items.extend(arts)
    wx_all_items = dedup(wx_all_items)
    wb, chars, imgs = count_text_images(wx_all_items)
    rows.append(("微信公众号·频道抓取（6个号）", len(wx_all_items), wb, chars, imgs))
    print(f"  微信公众号·频道抓取（6个号）      : {fmt(len(wx_all_items))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")
    for acct, arts in wx_channel.items():
        wbb, charss, imgss = count_text_images(arts)
        print(f"      - {acct}: {len(arts)} 篇 | 正文 {wbb} | 字数 {fmt(charss)} | 图片 {fmt(imgss)}")

wx_target = load(os.path.join(OUT, "wechat_target_articles.json"))
if wx_target:
    wb, chars, imgs = count_text_images(wx_target)
    rows.append(("微信公众号·定向抓取（2个号）", len(wx_target), wb, chars, imgs))
    print(f"  微信公众号·定向抓取（2个号）      : {fmt(len(wx_target))} 篇 | 正文 {wb} | 字数 {fmt(chars)} | 图片 {fmt(imgs)}")

# ================= 汇总 =================
print()
print("=" * 72)
print("【汇总】")
print("=" * 72)
tot_a = sum(r[1] for r in rows)
tot_wb = sum(r[2] for r in rows)
tot_c = sum(r[3] for r in rows)
tot_i = sum(r[4] for r in rows)
print(f"  总条目        : {fmt(tot_a)}")
print(f"  含正文条目    : {fmt(tot_wb)}")
print(f"  总正文字数    : {fmt(tot_c)}")
print(f"  总图片数      : {fmt(tot_i)}")

# 输出CSV方便查看
with open("output_stats.csv", "w", encoding="utf-8-sig") as f:
    f.write("站点,条目数,含正文,正文字数,图片数\n")
    for name, a, wb, c, i in rows:
        f.write(f"{name},{a},{wb},{c},{i}\n")
    f.write(f"合计,{tot_a},{tot_wb},{tot_c},{tot_i}\n")
print(f"\n已保存 output_stats.csv")
