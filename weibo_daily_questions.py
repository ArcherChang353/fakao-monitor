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
    """清洗微博智搜返回的markdown内容"""
    if not raw_msg:
        return ""

    text = raw_msg

    # 移除 wbCustomBlock JSON块
    text = re.sub(r'```wbCustomBlock\{[^}]*\}\s*[\s\S]*?```', '', text)
    text = re.sub(r'wbCustomBlock\{[^}]*\}', '', text)

    # 移除 media-block HTML块（含内部所有内容）
    text = re.sub(r'<media-block>[\s\S]*?</media-block>', '', text)

    # 移除 HTML 标签但保留内容
    text = re.sub(r'<[^>]+>', '', text)

    # 移除多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 清理开头空白
    text = text.strip()

    # 截取合理长度（邮件不宜过长）
    if len(text) > 2000:
        text = text[:2000] + "\n\n...(内容过长已截断，点击上方链接查看完整内容)"

    return text


def try_search_slot(queries, token):
    """
    对一个科目按优先级依次尝试搜索词，返回第一个成功的结果。
    返回: (source_label, content, weibo_link, is_alternative) 或 None
    """
    for i, q in enumerate(queries):
        label = q["label"]
        is_alt = i > 0  # 第一个是主师，后面都是替代

        data = search_weibo(q["query"], token)
        if data and not data.get("noContent"):
            raw_msg = data.get("msg", "")
            if len(raw_msg) > 50:
                cleaned = clean_weibo_markdown(raw_msg)
                scheme = data.get("scheme", "")
                weibo_link = scheme.replace("sinaweibo://", "https://weibo.com/") if scheme else ""
                return (label, cleaned, weibo_link, is_alt)

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
    """构建HTML邮件"""
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_map[datetime.now(timezone(timedelta(hours=8))).weekday()]

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #2c3e50; line-height: 1.8; max-width: 720px; margin: 20px auto; padding: 0 16px; }}
.header {{ background: linear-gradient(135deg, #c0392b, #e74c3c); color: #fff; padding: 24px 28px; border-radius: 12px 12px 0 0; margin-bottom: 0; }}
.header h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
.header .sub {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}
.alert {{ background: #ffeaa7; border-left: 4px solid #fdcb6e; padding: 12px 16px; margin: 12px 0; border-radius: 4px; font-size: 14px; }}
.alert .badge {{ background: #e74c3c; color: #fff; border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: bold; margin-right: 4px; }}
.alert .badge-alt {{ background: #6c5ce7; color: #fff; border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: bold; }}
.card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; margin: 14px 0; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.card-header {{ padding: 14px 18px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
.card-header .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}
.card-header .subject {{ font-weight: 600; font-size: 15px; }}
.card-header .source {{ font-size: 12px; color: #888; margin-left: 4px; }}
.card-header .tag {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; color: #fff; flex-shrink: 0; }}
.card-header .tag-alt {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; color: #fff; flex-shrink: 0; background: #6c5ce7; }}
.card-body {{ padding: 14px 18px; font-size: 13.5px; }}
.card-body p {{ margin: 4px 0; }}
.card-body h1, .card-body h2, .card-body h3 {{ font-size: 15px; margin: 8px 0 4px; color: #c0392b; }}
.card-body strong {{ color: #2c3e50; }}
.link-row {{ padding: 10px 18px; border-top: 1px solid #f5f5f5; background: #fafafa; font-size: 13px; }}
.link-row a {{ color: #2980b9; text-decoration: none; }}
.link-row a:hover {{ text-decoration: underline; }}
.no-result {{ color: #bdc3c7; font-style: italic; padding: 14px 18px; }}
.summary {{ background: #f8f9fa; border-radius: 8px; padding: 16px; margin: 14px 0; font-size: 13px; }}
.summary table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
.summary th {{ background: #2c3e50; color: #fff; padding: 6px 10px; text-align: left; font-weight: 500; }}
.summary td {{ padding: 5px 10px; border-bottom: 1px solid #eee; }}
.status-active {{ color: #27ae60; font-weight: 600; }}
.status-alt {{ color: #6c5ce7; font-weight: 600; }}
.status-inactive {{ color: #95a5a6; }}
.footer {{ color: #999; font-size: 11px; text-align: center; margin: 24px 0; padding: 16px; }}
.footer a {{ color: #999; }}
.legend {{ font-size: 11px; color: #999; margin-top: 4px; }}
@media (prefers-color-scheme: dark) {{
  body {{ background: #1a1a2e; color: #ddd; }}
  .card {{ background: #16213e; border-color: #0f3460; }}
  .card-header {{ border-color: #0f3460; }}
  .card-body strong {{ color: #eee; }}
  .link-row {{ background: #0f3460; border-color: #1a1a2e; }}
  .link-row a {{ color: #74b9ff; }}
  .summary {{ background: #16213e; }}
  .summary td {{ border-color: #0f3460; }}
  .no-result {{ color: #636e72; }}
}}
</style></head><body>
<div class="header">
  <h1>📝 法考每日一题 | 微博智搜版（多源替代）</h1>
  <div class="sub">{today} {weekday} · 8大学科 · AI智能总结 · 主师+替代名师</div>
</div>
"""

    # 统计
    success_count = 0
    alt_count = 0

    for subject, result in slot_results.items():
        color = result.get("color", "#636e72")

        html += f'<div class="card">\n'
        html += f'  <div class="card-header">\n'
        html += f'    <span class="dot" style="background:{color}"></span>\n'
        html += f'    <span class="subject">{subject}</span>\n'

        source_label = result.get("source_label", "")
        is_alternative = result.get("is_alternative", False)
        content = result.get("content", "")
        weibo_link = result.get("weibo_link", "")

        if content and not result.get("error"):
            success_count += 1
            if is_alternative:
                alt_count += 1
                html += f'    <span class="source">{source_label}</span>\n'
                html += f'    <span class="tag-alt">📡替代源</span>\n'
            else:
                html += f'    <span class="source">{source_label}</span>\n'
                html += f'    <span class="tag" style="background:#27ae60">AI已总结</span>\n'
        elif result.get("error"):
            html += f'    <span class="tag" style="background:#f39c12">获取失败</span>\n'
        else:
            html += f'    <span class="tag" style="background:#95a5a6">暂未搜到</span>\n'

        html += f'  </div>\n'

        if content and not result.get("error"):
            clean_content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            clean_content = clean_content.replace("\n", "<br>")
            html += f'  <div class="card-body">{clean_content}</div>\n'
        elif result.get("error"):
            html += f'  <div class="no-result">⚠️ {result["error"]}</div>\n'
        else:
            html += f'  <div class="no-result">🔍 微博智搜暂未检索到该科目每日一题，主师及替代名师均未命中。</div>\n'

        if weibo_link:
            html += f'  <div class="link-row">🔗 <a href="{weibo_link}">在微博查看原文</a></div>\n'

        html += f'</div>\n'

    # 汇总表
    html += '<div class="summary"><strong>📊 今日覆盖率</strong>\n<table>\n<tr><th>科目</th><th>来源</th><th>状态</th></tr>\n'
    for subject, result in slot_results.items():
        content = result.get("content", "")
        source_label = result.get("source_label", "")
        is_alt = result.get("is_alternative", False)
        error = result.get("error", False)

        if content and not error:
            if is_alt:
                status = f'<span class="status-alt">📡 替代源</span>'
            else:
                status = '<span class="status-active">✅ 已获取</span>'
        elif error:
            status = '<span class="status-inactive">获取失败</span>'
        else:
            status = '<span class="status-inactive">暂未获取</span>'

        source_short = source_label.replace("📡替代", "").strip() if source_label else "-"
        html += f'<tr><td>{subject}</td><td>{source_short}</td><td>{status}</td></tr>\n'
    html += '</table>'

    if alt_count > 0:
        html += f'<p class="legend">📡 共 {alt_count} 个科目使用了替代名师（主师无内容时自动切换）</p>'
    html += '</div>\n'

    html += f"""<div class="footer">
<p>☁️ 本报告由法考云端监控系统自动生成 · GitHub Actions · 微博智搜AI | 每日8:30推送</p>
<p>数据来源：微博龙虾助手（open-im.api.weibo.com）· 主师+替代名师多源抓取</p>
<p>替代机构：瑞达、厚大、华图 | 民诉→韩心怡 三国法→殷敏 理论法→杜洪波/宋光明 民法→钟秀勇/张翔</p>
<p><a href="https://github.com/ArcherChang353/fakao-monitor">GitHub 仓库</a></p>
</div>
</body></html>"""

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
                source_label, content, weibo_link, is_alt = result
                slot_results[subject] = {
                    "color": color,
                    "source_label": source_label,
                    "content": content,
                    "weibo_link": weibo_link,
                    "is_alternative": is_alt,
                    "error": False,
                }
                success_count += 1
                if is_alt:
                    alt_count += 1
                    print(f"   📡 替代源命中: {source_label} ({len(content)} 字符)")
                else:
                    print(f"   ✅ 主师命中: {source_label} ({len(content)} 字符)")
            else:
                slot_results[subject] = {
                    "color": color,
                    "source_label": "",
                    "content": "",
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
                "content": "",
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
