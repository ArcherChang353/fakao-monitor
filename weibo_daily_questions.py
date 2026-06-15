#!/usr/bin/env python3
"""
法考每日一题抓取 v3.0 — 真实帖子抓取版
核心改进：不再使用智搜AI摘要，而是通过hashtag搜索→提取mblogid→status_show获取真实帖子内容
8位老师各自配置最佳hashtag搜索词，自动匹配Q&A帖子对
每天8:30 GMT+8 执行，云端运行
"""

import os
import re
import json
import smtplib
import time
import urllib.request
import urllib.parse
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

# ============ 配置 ============
QQ_EMAIL = "jewelljaja@foxmail.com"
QQ_SMTP_CODE = os.environ["QQ_SMTP_CODE"]
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

WEIBO_APP_ID = os.environ["WEIBO_APP_ID"]
WEIBO_APP_SECRET = os.environ["WEIBO_APP_SECRET"]

TOKEN_ENDPOINT = "https://open-im.api.weibo.com/open/auth/ws_token"
SEARCH_ENDPOINT = "https://open-im.api.weibo.com/open/wis/search_query"
STATUS_API = "https://open-im.api.weibo.com/open/weibo/status_show"

# ============ 8科目配置（真实帖子抓取版） ============
# 每位老师配置：hashtag搜索词 + 教师筛选名 + 替代搜索词（fallback）
TEACHER_SLOTS = {
    "行政法": {
        "display_name": "李佳（行政法）",
        "color": "#e74c3c",
        "hashtag_query": "佳佳每日一题",
        "teacher_filter": "行政法李佳",
        "fallback_queries": [
            {"name": "李佳", "label": "李佳（行政法）", "query": "行政法李佳 每日一题"},
        ],
    },
    "刑法": {
        "display_name": "柏浪涛（刑法）",
        "color": "#e67e22",
        "hashtag_query": "柏浪涛每日一题",
        "teacher_filter": "柏浪涛",
        "fallback_queries": [
            {"name": "柏浪涛", "label": "柏浪涛（刑法）", "query": "柏浪涛 每日一题"},
        ],
    },
    "民法": {
        "display_name": "孟献贵（民法）",
        "color": "#2980b9",
        "hashtag_query": "孟献贵每日一题",
        "teacher_filter": "孟献贵",
        "fallback_queries": [
            {"name": "孟献贵", "label": "孟献贵（民法）",              "query": "孟献贵 每日一题"},
            {"name": "钟秀勇", "label": "钟秀勇（民法·瑞达）📡替代",  "query": "钟秀勇 民法"},
            {"name": "张翔",   "label": "张翔（民法·厚大）📡替代",    "query": "张翔 民法"},
        ],
    },
    "民诉": {
        "display_name": "戴鹏（民诉）",
        "color": "#8e44ad",
        "hashtag_query": "戴鹏每日一题",
        "teacher_filter": "戴鹏",
        "fallback_queries": [
            {"name": "戴鹏",   "label": "戴鹏（民诉）",               "query": "戴鹏 每日一题"},
            {"name": "韩心怡", "label": "韩心怡（民诉·瑞达）📡替代",  "query": "韩心怡 民诉法"},
        ],
    },
    "刑诉": {
        "display_name": "左宁（刑诉）",
        "color": "#27ae60",
        "hashtag_query": "左宁每日一题",
        "teacher_filter": "左宁",
        "fallback_queries": [
            {"name": "左宁", "label": "左宁（刑诉）", "query": "左宁 每日一题"},
        ],
    },
    "三国法": {
        "display_name": "杨帆（三国法）",
        "color": "#16a085",
        "hashtag_query": "杨帆三国法 每日一题",
        "teacher_filter": "杨帆",
        "fallback_queries": [
            {"name": "杨帆", "label": "杨帆（三国法）",                "query": "杨帆 每日一题"},
            {"name": "殷敏", "label": "殷敏（三国法·厚大）📡替代",    "query": "殷敏 三国法"},
        ],
    },
    "理论法": {
        "display_name": "马峰（理论法）",
        "color": "#2c3e50",
        "hashtag_query": "马峰每日一题",
        "teacher_filter": "马峰",
        "fallback_queries": [
            {"name": "马峰",   "label": "马峰（理论法）",                "query": "马峰 每日一题"},
            {"name": "杜洪波", "label": "杜洪波（理论法）📡替代",       "query": "杜洪波 法考"},
            {"name": "宋光明", "label": "宋光明（理论法·瑞达）📡替代",  "query": "宋光明 理论法"},
        ],
    },
    "商经知": {
        "display_name": "郄鹏恩（商经知）",
        "color": "#d35400",
        "hashtag_query": "郄鹏恩每日一题",
        "teacher_filter": "郄鹏恩",
        "fallback_queries": [
            {"name": "郄鹏恩", "label": "郄鹏恩（商经知）", "query": "郄鹏恩 每日一题"},
        ],
    },
}

