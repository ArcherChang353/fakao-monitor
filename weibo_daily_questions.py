#!/usr/bin/env python3
"""
法考每日一题抓取 - 微博智搜版（多源替代版）
通过微博龙虾助手API搜索8科目名师每日一题，获取AI完整内容摘要
每位老师按优先级配置主搜索词+替代名师搜索词，首个成功即采用
每天8:30 GMT+8 执行，云端运行，不依赖个人电脑
"""

import os
import re
import json
import hashlib
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

# ============ 8科目搜索配置（多源替代） ============
# 每个科目保留一个展示位，按优先级尝试多个搜索词
# 首个成功即采用，全部失败则显示"暂未搜到"
TEACHER_SLOTS = {
    "行政法": {
        "display_name": "李佳（行政法）",
        "color": "#e74c3c",
        "queries": [
            {"name": "李佳", "label": "李佳（行政法）", "query": "行政法李佳 每日一题"},
        ],
    },
    "刑法": {
        "display_name": "柏浪涛（刑法）",
        "color": "#e67e22",
        "queries": [
            {"name": "柏浪涛", "label": "柏浪涛（刑法）", "query": "柏浪涛 每日一题"},
        ],
    },
    "民法": {
        "display_name": "孟献贵（民法）",
        "color": "#2980b9",
        "queries": [
            {"name": "孟献贵", "label": "孟献贵（民法）",              "query": "孟献贵 每日一题"},
            {"name": "钟秀勇", "label": "钟秀勇（民法·瑞达）📡替代",  "query": "钟秀勇 民法"},
            {"name": "张翔",   "label": "张翔（民法·厚大）📡替代",    "query": "张翔 民法"},
        ],
    },
    "民诉": {
        "display_name": "戴鹏（民诉）",
        "color": "#8e44ad",
        "queries": [
            {"name": "戴鹏",   "label": "戴鹏（民诉）",               "query": "戴鹏 每日一题"},
            {"name": "韩心怡", "label": "韩心怡（民诉·瑞达）📡替代",  "query": "韩心怡 民诉法"},
        ],
    },
    "刑诉": {
        "display_name": "左宁（刑诉）",
        "color": "#27ae60",
        "queries": [
            {"name": "左宁", "label": "左宁（刑诉）", "query": "左宁 每日一题"},
        ],
    },
    "三国法": {
        "display_name": "杨帆（三国法）",
        "color": "#16a085",
        "queries": [
            {"name": "杨帆", "label": "杨帆（三国法）",                "query": "杨帆 每日一题"},
            {"name": "殷敏", "label": "殷敏（三国法·厚大）📡替代",    "query": "殷敏 三国法"},
        ],
    },
    "理论法": {
        "display_name": "马峰（理论法）",
        "color": "#2c3e50",
        "queries": [
            {"name": "马峰",   "label": "马峰（理论法）",                "query": "马峰 每日一题"},
            {"name": "杜洪波", "label": "杜洪波（理论法）📡替代",       "query": "杜洪波 法考"},
            {"name": "宋光明", "label": "宋光明（理论法·瑞达）📡替代",  "query": "宋光明 理论法"},
        ],
    },
    "商经知": {
        "display_name": "郄鹏恩（商经知）",
        "color": "#d35400",
        "queries": [
            {"name": "郄鹏恩", "label": "郄鹏恩（商经知）", "query": "郄鹏恩 每日一题"},
        ],
    },
}

CACHE_FILE = "weibo_search_cache.json"


# ============ 微博API ============

def get_weibo_token():
    """获取微博API访问令牌（缓存避免重复请求）"""
    # 先检查缓存
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                cache = json.load(f)
            cached_at = cache.get("cached_at", 0)
            expire_in = cache.get("expire_in", 0)
            if time.time() - cached_at < expire_in - 3600:  # 提前1小时刷新
                return cache.get("token")
        except Exception:
            pass

    # 请求新token
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

        # 缓存
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


def search_weibo(query, token):
    """调用微博智搜API"""
    encoded_query = urllib.parse.quote(query)
    url = f"{SEARCH_ENDPOINT}?query={encoded_query}&token={token}"

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


