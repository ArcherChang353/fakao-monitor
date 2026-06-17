#!/usr/bin/env python3
"""
微博API各端点直接验证脚本
使用本地缓存的token直接测试
"""
import json
import time
import urllib.request
import urllib.parse

# 从缓存加载token
with open("weibo_search_cache.json", "r") as f:
    cache = json.load(f)
token = cache["token"]
print(f"📌 使用缓存token: {token[:20]}... (缓存于 {time.strftime('%H:%M:%S', time.localtime(cache['cached_at']))})")
print("=" * 70)

# ===== 端点定义 =====
SEARCH_ENDPOINT = "https://open-im.api.weibo.com/open/wis/search_query"
STATUS_API = "https://open-im.api.weibo.com/open/weibo/status_show"
USER_TIMELINE_API = "https://open-im.api.weibo.com/open/weibo/statuses/user_timeline"

LIJIA_UID = "2510840"

# ===== Test 1: user_timeline 李佳 =====
print("\n" + "=" * 50)
print("Test 1: user_timeline — 李佳(uid=2510840)")
print("=" * 50)

try:
    url = f"{USER_TIMELINE_API}?token={token}&uid={LIJIA_UID}&count=5"
    resp = urllib.request.urlopen(url, timeout=15)
    result = json.loads(resp.read())
    code = result.get("code")
    msg = result.get("message", "")

    if code != 0:
        print(f"   ❌ code={code} msg={msg}")
        # 打印完整响应帮助排查
        resp_str = json.dumps(result, ensure_ascii=False)
        print(f"   完整响应({len(resp_str)}字符):")
        print(f"   {resp_str[:600]}")
    else:
        posts = result.get("data", {}).get("statuses", [])
        print(f"   ✅ 成功! 拉取 {len(posts)} 条帖子")
        for i, p in enumerate(posts[:5]):
            mid = p.get("mid") or p.get("id", "?")
            text = (p.get("longText") or p.get("text", ""))[:150].replace("\n", " ")
            created = p.get("created_at", "?")
            user = p.get("user", {}).get("screen_name", "?")
            pics = len(p.get("pic_urls", []))
            has_long = bool(p.get("longText"))
            print(f"   [{i+1}] mid={mid} | {created} | @{user}")
            print(f"       图片:{pics} longText:{has_long}")
            print(f"       内容: {text}...")
except Exception as e:
    print(f"   ❌ 异常: {e}")

# ===== Test 2: search_query 智搜 李佳 =====
print("\n" + "=" * 50)
print("Test 2: search_query — '行政法李佳 每日一题'")
print("=" * 50)

query = "行政法李佳 每日一题"
try:
    url = f"{SEARCH_ENDPOINT}?query={urllib.parse.quote(query)}&token={token}"
    resp = urllib.request.urlopen(url, timeout=30)
    result = json.loads(resp.read())
    code = result.get("code")
    msg = result.get("message", "")

    if code != 0:
        print(f"   ❌ code={code} msg={msg}")
        print(f"   完整响应: {json.dumps(result, ensure_ascii=False)[:400]}")
    else:
        posts = result.get("data", {}).get("posts", [])
        print(f"   ✅ 搜索结果: {len(posts)} 条")
        for i, p in enumerate(posts[:5]):
            mid = p.get("mblogid") or p.get("id", "?")
            text = p.get("text", "")[:150].replace("\n", " ")
            user = p.get("user", {}).get("screen_name", "?")
            created = p.get("created_at", "?")
            has_answer = "答案" in text
            has_daily = "每日一题" in text
            print(f"   [{i+1}] mid={mid} | {created} | @{user}")
            print(f"       每日一题:{has_daily} 答案:{has_answer}")
            print(f"       内容: {text}...")
except Exception as e:
    print(f"   ❌ 异常: {e}")

# ===== Test 3: status_show 通过智搜拿到的mblogid =====
print("\n" + "=" * 50)
print("Test 3: status_show — 获取单条帖子完整内容")
print("=" * 50)

try:
    url = f"{SEARCH_ENDPOINT}?query={urllib.parse.quote(query)}&token={token}"
    resp = urllib.request.urlopen(url, timeout=30)
    result = json.loads(resp.read())
    if result.get("code") == 0:
        posts = result.get("data", {}).get("posts", [])
        for p in posts:
            mid = p.get("mblogid")
            if mid:
                print(f"   用 mblogid={mid} 调 status_show...")
                url2 = f"{STATUS_API}?token={token}&id={mid}"
                resp2 = urllib.request.urlopen(url2, timeout=15)
                result2 = json.loads(resp2.read())
                code2 = result2.get("code")
                if code2 != 0:
                    print(f"   ❌ code={code2} msg={result2.get('message','')}")
                else:
                    post = result2.get("data", {})
                    text = post.get("longText") or post.get("text", "")
                    has_long = bool(post.get("longText"))
                    pics = post.get("pic_urls", [])
                    print(f"   ✅ 帖子详情获取成功")
                    print(f"      longText存在: {has_long}")
                    print(f"      text长度: {len(post.get('text', ''))}")
                    print(f"      longText长度: {len(post.get('longText', ''))}")
                    print(f"      图片数: {len(pics)}")
                    print(f"      完整内容:\n{text[:500]}")
                break
except Exception as e:
    print(f"   ❌ 异常: {e}")

# ===== Test 4: user_timeline 其他老师 =====
print("\n" + "=" * 50)
print("Test 4: user_timeline 批量测试其他老师")
print("=" * 50)

test_uids = {
    "柏浪涛": "3546604065514065",
    "孟献贵": "3546614072148177",
    "戴鹏":   "3546614786165583",
    "左宁":   "3546613221067578",
    "郄鹏恩": "3546611874650912",
    "马峰":   "3546607071864863",
    "刘安琪": "3546605622023053",
}

for name, uid in test_uids.items():
    try:
        url = f"{USER_TIMELINE_API}?token={token}&uid={uid}&count=3"
        resp = urllib.request.urlopen(url, timeout=15)
        result = json.loads(resp.read())
        code = result.get("code")
        if code != 0:
            msg = result.get("message", "")
            print(f"   ❌ {name}(uid={uid}): code={code} msg={msg[:100]}")
        else:
            count = len(result.get("data", {}).get("statuses", []))
            print(f"   ✅ {name}(uid={uid}): {count} 条帖子")
    except Exception as e:
        print(f"   ❌ {name}(uid={uid}): 异常 {e}")

# ===== Test 5: 用智搜搜索查李佳最新题号 =====
print("\n" + "=" * 50)
print("Test 5: 智搜查李佳最新题目（题号统计）")
print("=" * 50)

import re
try:
    url = f"{SEARCH_ENDPOINT}?query={urllib.parse.quote('李佳 每日一题')}&token={token}"
    resp = urllib.request.urlopen(url, timeout=30)
    result = json.loads(resp.read())
    if result.get("code") == 0:
        posts = result.get("data", {}).get("posts", [])
        nums = []
        for p in posts:
            text = p.get("text", "")
            m = re.search(r'每日一题[^\d]*(\d+)', text)
            if m:
                nums.append(int(m.group(1)))
        nums.sort(reverse=True)
        print(f"   找到 {len(nums)} 条含题号的帖子")
        print(f"   题号范围: {nums[-1] if nums else 'N/A'} ~ {nums[0] if nums else 'N/A'}")
        print(f"   最新5个题号: {nums[:5]}")
except Exception as e:
    print(f"   ❌ 异常: {e}")

print("\n" + "=" * 70)
print("🏁 全部验证完成")
print("=" * 70)