CACHE_FILE = "weibo_search_cache.json"
POST_CACHE_FILE = "weibo_post_cache.json"  # 缓存已抓取的帖子内容（24小时有效）

# API频率限制: 100次/小时
API_DELAY = 0.6
MAX_POSTS_TO_FETCH = 12  # 每个hashtag搜索最多抓取的帖子数


# ============ 微博API ============

def get_weibo_token():
    """获取微博API访问令牌（缓存避免重复请求）"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
            cached_at = cache.get("cached_at", 0)
            expire_in = cache.get("expire_in", 0)
            if time.time() - cached_at < expire_in - 3600:
                return cache.get("token")
        except Exception:
            pass

    req = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=json.dumps({
            "app_id": WEIBO_APP_ID,
            "app_secret": WEIBO_APP_SECRET,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if data.get("code") != 0:
            raise Exception(f"Token获取失败: {data.get('message', 'unknown')}")

        token_data = data["data"]
        token = token_data["token"]
        expire_in = token_data.get("expire_in", 525600)

        with open(CACHE_FILE, "w") as f:
            json.dump({
                "token": token,
                "cached_at": time.time(),
                "expire_in": expire_in,
            }, f)

        return token
    except urllib.error.HTTPError as e:
        raise Exception(f"Token HTTP错误: {e.code} {e.reason}")
    except Exception as e:
        raise Exception(f"Token获取异常: {e}")


def search_zhisou(query, token):
    """调用微博智搜API，返回原始数据（含wbCustomBlock引用）"""
    url = f"{SEARCH_ENDPOINT}?query={urllib.parse.quote(query)}&token={token}"

    try:
        resp = urllib.request.urlopen(url, timeout=30)
        data = json.loads(resp.read())
        if data.get("code") != 0:
            return None

        result = data.get("data", {})
        if result.get("noContent") or not result.get("completed"):
            return None

        return result
    except Exception as e:
        print(f"      搜索异常: {e}")
        return None


def extract_mblogids(zhisou_data):
    """从智搜返回数据中提取所有引用的mblogid，按ID大小降序（越大越新）"""
    mblogids = set()
    msg = zhisou_data.get("msg", "")

    # 从 wbCustomBlock 中提取 mblogid
    for m in re.finditer(r'mblogid=(\d+)', msg):
        mblogids.add(m.group(1))

    # 也检查 scheme 字段
    scheme = zhisou_data.get("scheme", "")
    if scheme and 'mblogid=' in scheme:
        mid = scheme.split('mblogid=')[1].split('&')[0]
        mblogids.add(mid)

    return sorted(mblogids, reverse=True)  # 最新的在前


def load_post_cache():
    """加载帖子缓存"""
    if os.path.exists(POST_CACHE_FILE):
        try:
            with open(POST_CACHE_FILE, "r") as f:
                cache = json.load(f)
            cache_time = cache.get("cached_at", 0)
            if time.time() - cache_time < 86400:  # 24小时有效
                return cache.get("posts", {})
        except Exception:
            pass
    return {}


def save_post_cache(posts_dict):
    """保存帖子缓存"""
    with open(POST_CACHE_FILE, "w") as f:
        json.dump({"cached_at": time.time(), "posts": posts_dict}, f, ensure_ascii=False)


def fetch_status(mblogid, token, post_cache=None):
    """通过status_show API获取单条微博完整内容（支持缓存）"""
    # 先查缓存
    if post_cache and mblogid in post_cache:
        return post_cache[mblogid]

    url = f"{STATUS_API}?token={token}&id={mblogid}"
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        result = json.loads(resp.read())
        if result.get("code") == 0:
            data = result.get("data", {})
            # 写入缓存
            if post_cache is not None and data:
                post_cache[mblogid] = data
            return data
        elif result.get("code") == 42900:
            print(f"      ⚠️ API频率限制，等待30秒...")
            time.sleep(30)
            return fetch_status(mblogid, token, post_cache)
        return None
    except Exception as e:
        print(f"      status_show异常 ({mblogid}): {e}")
        return None


# ============ 帖子分类与内容提取 ============

def classify_post(post_data, teacher_filter=""):
    """
    分类帖子类型，同时标注是否为第三方
    返回: (post_type, question_number, is_third_party)
        post_type: "question"|"answer"|"collection"|"other"
    """
    text = post_data.get("text", "")
    user = post_data.get("user", {}).get("screen_name", "")

    # 提取题号
    q_num = None
    num_match = re.search(r'每日一题[^\d]*(\d+)', text)
    if num_match:
        q_num = int(num_match.group(1))

    # 判断是否为第三方（非老师本人）
    is_third_party = bool(teacher_filter) and teacher_filter not in user

    # 判断类型
    has_daily = '每日一题' in text
    is_answer = ('答案' in text) and has_daily
    is_collection = any(kw in text for kw in ['笔记', '整理', '汇总', '资料汇总', 'PDF', '合集'])

    if is_answer:
        return ("answer", q_num, is_third_party)
    elif has_daily and ('答案' not in text) and ('解析' not in text):
        if is_collection:
            return ("collection", q_num, is_third_party)
        return ("question", q_num, is_third_party)
    elif is_collection:
        return ("collection", q_num, is_third_party)
    else:
        return ("other", q_num, is_third_party)


def clean_post_text(text):
    """清洗微博帖子文本"""
    if not text:
        return ""

    # 去除URL
    text = re.sub(r'https?://\S+', '', text)
    # 去除hashtag（保留内容）
    text = re.sub(r'#([^#]+)#', r'\1', text)
    # 去除@提及
    text = re.sub(r'@\S+', '', text)
    # 清理多余空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def format_question_html(question_text, q_num=None):
    """将题目文本格式化为HTML"""
    text = clean_post_text(question_text)

    # Markdown粗体 → HTML
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # 高亮法律术语（在非标签文本中）
    def bold_law(txt):
        parts = re.split(r'(<[^>]+>)', txt)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                # 法条引用
                part = re.sub(
                    r'(《[^》]+》(?:第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)?)',
                    r'<strong class="law">\1</strong>', part
                )
                # 法条号
                part = re.sub(
                    r'(?<!\w)(第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)',
                    r'<strong class="law">\1</strong>', part
                )
                # 金额
                part = re.sub(
                    r'(\d+(?:\.\d+)?\s*(?:万元?|元)(?!\w))',
                    r'<strong class="num">\1</strong>', part
                )
            result.append(part)
        return ''.join(result)

    text = bold_law(text)

    # HTML转义（保护已生成的标签）
    def escape_safe(s):
        parts = re.split(r'(<[^>]+>)', s)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                result.append(part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        return ''.join(result)

    text = escape_safe(text)
    text = text.replace('\n', '<br>')

    return text


def format_answer_html(answer_text):
    """将答案文本格式化为HTML"""
    return format_question_html(answer_text)  # 复用同样的格式化逻辑


# ============ 两阶段抓取：含真实帖子的为一级，AI摘要为二级 ============

def fetch_teacher_posts(hashtag_query, teacher_filter, token):
    """
    一级抓取：通过hashtag搜索获取真实帖子，返回配对好的Q&A
    返回: (question_text, answer_text, question_link, answer_link, source_label) 或 None
    """
    # Step 1: 搜索hashtag获取mblogids
    data = search_zhisou(hashtag_query, token)
    if not data:
        return None

    mblogids = extract_mblogids(data)
    if not mblogids:
        return None

    # 如果有fallback查询（teacher名+每日一题），也搜索一次合并mblogid
    fallback_query = f"{teacher_filter} 每日一题"
    fb_data = search_zhisou(fallback_query, token)
    if fb_data:
        fb_ids = extract_mblogids(fb_data)
        mblogids = sorted(set(mblogids + fb_ids), reverse=True)
        print(f"      hashtag搜索: {len(set(mblogids))} 个唯一引用帖（含fallback合并）")

    fetch_n = min(MAX_POSTS_TO_FETCH, len(mblogids))
    print(f"      检查最近 {fetch_n} 个帖子...")

    # 加载帖子缓存
    post_cache = load_post_cache()

    # Step 2: 获取帖子并分类
    questions = []  # (mblogid, q_num, text, created_at, user, is_third)
    answers = []    # (mblogid, q_num, text, created_at, user, is_third)

    for mid in mblogids[:fetch_n]:
        post = fetch_status(mid, token, post_cache)
        if not post:
            continue

        post_type, q_num, is_third = classify_post(post, teacher_filter)
        text = post.get("text", "")
        created = post.get("created_at", "")
        user = post.get("user", {}).get("screen_name", "")

        if post_type == "question":
            questions.append((mid, q_num, text, created, user, is_third))
            third_tag = "📎三方" if is_third else "👤本人"
            print(f"         🎯 题目帖 Q{q_num} | {user} {third_tag} | {created}")
        elif post_type == "answer":
            answers.append((mid, q_num, text, created, user, is_third))
            third_tag = "📎三方" if is_third else "👤本人"
            print(f"         ✅ 答案帖 Q{q_num} | {user} {third_tag} | {created}")
        elif post_type == "collection":
            print(f"         📦 合集帖 | {user} | {created}")

        time.sleep(API_DELAY)

    # 保存帖子缓存
    save_post_cache(post_cache)

    # Step 3: 配对Q&A - 优先老师本人帖子
    if not answers:
        if questions:
            # 优先本人题目帖
            own_qs = [q for q in questions if not q[5]]
            q = own_qs[0] if own_qs else questions[0]
            weibo_link = f"https://weibo.com/detail/{q[0]}"
            return (q[2], "", weibo_link, "", f"题目帖(@{q[4]})")
        return None

    # 优先老师本人的答案帖，其次按时间
    own_answers = [a for a in answers if not a[5]]
    latest_answer = own_answers[0] if own_answers else answers[0]
    a_mid, a_num, a_text, a_created, a_user, a_third = latest_answer

    matching_question = None
    if a_num:
        # 优先本人且题号匹配的题目帖
        for q in questions:
            if q[1] == a_num:
                matching_question = q
                if not q[5]:  # 找到本人帖就停
                    break

    question_text = matching_question[2] if matching_question else ""
    question_link = f"https://weibo.com/detail/{matching_question[0]}" if matching_question else ""
    answer_link = f"https://weibo.com/detail/{a_mid}"
    source_label = f"Q{a_num}" if a_num else f"@{a_user}"
    if a_third:
        source_label += "(三方)"

    # 处理答案帖太短的情况（视频解析）
    if len(a_text.strip()) < 30:
        a_text = f"📹 本题解析为视频形式，请点击下方链接查看完整讲解"

    # 如果题目帖未找到，尝试从答案帖推断
    if not question_text:
        question_text = f"📌 {teacher_filter}每日一题" + (f" 第{a_num}题" if a_num else "")

    return (question_text, a_text, question_link, answer_link, source_label)


def fetch_teacher_fallback(fallback_queries, token):
    """
    二级抓取（fallback）：通过智搜AI摘要获取内容
    保留旧版逻辑用于没有真实帖子的替代名师
    返回: (source_label, question_html, answer_html, weibo_link, is_alternative)
    """
    for i, q in enumerate(fallback_queries):
        label = q["label"]
        is_alt = i > 0

        data = search_zhisou(q["query"], token)
        if data and not data.get("noContent"):
            raw_msg = data.get("msg", "")
            if len(raw_msg) > 50:
                # 复用旧的format逻辑
                cleaned = clean_zhisou_markdown(raw_msg)
                question_html, answer_html = format_zhisou_qa(cleaned)
                scheme = data.get("scheme", "")
                weibo_link = scheme.replace("sinaweibo://", "https://weibo.com/") if scheme else ""
                return (label, question_html, answer_html, weibo_link, is_alt)

    return None


# ============ 旧版兼容：智搜AI摘要清洗（用于fallback） ============

def clean_zhisou_markdown(raw_msg):
    """清洗智搜markdown"""
    if not raw_msg:
        return ""
    text = raw_msg
    text = re.sub(r'```wbCustomBlock\{[^}]*\}\s*[\s\S]*?```', '', text)
    text = re.sub(r'wbCustomBlock\{[^}]*\}', '', text)
    text = re.sub(r'<media-block>[\s\S]*?</media-block>', '', text)
    text = re.sub(r'```(?:plaintext|text|markdown|md)?\s*\n?', '', text)
    text = re.sub(r'```', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def format_zhisou_qa(raw_text, max_len=1200):
    """旧的Q&A分离逻辑（用于fallback）"""
    text = raw_text.strip()
    if not text:
        return "", ""

    # Markdown → HTML
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # 高亮
    def bold_outside_tags(txt, pattern, template):
        parts = re.split(r'(<[^>]+>)', txt)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                result.append(re.sub(pattern, template, part))
        return ''.join(result)

    text = bold_outside_tags(text, r'(《[^》]+》(?:第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)?)', r'<strong class="law">\1</strong>')
    text = bold_outside_tags(text, r'(?<!\w)(第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)', r'<strong class="law">\1</strong>')
    text = bold_outside_tags(text, r'(\d+(?:\.\d+)?\s*(?:万元?|元)(?!\w))', r'<strong class="num">\1</strong>')

    # 找分隔点
    split_pos = None
    for pattern_str in [
        r'以第[一二三四五六七八九十百千\d]+题为例',
        r'(?<=\n)(?:###?\s*)?(?:答案|解析|【答案】|【解析】)',
    ]:
        m = re.search(pattern_str, text)
        if m and m.start() > 60:
            split_pos = m.start()
            break

    if split_pos is None:
        paragraphs = re.split(r'\n{2,}', text)
        cum_len = 0
        for i, p in enumerate(paragraphs):
            cum_len += len(p)
            if cum_len > 200 and i >= 1:
                split_pos = len('\n\n'.join(paragraphs[:i+1]))
                break

    if split_pos and split_pos > 60:
        q = text[:split_pos].strip()
        a = text[split_pos:].strip()
    else:
        q = text
        a = ""

    if len(q) > max_len:
        q = q[:max_len] + "<br><br>...(完整内容请点击链接查看)"

    if a and len(a) > max_len:
        a = a[:max_len] + "<br><br>...(完整内容请点击链接查看)"

    # 去除AI开场白
    q = re.sub(r'^[^。\n<br]{2,25}(?:是|为)(?:法考|法律职业|知名|资深)[^。\n<br]*?[。\n<br]', '', q).strip()

    # HTML转义
    def escape_safe(s):
        parts = re.split(r'(<[^>]+>)', s)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                result.append(part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        return ''.join(result)

    q = escape_safe(q).replace('\n', '<br>')
    a = escape_safe(a).replace('\n', '<br>') if a else ""

    return q, a


# ============ 邮件 ============

def send_email(subject, html_body):
    """通过QQ邮箱SMTP发送"""
    msg = MIMEMultipart("alternative")
    msg["From"] = QQ_EMAIL
    msg["To"] = QQ_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=30)
        server.login(QQ_EMAIL, QQ_SMTP_CODE)
        server.sendmail(QQ_EMAIL, [QQ_EMAIL], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"  ❌ 邮件发送失败: {e}")
        return False


# ============ 报告构建 ============

def build_html_report(slot_results):
    """构建Q&A格式HTML邮件"""
    tz = timezone(timedelta(hours=8))
    today = datetime.now(tz).strftime("%m月%d日")
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_map[datetime.now(tz).weekday()]

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system,'PingFang SC','Microsoft YaHei',sans-serif; color:#2c3e50; line-height:1.8; max-width:680px; margin:0 auto; padding:0; background:#f5f6fa; }}
.header {{ background: linear-gradient(135deg,#1a1a2e,#16213e); color:#fff; padding:20px 22px; text-align:center; }}
.header h1 {{ margin:0; font-size:18px; font-weight:600; letter-spacing:1px; }}
.header .date {{ font-size:12px; opacity:.7; margin-top:4px; }}
.header .sub {{ font-size:11px; opacity:.5; margin-top:2px; }}
.card {{ background:#fff; margin:10px 12px; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
.card-head {{ padding:12px 16px; display:flex; align-items:center; gap:8px; border-bottom:1px solid #f0f0f0; }}
.card-head .dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
.card-head .name {{ font-weight:600; font-size:14px; }}
.card-head .src {{ font-size:11px; color:#999; }}
.card-head .badge {{ font-size:10px; padding:1px 7px; border-radius:8px; color:#fff; flex-shrink:0; }}
.q-section {{ padding:14px 16px; font-size:13.5px; color:#2c3e50; }}
.q-section .q-label {{ display:inline-block; background:#fff3cd; color:#856404; font-size:10px; padding:2px 8px; border-radius:8px; font-weight:600; margin-bottom:8px; letter-spacing:1px; }}
.a-divider {{ margin:0 16px; border:none; border-top:2px dashed #e0e0e0; position:relative; height:40px; display:flex; align-items:center; justify-content:center; }}
.a-divider span {{ background:#fff; padding:0 12px; font-size:11px; color:#bbb; letter-spacing:2px; position:absolute; }}
.a-section {{ padding:6px 16px 18px; font-size:13.5px; color:#555; }}
.a-section .a-label {{ display:inline-block; background:#d4edda; color:#155724; font-size:10px; padding:2px 8px; border-radius:8px; font-weight:600; margin-bottom:8px; letter-spacing:1px; }}
.no-result {{ padding:16px; color:#bbb; font-size:13px; text-align:center; font-style:italic; }}
strong.law {{ color:#c0392b; font-weight:600; }}
strong.num {{ color:#2980b9; font-weight:600; }}
.link-row {{ padding:8px 16px; background:#fafafa; border-top:1px solid #f5f5f5; font-size:12px; }}
.link-row a {{ color:#6c5ce7; text-decoration:none; }}
.link-row a:hover {{ text-decoration:underline; }}
.summary {{ background:#f8f9fa; margin:10px 12px; border-radius:8px; padding:12px 16px; font-size:12px; color:#888; text-align:center; }}
.summary b {{ color:#2c3e50; }}
.footer {{ text-align:center; padding:16px; font-size:10px; color:#ccc; }}
@media (prefers-color-scheme:dark) {{
  body {{ background:#1a1a2e; color:#ddd; }}
  .card {{ background:#16213e; border:1px solid #0f3460; }}
  .card-head {{ border-color:#0f3460; }}
  .q-section {{ color:#ddd; }}
  .a-section {{ color:#bbb; }}
  .a-divider span {{ background:#16213e; }}
  .summary {{ background:#16213e; color:#888; }}
  .summary b {{ color:#ddd; }}
  .no-result {{ color:#555; }}
  .link-row {{ background:#0f3460; border-color:#1a1a2e; }}
}}
</style></head><body>
<div class="header">
  <h1>📝 法考每日一题</h1>
  <div class="date">{today} {weekday}</div>
  <div class="sub">v3.0 · 真实帖子抓取 · Hashtag搜索+内容配对</div>
</div>
"""
    success_count = 0
    real_post_count = 0  # 从真实帖子获取的
    alt_count = 0

    for subject, result in slot_results.items():
        color = result.get("color", "#636e72")
        source_label = result.get("source_label", "")
        is_alternative = result.get("is_alternative", False)
        is_real_post = result.get("is_real_post", False)
        question_html = result.get("question", "")
        answer_html = result.get("answer", "")
        question_link = result.get("question_link", "")
        answer_link = result.get("answer_link", "")
        error = result.get("error", False)
        has_content = bool(question_html and not error)

        if has_content:
            success_count += 1
            if is_real_post:
                real_post_count += 1
            if is_alternative:
                alt_count += 1

        html += '<div class="card">\n'
        html += '  <div class="card-head">\n'
        html += f'    <span class="dot" style="background:{color}"></span>\n'
        html += f'    <span class="name">{subject}</span>\n'
        if has_content and source_label:
            html += f'    <span class="src">{source_label}</span>\n'
        if has_content:
            badge_text = "📡真实帖" if is_real_post else ("替代" if is_alternative else "已更新")
            badge_color = "#27ae60" if is_real_post else ("#6c5ce7" if is_alternative else "#27ae60")
            html += f'    <span class="badge" style="background:{badge_color}">{badge_text}</span>\n'
        elif error:
            html += f'    <span class="badge" style="background:#f39c12">故障</span>\n'
        else:
            html += f'    <span class="badge" style="background:#bbb">暂无</span>\n'
        html += '  </div>\n'

        if has_content:
            a_len = len(answer_html) if answer_html else 0

            if is_real_post and a_len >= 30:
                # 真实帖子且有答案：Q&A分隔模式
                html += '  <div class="q-section">\n'
                html += '    <span class="q-label">📌 题目</span><br>\n'
                html += f'    {question_html}\n'
                html += '  </div>\n'

                html += '  <div class="a-divider"><span>▼ 答 案 在 下 方 ▼</span></div>\n'

                html += '  <div class="a-section">\n'
                html += '    <span class="a-label">✅ 答案 / 解析</span><br>\n'
                html += f'    {answer_html}\n'
                html += '  </div>\n'
            elif a_len >= 100:
                # AI摘要且有长答案
                html += '  <div class="q-section">\n'
                html += '    <span class="q-label">📌 题目</span><br>\n'
                html += f'    {question_html}\n'
                html += '  </div>\n'
                html += '  <div class="a-divider"><span>▼ 答 案 在 下 方 ▼</span></div>\n'
                html += '  <div class="a-section">\n'
                html += '    <span class="a-label">✅ 答案 / 解析</span><br>\n'
                html += f'    {answer_html}\n'
                html += '  </div>\n'
            else:
                html += '  <div class="q-section">\n'
                html += '    <span class="q-label">📌 综合摘要</span><br>\n'
                html += f'    {question_html}\n'
                if answer_html:
                    html += '    <br><br><span style="display:inline-block;background:#d4edda;color:#155724;font-size:10px;padding:2px 8px;border-radius:8px;font-weight:600;">✅ 答案</span><br>\n'
                    html += f'    {answer_html}\n'
                html += '  </div>\n'
        elif error:
            html += f'  <div class="no-result">⚠️ {error}</div>\n'
        else:
            html += '  <div class="no-result">🔍 今日暂未检索到该科目每日一题</div>\n'

        # 链接
        links = []
        if question_link:
            links.append(f'🔗 <a href="{question_link}">题目原文</a>')
        if answer_link and answer_link != question_link:
            links.append(f'🔗 <a href="{answer_link}">答案原文</a>')
        if links:
            html += f'  <div class="link-row">{" · ".join(links)}</div>\n'

        html += '</div>\n'

    # 汇总
    total = len(slot_results)
    html += '<div class="summary">\n'
    html += f'<b>{success_count}/{total}</b> 科目已获取'
    if real_post_count > 0:
        html += f' · <b>{real_post_count}</b> 来自真实帖子 📡'
    if alt_count > 0:
        html += f' · <b>{alt_count}</b> 使用替代名师'
    html += ' · 自动生成于 GitHub Actions</div>\n'

    html += '<div class="footer">\n'
    html += '<p>☁️ 法考云端监控 v3.0 · 每日8:30 · Hashtag真实帖子抓取+AI摘要fallback</p>\n'
    html += '</div>\n'
    html += '</body></html>'

    return html