def clean_weibo_markdown(raw_msg):
    """清洗微博智搜返回的markdown内容（第一阶段：去标签）"""
    if not raw_msg:
        return ""

    text = raw_msg

    # 移除 wbCustomBlock JSON块
    text = re.sub(r'```wbCustomBlock\{[^}]*\}\s*[\s\S]*?```', '', text)
    text = re.sub(r'wbCustomBlock\{[^}]*\}', '', text)

    # 移除 media-block HTML块（含内部所有内容）
    text = re.sub(r'<media-block>[\s\S]*?</media-block>', '', text)

    # 清理代码块标记（```plaintext ... ``` → 保留内容，去掉围栏）
    text = re.sub(r'```(?:plaintext|text|markdown|md)?\s*\n?', '', text)
    text = re.sub(r'```', '', text)

    # 移除 HTML 标签但保留内容
    text = re.sub(r'<[^>]+>', '', text)

    # 移除多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 清理开头空白
    text = text.strip()

    return text


def format_qa_sections(raw_text, max_len=1600):
    """
    将AI摘要格式化为Q&A结构，自动识别题目/答案边界并加分隔。
    返回: (question_html, answer_html) — 已含HTML标记
    """
    text = raw_text.strip()
    if not text:
        return "", ""

    # ---- 第一步：Markdown 粗体 → HTML ----
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)

    # ---- 第二步：加粗关键法律术语（仅对不在HTML标签内的文本） ----
    def bold_outside_tags(txt, pattern, template):
        """在非标签文本中应用加粗"""
        parts = re.split(r'(<[^>]+>)', txt)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                result.append(re.sub(pattern, template, part))
        return ''.join(result)

    # 法条引用：《XXX法》第X条
    text = bold_outside_tags(
        text,
        r'(《[^》]+》(?:第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)?)',
        r'<strong class="law">\1</strong>'
    )
    # 法条号 第X条（不在《》内的独立法条号）
    text = bold_outside_tags(
        text,
        r'(?<!\w)(第[一二三四五六七八九十百千\d]+条(?:之[一二三])?)',
        r'<strong class="law">\1</strong>'
    )
    # 金额/期限/百分比
    text = bold_outside_tags(
        text,
        r'(\d+(?:\.\d+)?\s*(?:万元?|元)(?!\w))',
        r'<strong class="num">\1</strong>'
    )

    # ---- 第三步：寻找Q&A边界 ----
    split_pos = None
    # 找第一个 "答案" "解析" 或 "以第X题为例" 等标记
    for pattern_str in [
        r'以第[一二三四五六七八九十百千\d]+题为例',
        r'(?<=\n)(?:###?\s*)?(?:答案|解析|【答案】|【解析】|考点剖析|争议焦点)',
    ]:
        m = re.search(pattern_str, text)
        if m and m.start() > 80:
            split_pos = m.start()
            break

    # 如果没找到明确分隔点，在第2-3段之后分隔
    if split_pos is None:
        paragraphs = re.split(r'\n{2,}', text)
        cum_len = 0
        for i, p in enumerate(paragraphs):
            cum_len += len(p)
            if cum_len > 200 and i >= 1:
                split_pos = len('\n\n'.join(paragraphs[:i+1]))
                break

    # ---- 第四步：切分 ----
    if split_pos and split_pos > 80:
        question_part = text[:split_pos].strip()
        answer_part = text[split_pos:].strip()
    else:
        question_part = text
        answer_part = ""

    # ---- 第五步：长度控制 ----
    if len(question_part) > max_len:
        question_part = question_part[:max_len] + "<br><br>...(内容较长，点击链接查看完整内容)"

    if answer_part and len(answer_part) > max_len:
        answer_part = answer_part[:max_len] + "<br><br>...(内容较长，点击链接查看完整内容)"

    # ---- 第六步：去除AI摘要的开场白 ----
    intro_pattern = re.compile(
        r'^[^。\n<br]{2,25}(?:是|为)(?:法考|法律职业|知名|资深|著名|签约)[^。\n<br]*?[。\n<br]'
    )
    question_part = intro_pattern.sub('', question_part, count=1).strip()

    # 去除可能残留的纯介绍性开头
    if question_part.startswith('<strong') or question_part.startswith('以下'):
        pass  # 保留

    # ---- 第七步：转义残留特殊字符（保护已生成的HTML标签） ----
    def escape_unless_tag(s):
        parts = re.split(r'(<[^>]+>)', s)
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                result.append(part)
            else:
                result.append(part.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
        return ''.join(result)

    question_part = escape_unless_tag(question_part)
    if answer_part:
        answer_part = escape_unless_tag(answer_part)

    # 清理多余分隔线
    question_part = re.sub(r'\n*---+\n*$', '', question_part)
    if answer_part:
        answer_part = re.sub(r'^\n*---+\n*', '', answer_part)

    # 换行 → <br>
    question_part = question_part.replace('\n', '<br>')
    if answer_part:
        answer_part = answer_part.replace('\n', '<br>')

    return question_part, answer_part


def try_search_slot(queries, token):
    """
    对一个科目按优先级依次尝试搜索词，返回第一个成功的结果。
    返回: (source_label, question_html, answer_html, weibo_link, is_alternative) 或 None
    """
    for i, q in enumerate(queries):
        label = q["label"]
        is_alt = i > 0  # 第一个是主师，后面都是替代

        data = search_weibo(q["query"], token)
        if data and not data.get("noContent"):
            raw_msg = data.get("msg", "")
            if len(raw_msg) > 50:
                cleaned = clean_weibo_markdown(raw_msg)
                question_html, answer_html = format_qa_sections(cleaned)
                scheme = data.get("scheme", "")
                weibo_link = scheme.replace("sinaweibo://", "https://weibo.com/") if scheme else ""
                return (label, question_html, answer_html, weibo_link, is_alt)

    return None


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
    """构建简洁Q&A格式HTML邮件"""
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%m月%d日")
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_map[datetime.now(timezone(timedelta(hours=8))).weekday()]

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body {{ font-family: -apple-system,'PingFang SC','Microsoft YaHei',sans-serif; color:#2c3e50; line-height:1.8; max-width:680px; margin:0 auto; padding:0; background:#f5f6fa; }}
.header {{ background: linear-gradient(135deg,#1a1a2e,#16213e); color:#fff; padding:20px 22px; text-align:center; }}
.header h1 {{ margin:0; font-size:18px; font-weight:600; letter-spacing:1px; }}
.header .date {{ font-size:12px; opacity:.7; margin-top:4px; }}
.card {{ background:#fff; margin:10px 12px; border-radius:10px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.06); }}
.card-head {{ padding:12px 16px; display:flex; align-items:center; gap:8px; border-bottom:1px solid #f0f0f0; }}
.card-head .dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
.card-head .name {{ font-weight:600; font-size:14px; }}
.card-head .src {{ font-size:11px; color:#999; }}
.card-head .badge {{ font-size:10px; padding:1px 7px; border-radius:8px; color:#fff; flex-shrink:0; }}
.q-section {{ padding:14px 16px; font-size:13.5px; color:#2c3e50; }}
.q-section .q-label {{ display:inline-block; background:#fff3cd; color:#856404; font-size:10px; padding:2px 8px; border-radius:8px; font-weight:600; margin-bottom:8px; letter-spacing:1px; }}
/* 答案分隔区——大幅留白+分割线 */
.a-divider {{ margin:0 16px; border:none; border-top:2px dashed #e0e0e0; position:relative; height:40px; display:flex; align-items:center; justify-content:center; }}
.a-divider span {{ background:#fff; padding:0 12px; font-size:11px; color:#bbb; letter-spacing:2px; position:absolute; }}
/* 答案区域 */
.a-section {{ padding:6px 16px 18px; font-size:13.5px; color:#555; }}
.a-section .a-label {{ display:inline-block; background:#d4edda; color:#155724; font-size:10px; padding:2px 8px; border-radius:8px; font-weight:600; margin-bottom:8px; letter-spacing:1px; }}
.no-result {{ padding:16px; color:#bbb; font-size:13px; text-align:center; font-style:italic; }}
/* 重点加粗样式 */
strong,strong.law {{ color:#c0392b; font-weight:600; }}
strong.crime {{ color:#e67e22; font-weight:600; }}
strong.num {{ color:#2980b9; font-weight:600; }}
.link-row {{ padding:8px 16px; background:#fafafa; border-top:1px solid #f5f5f5; font-size:12px; }}
.link-row a {{ color:#6c5ce7; text-decoration:none; }}
.link-row a:hover {{ text-decoration:underline; }}
.summary {{ background:#f8f9fa; margin:10px 12px; border-radius:8px; padding:12px 16px; font-size:12px; color:#888; text-align:center; }}
.summary b {{ color:#2c3e50; }}
.footer {{ text-align:center; padding:16px; font-size:10px; color:#ccc; }}
.footer a {{ color:#ccc; }}
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
</div>
"""
    # 统计
    success_count = 0
    alt_count = 0

    for subject, result in slot_results.items():
        color = result.get("color", "#636e72")
        source_label = result.get("source_label", "")
        is_alternative = result.get("is_alternative", False)
        question_html = result.get("question", "")
        answer_html = result.get("answer", "")
        weibo_link = result.get("weibo_link", "")
        error = result.get("error", False)
        has_content = bool(question_html and not error)

        if has_content:
            success_count += 1
            if is_alternative:
                alt_count += 1

        html += '<div class="card">\n'
        html += '  <div class="card-head">\n'
        html += f'    <span class="dot" style="background:{color}"></span>\n'
        html += f'    <span class="name">{subject}</span>\n'
        if has_content and source_label:
            html += f'    <span class="src">{source_label}</span>\n'
        if has_content:
            if is_alternative:
                html += f'    <span class="badge" style="background:#6c5ce7">替代</span>\n'
            else:
                html += f'    <span class="badge" style="background:#27ae60">已更新</span>\n'
        elif error:
            html += f'    <span class="badge" style="background:#f39c12">故障</span>\n'
        else:
            html += f'    <span class="badge" style="background:#bbb">暂无</span>\n'
        html += '  </div>\n'

        if has_content:
            # 判断是否有实质性答案分离
            a_len = len(answer_html) if answer_html else 0
            
            if a_len >= 100:
                # 有足够长的答案：显示Q&A分隔模式
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
                # 答案太短或无法分离：显示为综合摘要
                html += '  <div class="q-section">\n'
                html += '    <span class="q-label">📌 综合摘要</span><br>\n'
                html += f'    {question_html}\n'
                if answer_html:
                    html += '    <br><br><span style="display:inline-block;background:#d4edda;color:#155724;font-size:10px;padding:2px 8px;border-radius:8px;font-weight:600;">✅ 答案</span><br>\n'
                    html += f'    {answer_html}\n'
                else:
                    html += '    <br><br><em style="color:#999;font-size:12px;">（AI摘要未分离出独立答案段落，建议点击下方链接查看原文）</em>\n'
                html += '  </div>\n'
        elif error:
            html += f'  <div class="no-result">⚠️ {error}</div>\n'
        else:
            html += '  <div class="no-result">🔍 今日暂未检索到该科目每日一题</div>\n'

        if weibo_link:
            html += f'  <div class="link-row">🔗 <a href="{weibo_link}">在微博查看原文</a></div>\n'

        html += '</div>\n'

    # 简化汇总
    total = len(slot_results)
    html += '<div class="summary">\n'
    html += f'<b>{success_count}/{total}</b> 科目已获取 · '
    if alt_count > 0:
        html += f'<b>{alt_count}</b> 个使用替代名师 · '
    html += '自动生成于 GitHub Actions</div>\n'

    html += '<div class="footer">\n'
    html += '<p>☁️ 法考云端监控 · 每日8:30 · 主师+替代名师多源抓取</p>\n'
    html += '<p>替代机构：瑞达 厚大 | 民法→钟秀勇/张翔 民诉→韩心怡 三国→殷敏 理论→杜洪波/宋光明</p>\n'
    html += '</div>\n'
    html += '</body></html>'

    return html


# ============ 主流程 ============

def main():
    print(f"===== 法考每日一题 · 微博智搜版（多源替代）=====")
    print(f"执行时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)\n")

    # 获取token
    print("🔑 获取微博API Token...")
    try:
        token = get_weibo_token()
        print(f"   ✅ Token已就绪 (前8位: {token[:8]}...)")
    except Exception as e:
        print(f"   ❌ Token获取失败: {e}")
        fallback_html = f"""<html><body>
<h2>⚠️ 法考每日一题 · 微博API故障</h2>
<p>微博Token获取失败: {e}</p>
<p>时间: {datetime.now(timezone(timedelta(hours=8)))} (GMT+8)</p>
<p>请检查AppId/AppSecret是否有效。</p>
<hr><p style="color:#999;font-size:12px">法考云端监控系统</p>
</body></html>"""
        send_email("⚠️【法考每日一题】微博API故障 | 需检查凭据", fallback_html)
        return

    # 逐个科目搜索
    slot_results = {}
    success_count = 0
    alt_count = 0

    for subject, slot in TEACHER_SLOTS.items():
        display = slot["display_name"]
        queries = slot["queries"]
        color = slot["color"]
        query_count = len(queries)

        print(f"\n🔍 {subject} ({display}) [{query_count}个搜索词]...")

        try:
            result = try_search_slot(queries, token)

            if result:
                source_label, question_html, answer_html, weibo_link, is_alt = result
                content_len = len(question_html) + len(answer_html)
                slot_results[subject] = {
                    "color": color,
                    "source_label": source_label,
                    "question": question_html,
                    "answer": answer_html,
                    "weibo_link": weibo_link,
                    "is_alternative": is_alt,
                    "error": False,
                }
                success_count += 1
                if is_alt:
                    alt_count += 1
                    print(f"   📡 替代源命中: {source_label} ({content_len} 字符)")
                else:
                    print(f"   ✅ 主师命中: {source_label} ({content_len} 字符)")
            else:
                slot_results[subject] = {
                    "color": color,
                    "source_label": "",
                    "question": "",
                    "answer": "",
                    "weibo_link": "",
                    "is_alternative": False,
                    "error": False,
                }
                print(f"   ⚪ 全部{query_count}个搜索词均未命中")
        except Exception as e:
            print(f"   ❌ 错误: {e}")
            slot_results[subject] = {
                "color": color,
                "source_label": "",
                "question": "",
                "answer": "",
                "weibo_link": "",
                "is_alternative": False,
                "error": str(e),
            }

    # 构建报告
    total_slots = len(TEACHER_SLOTS)
    print(f"\n📊 结果: {success_count}/{total_slots} 科目获取成功")
    if alt_count > 0:
        print(f"   📡 其中 {alt_count} 个科目使用了替代名师")

    # 构建alert
    alert_parts = []
    if success_count >= 6:
        alert_parts.append(f'<span class="badge">✨ {success_count}/{total_slots}</span> 个科目通过微博智搜获取')
    elif success_count >= 3:
        alert_parts.append(f'<span class="badge">⚠️ {success_count}/{total_slots}</span> 个科目获取成功')
    else:
        alert_parts.append(f'<span class="badge">❌ {success_count}/{total_slots}</span> 个科目获取成功')
    if alt_count > 0:
        alert_parts.append(f'<span class="badge-alt">📡 {alt_count}替代</span>')

    alert = " ".join(alert_parts)

    # 构建并发送报告
    html = build_html_report(slot_results)

    today_mmdd = datetime.now(timezone(timedelta(hours=8))).strftime("%m/%d")
    subject = f"【法考每日一题】{today_mmdd} | 微博智搜 | {success_count}/{total_slots}已获取"
    if alt_count > 0:
        subject += f"({alt_count}替代)"

    send_email(subject, html)
    print(f"\n✅ 任务完成! 邮件已发送")


if __name__ == "__main__":
    main()
