#!/usr/bin/env python3
"""
法考每日一题抓取 - 微博智搜版（方案终极版）
通过微博龙虾助手API搜索8位名师每日一题，获取完整内容摘要
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

# 8位老师搜索配置
TEACHERS = {
    "李佳（行政法）": {
        "query": "行政法李佳 每日一题",
        "active": True,
    },
    "柏浪涛（刑法）": {
        "query": "柏浪涛 每日一题",
        "active": True,
    },
    "孟献贵（民法）": {
        "query": "孟献贵 每日一题",
        "active": True,   # API偶尔返回空，容错处理
    },
    "戴鹏（民诉）": {
        "query": "戴鹏 每日一题",
        "active": False,  # 无独立每日一题系列
    },
    "左宁（刑诉）": {
        "query": "左宁 每日一题",
        "active": True,
    },
    "杨帆（三国法）": {
        "query": "杨帆 每日一题",
        "active": False,  # 2026版尚未开始
    },
    "马峰（理论法）": {
        "query": "马峰 每日一题",
        "active": False,  # 2026版尚未开始
    },
    "郄鹏恩（商经知）": {
        "query": "郄鹏恩 每日一题",
        "active": True,
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
        print(f"    搜索异常: {e}")
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

def build_html_report(results, alert_info):
    """构建HTML邮件"""
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y年%m月%d日")
    weekday_map = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_map[datetime.now(timezone(timedelta(hours=8))).weekday()]

    color_map = {
        "李佳": "#e74c3c",
        "柏浪涛": "#e67e22",
        "孟献贵": "#2980b9",
        "戴鹏": "#8e44ad",
        "左宁": "#27ae60",
        "杨帆": "#16a085",
        "马峰": "#2c3e50",
        "郄鹏恩": "#d35400",
    }

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #2c3e50; line-height: 1.8; max-width: 720px; margin: 20px auto; padding: 0 16px; }}
.header {{ background: linear-gradient(135deg, #c0392b, #e74c3c); color: #fff; padding: 24px 28px; border-radius: 12px 12px 0 0; margin-bottom: 0; }}
.header h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
.header .sub {{ font-size: 13px; opacity: 0.85; margin-top: 4px; }}
.alert {{ background: #ffeaa7; border-left: 4px solid #fdcb6e; padding: 12px 16px; margin: 12px 0; border-radius: 4px; font-size: 14px; }}
.alert .badge {{ background: #e74c3c; color: #fff; border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: bold; margin-right: 4px; }}
.card {{ background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; margin: 14px 0; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
.card-header {{ padding: 14px 18px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 10px; }}
.card-header .dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}
.card-header .name {{ font-weight: 600; font-size: 15px; }}
.card-header .tag {{ font-size: 11px; padding: 2px 8px; border-radius: 10px; color: #fff; flex-shrink: 0; }}
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
.status-inactive {{ color: #95a5a6; }}
.footer {{ color: #999; font-size: 11px; text-align: center; margin: 24px 0; padding: 16px; }}
.footer a {{ color: #999; }}
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
  <h1>📝 法考每日一题 | 微博智搜版</h1>
  <div class="sub">{today} {weekday} · 8位名师 · AI智能总结</div>
</div>
"""

    if alert_info:
        html += f'<div class="alert">{alert_info}</div>\n'

    for teacher_key, result in results.items():
        # 提取老师简称
        name_full = teacher_key
        surname = teacher_key[0]  # 姓
        color = color_map.get(surname, "#636e72")
        is_active = result.get("active", True)

        html += f'<div class="card">\n'
        html += f'  <div class="card-header">\n'
        html += f'    <span class="dot" style="background:{color}"></span>\n'
        html += f'    <span class="name">{name_full}</span>\n'

        if not is_active:
            html += f'    <span class="tag" style="background:#95a5a6">2026版未发布</span>\n'
        elif result.get("error"):
            html += f'    <span class="tag" style="background:#f39c12">获取失败</span>\n'
        elif result.get("no_content"):
            html += f'    <span class="tag" style="background:#95a5a6">暂未搜到</span>\n'
        else:
            html += f'    <span class="tag" style="background:#27ae60">AI已总结</span>\n'

        html += f'  </div>\n'

        content = result.get("content", "")
        weibo_link = result.get("weibo_link", "")

        if not is_active:
            html += f'  <div class="no-result">⏳ 该老师2026版每日一题尚未发布，后续将自动追踪。</div>\n'
        elif result.get("error"):
            html += f'  <div class="no-result">⚠️ {result["error"]}</div>\n'
        elif result.get("no_content"):
            html += f'  <div class="no-result">🔍 微博智搜暂未检索到相关内容，可能尚未发布或内容较新。</div>\n'
        elif content:
            # 转义HTML特殊字符并保留换行
            clean_content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            clean_content = clean_content.replace("\n", "<br>")
            html += f'  <div class="card-body">{clean_content}</div>\n'

        if weibo_link:
            html += f'  <div class="link-row">🔗 <a href="{weibo_link}">在微博查看原文</a></div>\n'

        html += f'</div>\n'

    # 汇总表
    html += '<div class="summary"><strong>📊 今日覆盖率</strong>\n<table>\n<tr><th>老师</th><th>科目</th><th>状态</th></tr>\n'
    for teacher_key, result in results.items():
        surname = teacher_key[0]
        parts = teacher_key.replace("（", "|").replace("）", "").split("|")
        name = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        is_active = result.get("active", True)
        if not is_active:
            status = '<span class="status-inactive">未发布</span>'
        elif result.get("error") or result.get("no_content"):
            status = '<span class="status-inactive">暂未获取</span>'
        else:
            status = '<span class="status-active">✅ 已获取</span>'
        html += f'<tr><td>{name}</td><td>{subject}</td><td>{status}</td></tr>\n'
    html += '</table></div>\n'

    html += f"""<div class="footer">
<p>☁️ 本报告由法考云端监控系统自动生成 · GitHub Actions · 微博智搜AI | 每日8:30推送</p>
<p>数据来源：微博龙虾助手（open-im.api.weibo.com）</p>
<p><a href="https://github.com/ArcherChang353/fakao-monitor">GitHub 仓库</a></p>
</div>
</body></html>"""

    return html


