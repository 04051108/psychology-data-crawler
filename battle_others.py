"""
逐个攻克剩余站点
"""
from scrapling.fetchers import Fetcher, DynamicFetcher
import json, os, re, time, ssl, urllib.request

OUT = "output"
os.makedirs(OUT, exist_ok=True)
Fetcher.configure(adaptive=True, huge_tree=True)
DynamicFetcher.configure(adaptive=True, huge_tree=True)

def save(name, articles):
    path = os.path.join(OUT, f"cn_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    wb = sum(1 for a in articles if a.get("body_text"))
    ti = sum(len(a.get("body_images",[])) for a in articles)
    print(f"  💾 {path} | {len(articles)}篇 正文{wb} 图片{ti}")

# ====== 1. 人邮出版社 - 找tenantID ======
print(f"\n{'='*50}\n1. 人邮出版社 - 找tenantID\n{'='*50}")
def find_tenant(page):
    import time, json
    time.sleep(3)
    r = page.evaluate("""() => {
        const scripts = document.querySelectorAll('script');
        let allText = '';
        scripts.forEach(s => { allText += (s.textContent||'') + '\\n'; });
        const matches = allText.match(/tenant[^}]*}|"tenantId"[^,]+|tenantID[^,]+/gi) || [];
        // 找所有可能的配置
        const configs = [];
        (allText.match(/\\{[^}]*tenant[^}]*\\}/gi)||[]).forEach(m => configs.push(m.slice(0,200)));
        return { configs: configs.slice(0,10), matches: matches.slice(0,10) };
    }""")
    with open('_tmp.json','w',encoding='utf-8') as f:
        json.dump(r,f,ensure_ascii=False)

DynamicFetcher.fetch("https://www.ptpress.com.cn", headless=True, timeout=30000,
    disable_resources=False, network_idle=True, load_dom=True, page_action=find_tenant)

if os.path.exists('_tmp.json'):
    with open('_tmp.json', encoding='utf-8') as f:
        d = json.load(f)
    os.remove('_tmp.json')
    for m in d.get('matches',[]):
        print(f"  Match: {m}")
    for c in d.get('configs',[]):
        print(f"  Config: {c}")


# ====== 2. KnowYourself - 深扒Next.js ======
print(f"\n{'='*50}\n2. KnowYourself - 深扒Next.js\n{'='*50}")
ssl._create_default_https_context = ssl._create_unverified_context
try:
    r = urllib.request.urlopen("https://www.knowyourself.cc", timeout=15)
    html = r.read().decode('utf-8', errors='replace')
    # 找出所有JS文件
    js_files = re.findall(r'/_next/static/chunks/pages/[^"\']+\.js', html)
    print(f"页面JS文件: {len(js_files)}")
    for js in js_files[:10]:
        print(f"  {js}")

    # 找 _next/data
    builds = re.findall(r'/_next/static/[^"\']*buildId[^"\']*|/_next/data/[^"\']+', html)
    for b in builds:
        print(f"  Build: {b}")

    # 看JS bundle中的API
    for js_path in js_files[:5]:
        url = f"https://www.knowyourself.cc{js_path}"
        try:
            js = urllib.request.urlopen(url, timeout=10).read().decode('utf-8', errors='replace')
            apis = re.findall(r'["\'](/api/[^"\']+)["\']', js)
            if apis:
                print(f"\n  {js_path}:")
                for a in set(apis):
                    print(f"    API: {a}")
        except:
            pass
except Exception as e:
    print(f"  Error: {e}")


# ====== 3. 武志红 - 浏览器导航hash路由 ======
print(f"\n{'='*50}\n3. 武志红 - hash路由\n{'='*50}")
def navigate_wzh(page):
    import time, json
    time.sleep(3)
    # 尝试点击导航链接
    all_content = {}
    routes = ['#/?channelId=99', '#/wwyy/zixun?channelId=99',
              '#/wwyy/detail?channelId=99', '#/wwyy/joinus?channelId=99']
    for route in routes:
        try:
            page.goto(f"http://www.wzhxlx.com/{route}", wait_until='networkidle')
            time.sleep(3)
            text = page.evaluate("() => document.body.innerText")
            all_content[route] = text.strip()[:200]
        except:
            pass
    # 点击所有可点击的
    page.goto("http://www.wzhxlx.com", wait_until='networkidle')
    time.sleep(3)
    for i in range(5):
        try:
            links = page.query_selector_all('a[href*="#/"]')
            if links and len(links) > i:
                links[i].click()
                time.sleep(2)
                text = page.evaluate("() => document.body.innerText")
                all_content[f"click_{i}"] = text.strip()[:200]
        except:
            pass

    with open('_tmp.json','w',encoding='utf-8') as f:
        json.dump(all_content, f, ensure_ascii=False)

DynamicFetcher.fetch("http://www.wzhxlx.com", headless=True, timeout=60000,
    disable_resources=False, network_idle=True, load_dom=True,
    page_action=navigate_wzh)

if os.path.exists('_tmp.json'):
    with open('_tmp.json', encoding='utf-8') as f:
        d = json.load(f)
    os.remove('_tmp.json')
    for route, text in d.items():
        print(f"  {route}: {len(text)}c -> {text[:100]}")

print(f"\n✅ 完成!")
