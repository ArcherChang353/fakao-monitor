#!/usr/bin/env python3
"""
法考每日一题抓取 v4.0 — OAuth2.0 + friends_timeline 方案
核心：通过OAuth2.0 access_token调用friends_timeline获取关注人（8位老师）帖子，
      筛选每日一题内容，实现Q&A配对。
每天8:30 GMT+8 执行，云端运行（GitHub Actions）。
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

# OAuth2.0 配置（api.weibo.com 体系）
WEIBO_APP_KEY = os.environ["WEIBO_APP_KEY"]
WEIBO_APP_SECRET = os.environ["WEIBO_APP_SECRET"]
WEIBO_ACCESS_TOKEN = os.environ.get("WEIBO_ACCESS_TOKEN", "")

# OAuth2.0 API
OAUTH_TOKEN_URL = "https://api.weibo.com/oauth2/access_token"
FRIENDS_TIMELINE_URL = "https://api.weibo.com/2/statuses/friends_timeline.json"
STATUS_SHOW_URL = "https://api.weibo.com/2/statuses/show.json"

# 缓存
TOKEN_CACHE_FILE = "weibo_oauth_token.json"
QUESTION_CACHE_FILE = "weibo_question_cache.json"

# 8位老师配置（已验证的正确UID）
TEACHERS = {
    "行政法": {"name": "李佳", "uid": 1552849431, "screen_name": "行政法李佳", "color": "#e74c3c"},
    "刑法":   {"name": "柏浪涛", "uid": 2523185197, "screen_name": "柏浪涛的刑法观", "color": "#e67e22"},
    "民法":   {"name": "孟献贵", "uid": 2342740757, "screen_name": "民商法孟献贵", "color": "#2980b9"},
    "民诉":   {"name": "戴鹏", "uid": 2758385724, "screen_name": "法律人戴鹏", "color": "#8e44ad"},
    "刑诉":   {"name": "左宁", "uid": 3153511812, "screen_name": "左宁刑诉", "color": "#27ae60"},
    "三国法": {"name": "杨帆", "uid": 2629450315, "screen_name": "三国法杨帆", "color": "#16a085"},
    "理论法": {"name": "马峰", "uid": 1826780577, "screen_name": "理论法马峰", "color": "#2c3e50"},
    "商经知": {"name": "鄢梦萱", "uid": 5568788458, "screen_name": "商经法鄢梦萱", "color": "#d35400"},
}

TEACHER_UID_SET = {t["uid"] for t in TEACHERS.values()}
TEACHER_BY_UID = {t["uid"]: t for t in TEACHERS.values()}

# friends_timeline 翻页配置
TIMELINE_PAGES = 5
TIMELINE_COUNT = 100  # 每页条数（OAuth2.0限制单次最多100条）
API_DELAY = 1.0


# ============ OAuth2.0 Token管理 ============

def get_oauth_token():
    """
    获取OAuth2.0 access_token。
    优先从环境变量，其次从缓存文件。
    如果缓存失效，使用client_credentials无法刷新，需要手动重新授权。
    """
    # 优先环境变量
    if WEIBO_ACCESS_TOKEN:
        print("   ✅ 从环境变量加载 access_token")
        return WEIBO_ACCESS_TOKEN

    # 从缓存
    if os.path.exists(TOKEN_CACHE_FILE):
        try:
            with open(TOKEN_CACHE_FILE, "r") as f:
                cache = json.load(f)
            cached_at = cache.get("cached_at", 0)
            expires_in = cache.get("expires_in", 157680000)
            if time.time() - cached_at < expires_in - 86400:
                return cache.get("access_token")
        except Exception:
            pass

    # 缓存无效，无法自动刷新（OAuth2.0需要手动授权）
    raise Exception("OAuth2.0 access_token 无效，需要重新手动授权获取")


def save_oauth_token(access_token, expires_in=157680000):
    """保存access_token到缓存"""
    with open(TOKEN_CACHE_FILE, "w") as f:
        json.dump({
            "access_token": access_token,
            "cached_at": time.time(),
            "expires_in": expires_in,
        }, f)


# ============ 题目缓存 ============

def load_question_cache():
    """加载跨天题目缓存"""
    if os.path.exists(QUESTION_CACHE_FILE):
        try:
            with open(QUESTION_CACHE_FILE, "r") as f:
                cache = json.load(f)
            # 清理7天前的
            cutoff = time.time() - 604800
            stale = [k for k, v in cache.items() if v.get("cached_ts", 0) < cutoff]
            for k in stale:
                del cache[k]
            return cache
        except Exception:
            pass
    return {}


def save_question_cache(cache):
    with open(QUESTION_CACHE_FILE, "w") as f:
        json.dump(cache, f, ensure_ascii=False)


def find_cached_question(teacher_name, q_num, cache):
    key = f"{teacher_name}_{q_num}"
    return cache.get(key)


def store_question_cache(teacher_name, q_num, text, weibo_link, created_at, cache):
    key = f"{teacher_name}_{q_num}"
    cache[key] = {
        "q_num": q_num,
        "text": text,
        "weibo_link": weibo_link,
        "created_at": created_at,
        "cached_ts": time.time(),
    }


# ============ 帖子处理 ============

def extract_q_num(text):
    """从帖子文本提取题号"""
    # 模式1: 每日一题XX
    m = re.search(r'每日一题[^\d]*(\d+)', text)
    if m:
        return int(m.group(1))
    # 模式2: 纯数字标题（柏浪涛模式: "90.xxx"）
    m = re.search(r'^(\d{1,3})[\.\、\s]', text.strip())
    if m:
        num = int(m.group(1))
        if 1 <= num <= 999:
            return num
    # 模式3: 第X题
    m = re.search(r'第\s*(\d+)\s*题', text)
    if m:
        return int(m.group(1))
    return None


def classify_post(post_data):
    """
    分类帖子类型。
    返回: ("question"|"answer"|"collection"|"other", q_num)

    识别策略：
    1. 包含"每日一题" + "答案" → answer
    2. 包含"每日一题" + 不含"答案" → question
    3. 纯题号格式（如"90.xxx"）+ 包含ABCD选项 → question
    4. 纯题号格式 + 无选项（可能被截断）→ 仍判定为question（法考题帖格式）
    5. 纯题号格式 + 含"答案"/"解析" → answer
    """
    text = post_data.get("text", "")

    q_num = extract_q_num(text)

    has_daily = "每日一题" in text
    has_options = bool(re.search(r'[A-D][\.\、）\)]', text))
    has_answer_kw = "答案" in text or "解析" in text
    is_collection = any(kw in text for kw in ["笔记", "整理", "汇总", "PDF", "合集"])

    if is_collection:
        return ("collection", q_num)

    if has_daily:
        if has_answer_kw:
            return ("answer", q_num)
        else:
            return ("question", q_num)

    # 无"每日一题"但有题号：纯题号格式（柏浪涛/左宁模式）
    if q_num:
        if has_answer_kw:
            return ("answer", q_num)
        # 有选项或题号>=10（前几位老师通常10题起）→ 视为题目
        if has_options or q_num >= 10:
            return ("question", q_num)

    return ("other", q_num)


def clean_text(text):
    """清洗微博文本"""
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'#([^#]+)#', r'\1', text)
    text = re.sub(r'@\S+', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def format_html(text):
    """文本转HTML"""
    text = clean_text(text)

    # Markdown粗体
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # 法条引用高亮
    def bold_law(txt):
        parts = re.split(r'(<[^>]+>)', txt)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                part = re.sub(r'(《[^》]+》(?:第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)?)', r'<strong class="law">\1</strong>', part)
                part = re.sub(r'(?<!\w)(第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)', r'<strong class="law">\1</strong>', part)
                part = re.sub(r'(\d+(?:\.\d+)?\s*(?:万元?|元)(?!\w))', r'<strong class="num">\1</strong>', part)
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


# ============ 核心抓取逻辑 ============

def fetch_full_post(token, mid):
    """
    获取单条微博完整内容。
    先尝试 statuses/show（仅对互关用户有效），
    失败则用 m.weibo.cn 移动端API（公开接口，无需鉴权）。
    """
    # 方式1: OAuth2.0 statuses/show
    url = f"{STATUS_SHOW_URL}?access_token={token}&id={mid}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if "error_code" not in data:
            return data.get("text", "")
    except Exception:
        pass

    # 方式2: m.weibo.cn 移动端公开API
    try:
        m_url = f"https://m.weibo.cn/statuses/show?id={mid}"
        m_req = urllib.request.Request(
            m_url,
            headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15"}
        )
        with urllib.request.urlopen(m_req, timeout=10) as m_resp:
            m_json = json.loads(m_resp.read().decode("utf-8"))
        m_data = m_json.get("data") or m_json.get("status") or {}
        if m_data:
            return m_data.get("text", "")
    except Exception:
        pass

    return None


def fetch_all_teacher_posts(token):
    """
    通过 friends_timeline 翻页获取所有关注人帖子，筛选8位老师。
    对截断的长文帖子（含"全文"链接），调用statuses/show获取完整内容。
    返回: {teacher_name: [(mid, text, created_at, q_num, post_type), ...]}
    """
    teacher_posts = {t["name"]: [] for t in TEACHERS.values()}

    max_id = None
    for page in range(TIMELINE_PAGES):
        url = f"{FRIENDS_TIMELINE_URL}?access_token={token}&count={TIMELINE_COUNT}"
        if max_id:
            url += f"&max_id={max_id}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"   ⚠️ friends_timeline 第{page+1}页失败: {e}")
            break

        posts = data.get("statuses", [])
        if not posts:
            break

        for p in posts:
            uid = p.get("user", {}).get("id")
            if uid not in TEACHER_UID_SET:
                continue

            teacher = TEACHER_BY_UID[uid]
            mid = str(p.get("id", ""))
            text = p.get("text", "")
            created = p.get("created_at", "")

            # 检测截断：如果文本含"全文"或 isLongText（被截断），尝试获取完整内容
            truncated = ("全文" in text and ("http://m.weibo.cn" in text or "t.cn" in text)) or p.get("isLongText")
            full_text = None
            if truncated:
                full_text = fetch_full_post(token, mid)
                if full_text and len(full_text) > len(text):
                    text = full_text
                    time.sleep(0.3)

            post_type, q_num = classify_post({"text": text})

            # 如果截断无法获取完整内容，给文本加提示
            if truncated and not full_text:
                text = text.replace("...全文：", f"\n\n⚠️ 原文较长，以下为截断版本，完整内容请点击原文链接\n（截断处）...全文：")

            teacher_posts[teacher["name"]].append((mid, text, created, q_num, post_type))

        max_id = int(posts[-1].get("id", 0)) - 1
        time.sleep(API_DELAY)

    return teacher_posts


def process_teacher(subject, teacher_info, posts, question_cache):
    """
    处理单个老师的帖子，返回结果字典。
    核心逻辑：
    1. 今天发的新题目 → 直接展示
    2. 今天发的答案 → 从缓存找昨天的题目配对
    3. 都没有 → 返回None
    """
    name = teacher_info["name"]
    color = teacher_info["color"]

    questions = [(mid, text, created, qn) for mid, text, created, qn, pt in posts if pt == "question" and qn]
    answers = [(mid, text, created, qn) for mid, text, created, qn, pt in posts if pt == "answer" and qn]

    print(f"   {name}: {len(questions)}个题目帖, {len(answers)}个答案帖")

    # 策略1: 今天有答案帖 → 尝试配对
    if answers:
        best_answer = answers[0]  # 最新的答案
        a_mid, a_text, a_created, a_num = best_answer

        # 从缓存找题目
        cached_q = find_cached_question(name, a_num, question_cache)
        if cached_q:
            q_text = cached_q["text"]
            q_link = cached_q["weibo_link"]
            print(f"   ✅ {name} 缓存配对: Q{a_num} 答案 + 缓存题目")
        else:
            # 缓存没命中，用答案帖文本提取题目描述
            q_text = f"📌 {name} 每日一题 第{a_num}题\n（题目缓存未命中，仅展示答案）"
            q_link = ""
            print(f"   ⚠️ {name} Q{a_num} 答案缓存未命中")

        # 同时检查今天是否也发了新题
        if questions:
            new_q = questions[0]
            new_mid, new_text, new_created, new_num = new_q
            if new_num != a_num:
                # 缓存新题目
                store_question_cache(name, new_num, new_text, f"https://weibo.com/detail/{new_mid}", new_created, question_cache)

        return {
            "question": format_html(q_text),
            "answer": format_html(a_text),
            "question_link": q_link,
            "answer_link": f"https://weibo.com/detail/{a_mid}",
            "source_label": f"Q{a_num} ✅完整(缓存配对)",
            "q_num": a_num,
            "is_complete": bool(cached_q),
        }

    # 策略2: 今天只有题目帖 → 缓存并展示
    if questions:
        best_q = questions[0]
        q_mid, q_text, q_created, q_num = best_q
        weibo_link = f"https://weibo.com/detail/{q_mid}"
        store_question_cache(name, q_num, q_text, weibo_link, q_created, question_cache)

        return {
            "question": format_html(q_text),
            "answer": f"📌 今日新题，答案将于明日公布",
            "question_link": weibo_link,
            "answer_link": "",
            "source_label": f"Q{q_num} 🆕新题",
            "q_num": q_num,
            "is_complete": False,
        }

    return None


# ============ 邮件和报告 ============

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
  <div class="sub">v4.0 · OAuth2.0 · friends_timeline · 真实帖子完整抓取</div>
</div>
"""

    success_count = 0
    complete_count = 0

    for subject in TEACHERS:
        teacher = TEACHERS[subject]
        result = slot_results.get(subject, {})
        color = result.get("color", teacher["color"])
        source_label = result.get("source_label", "")
        question_html = result.get("question", "")
        answer_html = result.get("answer", "")
        question_link = result.get("question_link", "")
        answer_link = result.get("answer_link", "")
        error = result.get("error", False)
        is_complete = result.get("is_complete", False)
        has_content = bool(question_html and not error)

        if has_content:
            success_count += 1
            if is_complete:
                complete_count += 1

        html += '<div class="card">\n'
        html += '  <div class="card-head">\n'
        html += f'    <span class="dot" style="background:{color}"></span>\n'
        html += f'    <span class="name">{subject} · {teacher["name"]}</span>\n'
        if has_content and source_label:
            html += f'    <span class="src">{source_label}</span>\n'
        if has_content:
            badge_text = "完整Q&A" if is_complete else "新题"
            badge_color = "#27ae60" if is_complete else "#3498db"
            html += f'    <span class="badge" style="background:{badge_color}">{badge_text}</span>\n'
        elif error:
            html += f'    <span class="badge" style="background:#f39c12">故障</span>\n'
        else:
            html += f'    <span class="badge" style="background:#bbb">暂无</span>\n'
        html += '  </div>\n'

        if has_content:
            html += '  <div class="q-section">\n'
            html += '    <span class="q-label">📌 题目</span><br>\n'
            html += f'    {question_html}\n'
            html += '  </div>\n'

            if answer_html and len(answer_html) > 30:
                html += '  <div class="a-divider"><span>▼ 答 案 在 下 方 ▼</span></div>\n'
                html += '  <div class="a-section">\n'
                html += '    <span class="a-label">✅ 答案 / 解析</span><br>\n'
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

    total = len(TEACHERS)
    html += '<div class="summary">\n'
    html += f'<b>{success_count}/{total}</b> 科目已获取'
    if complete_count > 0:
        html += f' · <b>{complete_count}</b> 完整Q&A'
    html += f' · OAuth2.0直连 · 真实帖子完整抓取</div>\n'

    html += '<div class="footer">\n'
    html += '<p>☁️ 法考云端监控 v4.0 · 每日8:30 · OAuth2.0 friends_timeline</p>\n'
    html += '</div>\n'
    html += '</body></html>'

    return html


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