# ============ 主流程 ============

def main():
    tz = timezone(timedelta(hours=8))
    print(f"===== 法考每日一题 v3.0 · 真实帖子抓取版 =====")
    print(f"执行时间: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)\n")

    # 获取token
    print("🔑 获取微博API Token...")
    try:
        token = get_weibo_token()
        print(f"   ✅ Token已就绪 (前8位: {token[:8]}...)\n")
    except Exception as e:
        print(f"   ❌ Token获取失败: {e}")
        fallback_html = f"""<html><body>
<h2>⚠️ 法考每日一题 · 微博API故障</h2>
<p>微博Token获取失败: {e}</p>
<p>时间: {datetime.now(tz)} (GMT+8)</p>
<p>请检查AppId/AppSecret是否有效。</p>
<hr><p style="color:#999;font-size:12px">法考云端监控系统</p>
</body></html>"""
        send_email("⚠️【法考每日一题】微博API故障 | 需检查凭据", fallback_html)
        return

    # 逐个科目抓取
    slot_results = {}
    success_count = 0
    real_post_count = 0
    alt_count = 0
    api_calls = 0

    for subject, slot in TEACHER_SLOTS.items():
        display = slot["display_name"]
        color = slot["color"]
        hashtag_query = slot["hashtag_query"]
        teacher_filter = slot["teacher_filter"]
        fallback_queries = slot["fallback_queries"]

        print(f"🔍 {subject} ({display})")
        print(f"   📡 一级抓取: hashtag='{hashtag_query}' filter='{teacher_filter}'...")

        try:
            # ============ 一级：真实帖子抓取 ============
            result = fetch_teacher_posts(hashtag_query, teacher_filter, token)
            api_calls += 1  # 搜索调用

            if result:
                q_text, a_text, q_link, a_link, source_label = result
                q_html = format_question_html(q_text)
                a_html = format_answer_html(a_text)

                slot_results[subject] = {
                    "color": color,
                    "source_label": source_label,
                    "question": q_html,
                    "answer": a_html,
                    "question_link": q_link,
                    "answer_link": a_link,
                    "is_alternative": False,
                    "is_real_post": True,
                    "error": False,
                }
                success_count += 1
                real_post_count += 1
                content_len = len(q_text) + len(a_text)
                print(f"   ✅ 真实帖子命中: {source_label} ({content_len} 字符)")
            else:
                # ============ 二级：AI摘要fallback ============
                print(f"   📡 一级未命中，尝试二级（AI摘要+替代名师）...")
                fb_result = fetch_teacher_fallback(fallback_queries, token)
                api_calls += len(fallback_queries)

                if fb_result:
                    fb_label, q_html, a_html, wb_link, is_alt = fb_result
                    slot_results[subject] = {
                        "color": color,
                        "source_label": fb_label,
                        "question": q_html,
                        "answer": a_html,
                        "question_link": wb_link,
                        "answer_link": "",
                        "is_alternative": is_alt,
                        "is_real_post": False,
                        "error": False,
                    }
                    success_count += 1
                    if is_alt:
                        alt_count += 1
                    tag = "📡替代" if is_alt else "✅"
                    print(f"   {tag} AI摘要命中: {fb_label}")
                else:
                    slot_results[subject] = {
                        "color": color,
                        "source_label": "",
                        "question": "",
                        "answer": "",
                        "question_link": "",
                        "answer_link": "",
                        "is_alternative": False,
                        "is_real_post": False,
                        "error": False,
                    }
                    print(f"   ⚪ 一级二级均未命中")

        except Exception as e:
            print(f"   ❌ 错误: {e}")
            slot_results[subject] = {
                "color": color,
                "source_label": "",
                "question": "",
                "answer": "",
                "question_link": "",
                "answer_link": "",
                "is_alternative": False,
                "is_real_post": False,
                "error": str(e),
            }

    # 统计
    total_slots = len(TEACHER_SLOTS)
    print(f"\n{'='*60}")
    print(f"📊 结果: {success_count}/{total_slots} 科目获取成功")
    print(f"   📡 真实帖子: {real_post_count}")
    if alt_count > 0:
        print(f"   🔄 替代名师: {alt_count}")
    print(f"   🔢 API调用: ~{api_calls}/100 (小时限额)")

    # 构建并发送报告
    html = build_html_report(slot_results)

    today_mmdd = datetime.now(tz).strftime("%m/%d")
    subject = f"【法考每日一题】{today_mmdd} | v3.0真实帖 | {success_count}/{total_slots}已获取"
    if real_post_count > 0:
        subject += f"({real_post_count}真实帖)"

    if send_email(subject, html):
        print(f"\n✅ 任务完成! 邮件已发送至 {QQ_EMAIL}")
    else:
        print(f"\n❌ 邮件发送失败")


if __name__ == "__main__":
    main()
