#!/usr/bin/env python3
"""
竹知了事件官媒追踪 - 每天20:00执行
搜索官媒对竹知了事件的报道和华为/余承东的公开回应
通过QQ邮箱SMTP发送到 jewelljaja@foxmail.com
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from ddgs import DDGS

# ============ 配置 ============
QQ_EMAIL = "jewelljaja@foxmail.com"
QQ_SMTP_CODE = os.environ["QQ_SMTP_CODE"]
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zhuzhilao_state.json")

# 官媒域名白名单
OFFICIAL_MEDIA_DOMAINS = {
    "people.com.cn": "人民日报",
    "xinhuanet.com": "新华社",
    "cctv.com": "央视新闻",
    "news.cctv.com": "央视新闻",
    "gmw.cn": "光明日报",
    "ce.cn": "经济日报",
    "chinanews.com": "中国新闻网",
    " chinanews.com.cn": "中国新闻网",
    "huanqiu.com": "环球时报",
    "cankaoxiaoxi.com": "参考消息",
    "cyol.com": "中国青年报",
    "legaldaily.com.cn": "法治日报",
    "worker.cn": "工人日报",
    "stdaily.com": "科技日报",
    "youth.cn": "中国青年网",
    "china.com.cn": "中国网",
    "cnr.cn": "央广网",
    "thepaper.cn": "澎湃新闻",
    "caixin.com": "财新网",
}

# 搜索关键词组
SEARCH_QUERIES = [
    "竹知了 华为 官方 回应 声明",
    "竹知了事件 人民日报 新华社 央视",
    "余承东 竹知了 回应",
    "竹知了 官媒 评论 定性",
    "华为 竹知了 法务 投诉 官方回应",
    "竹知了 余承东 发声 辟谣",
    "竹知了事件 官方通报",
]


def is_official_media(url):
    """检查URL是否来自官媒"""
    if not url:
        return None
    url_lower = url.lower()
    for domain, name in OFFICIAL_MEDIA_DOMAINS.items():
        if domain in url_lower:
            return name
    return None


def is_huawei_response(title, snippet):
    """检测是否为华为/余承东官方回应"""
    keywords = ["华为回应", "华为声明", "华为官方", "余承东回应", "余承东发声",
                "余承东回应竹知了", "华为回应竹知了", "华为辟谣", "华为官方声明"]
    text = f"{title} {snippet}".lower()
    for kw in keywords:
        if kw in text:
            return True
    return False


def search_news():
    """搜索竹知了事件相关新闻"""
    all_results = []
    official_results = []
    huawei_response_results = []
    other_results = []

    try:
        with DDGS() as ddgs:
            for q in SEARCH_QUERIES:
                try:
                    results = list(ddgs.text(q, max_results=8))
                    for r in results:
                        url = r.get("href", "") or r.get("url", "")
                        title = r.get("title", "")
                        snippet = r.get("body", "") or r.get("snippet", "")

                        if not url or not title:
                            continue

                        item = {
                            "title": title,
                            "url": url,
                            "snippet": snippet[:300] if snippet else "",
                            "source_query": q,
                        }

                        # 去重
                        if any(x["url"] == url for x in all_results):
                            continue
                        all_results.append(item)

                        media_name = is_official_media(url)
                        is_huawei = is_huawei_response(title, snippet)

                        if is_huawei:
                            item["media"] = media_name or "其他"
                            item["type"] = "huawei_response"
                            huawei_response_results.append(item)
                        elif media_name:
                            item["media"] = media_name
                            item["type"] = "official"
                            official_results.append(item)
                        else:
                            item["media"] = "其他"
                            item["type"] = "other"
                            other_results.append(item)

                except Exception as e:
                    print(f"  搜索 '{q}' 失败: {e}")
                    continue
    except Exception as e:
        print(f"  DDGS初始化失败: {e}")

    return huawei_response_results, official_results, other_results


def load_state():
    """加载历史状态（已报道的URL集合）"""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"reported_urls": [], "last_run": ""}


def save_state(state, new_urls):
    """保存状态"""
    reported = set(state.get("reported_urls", []))
    reported.update(new_urls)
    state["reported_urls"] = list(reported)[-200:]  # 保留最近200条
    state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def filter_new(items, reported_urls):
    """筛选出未报道过的新内容"""
    reported_set = set(reported_urls)
    new_items = [item for item in items if item["url"] not in reported_set]
    return new_items


def build_html_report(huawei_items, official_items, other_items, has_new):
    """构建HTML邮件报告"""
    today = datetime.now().strftime("%Y年%m月%d日")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; color: #333; line-height: 1.8; max-width: 800px; margin: 0 auto; }}
h2 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 6px; }}
h3 {{ color: #2c3e50; margin-top: 25px; }}
.card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin: 12px 0; background: #fafafa; }}
.card-huawei {{ border-left: 4px solid #e74c3c; background: #fef5f5; }}
.card-official {{ border-left: 4px solid #2980b9; }}
.card-other {{ border-left: 4px solid #95a5a6; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 12px; color: #fff; margin-right: 6px; }}
.badge-huawei {{ background: #e74c3c; }}
.badge-official {{ background: #2980b9; }}
.badge-other {{ background: #95a5a6; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.snippet {{ color: #555; font-size: 14px; margin-top: 6px; }}
.footer {{ color: #999; font-size: 12px; margin-top: 30px; border-top: 1px dashed #ccc; padding-top: 15px; }}
.empty {{ text-align: center; color: #999; padding: 30px; }}
.alert {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; padding: 12px; margin: 15px 0; }}
</style></head><body>
<h2>📢 竹知了事件 · 官媒追踪 | {today}</h2>
"""

    # 华为/余承东回应（最高优先级）
    if huawei_items:
        html += '<h3>🔥 华为/余承东公开回应</h3>\n'
        for item in huawei_items:
            html += f"""<div class="card card-huawei">
<span class="badge badge-huawei">华为回应</span>
<span class="badge badge-official">{item.get('media', '')}</span>
<br><strong><a href="{item['url']}">{item['title']}</a></strong>
<div class="snippet">{item['snippet']}</div>
</div>\n"""
    else:
        html += '<div class="alert">ℹ️ 华为/余承东暂无公开回应</div>\n'

    # 官媒报道
    html += '<h3>📰 官媒报道</h3>\n'
    if official_items:
        for item in official_items:
            html += f"""<div class="card card-official">
<span class="badge badge-official">{item['media']}</span>
<br><strong><a href="{item['url']}">{item['title']}</a></strong>
<div class="snippet">{item['snippet']}</div>
</div>\n"""
    else:
        html += '<div class="empty">今日官媒无新报道，事件仍在发酵中</div>\n'

    # 其他来源（非官媒但有价值的报道）
    if other_items:
        html += '<h3>📋 其他报道（非官媒）</h3>\n'
        for item in other_items[:5]:
            html += f"""<div class="card card-other">
<span class="badge badge-other">其他</span>
<br><strong><a href="{item['url']}">{item['title']}</a></strong>
<div class="snippet">{item['snippet']}</div>
</div>\n"""

    # 页脚
    html += f"""<div class="footer">
<p>📡 竹知了事件官媒追踪系统 | 检索时间: {now_str}</p>
<p>数据来源: DuckDuckGo搜索 + 官媒域名筛选</p>
<p>监控目标: 人民日报·新华社·央视·光明日报·经济日报·中国新闻网·环球时报·参考消息·中国青年报·法治日报</p>
<p>Powered by GitHub Actions ☁️ | 真正的无人值守</p>
</div>
</body></html>"""

    return html