# ============ 主流程 ============

def main():
    tz = timezone(timedelta(hours=8))
    print(f"===== 法考每日一题 v4.0 · OAuth2.0 + friends_timeline =====")
    print(f"执行时间: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)\n")

    # Step 1: 获取 access_token
    print("🔑 获取 OAuth2.0 access_token...")
    try:
        token = get_oauth_token()
        print(f"   ✅ Token已就绪 (前8位: {token[:8]}...)\n")
    except Exception as e:
        print(f"   ❌ Token获取失败: {e}")
        fallback_html = f"""<html><body>
<h2>⚠️ 法考每日一题 · OAuth2.0 Token失效</h2>
<p>错误: {e}</p>
<p>时间: {datetime.now(tz)} (GMT+8)</p>
<p>需要手动重新授权获取新的 access_token。</p>
<hr><p style="color:#999;font-size:12px">法考云端监控 v4.0</p>
</body></html>"""
        send_email("⚠️【法考每日一题】OAuth2.0 Token失效 | 需重新授权", fallback_html)
        return

    # Step 2: 加载题目缓存
    question_cache = load_question_cache()
    print(f"📦 题目缓存: {len(question_cache)} 条\n")

    # Step 3: 拉取关注人时间线
    print(f"📡 拉取关注人时间线（最多{TIMELINE_PAGES}页×{TIMELINE_COUNT}条）...")
    teacher_posts = fetch_all_teacher_posts(token)

    total_teacher_posts = sum(len(v) for v in teacher_posts.values())
    print(f"   ✅ 共 {total_teacher_posts} 条老师帖子\n")

    # Step 4: 逐个处理
    slot_results = {}
    for subject, teacher in TEACHERS.items():
        name = teacher["name"]
        posts = teacher_posts.get(name, [])

        print(f"🔍 {subject} ({name})")
        result = process_teacher(subject, teacher, posts, question_cache)

        if result:
            slot_results[subject] = {
                "color": teacher["color"],
                **result,
                "error": False,
            }
        else:
            slot_results[subject] = {
                "color": teacher["color"],
                "question": "",
                "answer": "",
                "question_link": "",
                "answer_link": "",
                "source_label": "",
                "q_num": None,
                "is_complete": False,
                "error": False,
            }
            print(f"   ⚪ 未找到每日一题")

    # Step 5: 保存缓存
    save_question_cache(question_cache)

    # Step 6: 统计
    total = len(TEACHERS)
    success_count = sum(1 for r in slot_results.values() if r.get("question"))
    complete_count = sum(1 for r in slot_results.values() if r.get("is_complete"))

    print(f"\n{'='*60}")
    print(f"📊 结果: {success_count}/{total} 科目获取成功 · {complete_count} 完整Q&A")

    if success_count == 0:
        print(f"\n⚠️ 所有科目均获取失败，跳过邮件发送")
        return

    # Step 7: 构建HTML并发送
    html = build_html_report(slot_results)

    # 保存本地预览
    try:
        today_ymd = datetime.now(tz).strftime("%Y%m%d")
        preview_path = f"preview-{today_ymd}.html"
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"💾 HTML预览已保存: {preview_path}")
    except Exception as e:
        print(f"⚠️ HTML预览保存失败: {e}")

    today_mmdd = datetime.now(tz).strftime("%m/%d")
    subject = f"【法考每日一题】{today_mmdd} | v4.0 | {success_count}/{total}已获取"
    if complete_count > 0:
        subject += f"({complete_count}完整Q&A)"

    if send_email(subject, html):
        print(f"\n✅ 任务完成! 邮件已发送至 {QQ_EMAIL}")
    else:
        print(f"\n❌ 邮件发送失败（但HTML预览已保存到本地）")


if __name__ == "__main__":
    main()