# ============ 主流程 ============

def main():
    print(f"===== 法考每日一题 · 微博智搜版 =====")
    print(f"执行时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')} (GMT+8)\n")

    # 获取token
    print("🔑 获取微博API Token...")
    try:
        token = get_weibo_token()
        print(f"   ✅ Token已就绪 (前8位: {token[:8]}...)")
    except Exception as e:
        print(f"   ❌ Token获取失败: {e}")
        # 兜底：发一封简单的错误通知邮件
        fallback_html = f"""<html><body>
<h2>⚠️ 法考每日一题 · 微博API故障</h2>
<p>微博Token获取失败: {e}</p>
<p>时间: {datetime.now(timezone(timedelta(hours=8)))}, (GMT+8)</p>
<p>请检查AppId/AppSecret是否有效。</p>
<hr><p style="color:#999;font-size:12px">法考云端监控系统</p>
</body></html>"""
        send_email("⚠️【法考每日一题】微博API故障 | 需检查凭据", fallback_html)
        return

    # 搜索每位老师
    results = {}
    success_count = 0
    active_count = 0

    for teacher_key, config in TEACHERS.items():
        print(f"\n🔍 {teacher_key}...")

        if not config["active"]:
            print(f"   ⏸️  2026版未发布，跳过")
            results[teacher_key] = {"active": False, "content": "", "weibo_link": ""}
            continue

        active_count += 1

        try:
            data = search_weibo(config["query"], token)

            if data and not data.get("noContent"):
                raw_msg = data.get("msg", "")
                if len(raw_msg) > 50:  # 有实质内容
                    cleaned = clean_weibo_markdown(raw_msg)
                    scheme = data.get("scheme", "")
                    weibo_link = scheme.replace("sinaweibo://", "https://weibo.com/") if scheme else ""

                    results[teacher_key] = {
                        "active": True,
                        "content": cleaned,
                        "weibo_link": weibo_link,
                        "error": False,
                        "no_content": False,
                    }
                    success_count += 1
                    print(f"   ✅ 获取成功 ({len(cleaned)} 字符)")
                else:
                    # API返回了结果但msg为空（偶尔发生）
                    results[teacher_key] = {
                        "active": True,
                        "content": "",
                        "weibo_link": "",
                        "error": False,
                        "no_content": True,
                    }
                    print(f"   ⚠️ API返回空内容（rare）")
            else:
                results[teacher_key] = {
                    "active": True,
                    "content": "",
                    "weibo_link": "",
                    "error": False,
                    "no_content": True,
                }
                print(f"   ⚪ 未搜到内容")
        except Exception as e:
            print(f"   ❌ 错误: {e}")
            results[teacher_key] = {
                "active": True,
                "content": "",
                "weibo_link": "",
                "error": str(e),
                "no_content": False,
            }

    # 构建报告
    print(f"\n📊 结果: {success_count}/{active_count} 位活跃老师获取成功")

    alert = ""
    if success_count >= 4:
        today_str = datetime.now(timezone(timedelta(hours=8))).strftime("%m/%d")
        alert = f'<span class="badge">✨ {success_count}/{active_count}</span> 位老师每日一题已通过微博智搜AI获取，内容摘要见下方。'
    elif success_count > 0:
        alert = f'<span class="badge">⚠️ {success_count}/{active_count}</span> 位老师获取成功，部分未获取。'
    else:
        alert = f'<span class="badge">❌</span> 所有老师均未获取到内容，请检查API状态。'

    html = build_html_report(results, alert)

    today_mmdd = datetime.now(timezone(timedelta(hours=8))).strftime("%m/%d")
    subject = f"【法考每日一题】{today_mmdd} | 微博智搜 | {success_count}/{active_count}位已获取"

    send_email(subject, html)
    print(f"\n✅ 任务完成! 邮件已发送")


if __name__ == "__main__":
    main()