def send_email(subject, html_body):
    """通过QQ邮箱SMTP发送邮件"""
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
        print("  邮件发送成功")
        return True
    except Exception as e:
        print(f"  邮件发送失败: {e}")
        return False


def main():
    print("=" * 50)
    print("竹知了事件官媒追踪")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)

    # 1. 搜索新闻
    print("\n[1/3] 搜索新闻...")
    huawei_items, official_items, other_items = search_news()
    print(f"  华为回应: {len(huawei_items)} 条")
    print(f"  官媒报道: {len(official_items)} 条")
    print(f"  其他来源: {len(other_items)} 条")

    # 2. 去重（只报告新内容）
    print("\n[2/3] 筛选新内容...")
    state = load_state()
    reported_urls = state.get("reported_urls", [])

    new_huawei = filter_new(huawei_items, reported_urls)
    new_official = filter_new(official_items, reported_urls)
    new_other = filter_new(other_items, reported_urls)

    all_new_urls = [item["url"] for item in new_huawei + new_official + new_other]

    total_new = len(new_huawei) + len(new_official) + len(new_other)
    print(f"  新华为回应: {len(new_huawei)} 条")
    print(f"  新官媒报道: {len(new_official)} 条")
    print(f"  新其他来源: {len(new_other)} 条")
    print(f"  合计新内容: {total_new} 条")

    # 3. 构建报告并发送
    print("\n[3/3] 构建报告并发送邮件...")

    # 即使没有新内容，如果有华为回应也始终发送
    # 如果没有新内容，仍然发送一封"暂无新动态"的邮件
    has_huawei = len(huawei_items) > 0  # 华为回应无论新旧都报告
    has_any_new = total_new > 0

    # 如果有华为回应（不管新旧），或者有新的官媒报道，都发邮件
    should_send = has_huawei or has_any_new

    if should_send:
        html = build_html_report(
            huawei_items if has_huawei else [],
            new_official if has_any_new else [],
            new_other if has_any_new else [],
            has_any_new
        )
        today_str = datetime.now().strftime("%m/%d")
        if has_huawei:
            subject = f"【竹知了官媒追踪】{today_str} - 华为有公开回应！"
        elif has_any_new:
            subject = f"【竹知了官媒追踪】{today_str} - 有新报道"
        else:
            subject = f"【竹知了官媒追踪】{today_str} - 暂无官媒新动态"

        send_email(subject, html)
    else:
        # 无新内容，发送简短通知
        html = build_html_report([], [], [], False)
        today_str = datetime.now().strftime("%m/%d")
        subject = f"【竹知了官媒追踪】{today_str} - 暂无官媒新动态"
        send_email(subject, html)

    # 保存状态
    save_state(state, all_new_urls)
    print("\n  状态已保存")

    print("\n" + "=" * 50)
    print("任务完成!")
    print("=" * 50)


if __name__ == "__main__":
    main()
