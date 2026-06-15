#!/usr/bin/env python3
"""
法考每日资讯与押题监控 - 每天8:30执行
监控8位法考名师B站最新更新，搜罗法考热点资讯
通过QQ邮箱推送到 jewelljaja@foxmail.com
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
from duckduckgo_search import DDGS

# ============ 配置 ============
QQ_EMAIL = "jewelljaja@foxmail.com"
QQ_SMTP_CODE = os.environ["QQ_SMTP_CODE"]
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

# 8位法考名师 B站 UID
TEACHERS = {
    "李佳（行政法）": {"uid": "2510840", "bname": "行政法李佳"},
    "柏浪涛（刑法）": {"uid": "3546604065514065", "bname": "刑法柏浪涛"},
    "孟献贵（民法）": {"uid": "3546614072148177", "bname": "民法孟献贵"},
    "戴鹏（民诉）": {"uid": "19568993", "bname": "民诉戴鹏"},
    "左宁（刑诉）": {"uid": "1733061450", "bname": "刑诉左宁"},
    "杨帆（三国法）": {"uid": "276804772", "bname": "三国法杨帆"},
    "马峰（理论法）": {"uid": "3546614072148178", "bname": "理论法马峰"},
    "郄鹏恩（商经知）": {"uid": "3546614065514066", "bname": "商经知郄鹏恩"},
}


def check_bilibili_update(uid, teacher_name):
    """检查B站UP主最近24h的动态"""
    try:
        url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={uid}&pn=1&ps=3"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()

        if data["code"] != 0:
            return None

        videos = data.get("data", {}).get("list", {}).get("vlist", [])
        if not videos:
            return None

        recent = []
        yesterday = datetime.now() - timedelta(days=1)
        for v in videos:
            pub_ts = v.get("created", 0)
            pub_date = datetime.fromtimestamp(pub_ts)
            if pub_date >= yesterday:
                recent.append(
                    {
                        "title": v["title"],
                        "url": f"https://www.bilibili.com/video/{v['bvid']}",
                        "date": pub_date.strftime("%m-%d %H:%M"),
                        "plays": v.get("play", 0),
                    }
                )

        return recent if recent else None
    except Exception as e:
        print(f"  [{teacher_name}] B站检查失败: {e}")
        return None


def search_fakao_news():
    """搜索法考相关最新资讯"""
    news_items = []
    queries = [
        "法考 2026 押题",
        "司法考试 2026 最新动态",
        "法考 考前聚焦 2026",
        "法律职业资格考试 2026 公告",
    ]

    try:
        with DDGS() as ddgs:
            for q in queries:
                results = list(ddgs.text(q, max_results=3))
                for r in results:
                    news_items.append(
                        {
                            "title": r["title"],
                            "url": r["href"],
                            "snippet": r.get("body", "")[:150],
                            "source": q,
                        }
                    )
    except Exception as e:
        print(f"  新闻搜索失败: {e}")

    # 去重
    seen = set()
    unique = []
    for item in news_items:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)
    return unique[:10]


def build_html_report(bilibili_results, news_items):
    """构建HTML邮件报告"""
    today = datetime.now().strftime("%Y年%m月%d日")

    html = f"""<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; color: #333; line-height: 1.8; }}
h2 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 6px; }}
h3 {{ color: #2c3e50; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th {{ background: #2c3e50; color: #fff; padding: 8px 12px; text-align: left; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #ddd; }}
tr:hover {{ background: #f9f9f9; }}
.tag {{ display: inline-block; background: #e74c3c; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 12px; margin-right: 4px; }}
.tag-new {{ background: #27ae60; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
hr {{ border: none; border-top: 1px dashed #ccc; margin: 20px 0; }}
.footer {{ color: #999; font-size: 12px; margin-top: 20px; }}
</style></head><body>
<h2>📚 法考每日资讯 | {today}</h2>

<h3>一、名师B站动态</h3>
<table>
<tr><th>老师</th><th>最新视频</th><th>时间</th><th>播放</th></tr>
"""

    has_bilibili = False
    for name, videos in bilibili_results.items():
        if videos:
            has_bilibili = True
            for v in videos[:2]:
                html += f'<tr><td><strong>{name}</strong></td><td><a href="{v["url"]}">{v["title"]}</a></td><td>{v["date"]}</td><td>{v["plays"]}</td></tr>\n'

    if not has_bilibili:
        html += '<tr><td colspan="4" style="text-align:center;color:#999;">近24h暂无新动态</td></tr>\n'

    html += "</table>\n"

    html += '<h3>二、法考热点资讯</h3>\n<table>\n<tr><th>标题</th><th>来源</th></tr>\n'
    for item in news_items:
        source_tag = item["source"].replace(" ", "·")
        html += f'<tr><td><a href="{item["url"]}">{item["title"]}</a><br><small>{item["snippet"]}</small></td><td><span class="tag">{source_tag}</span></td></tr>\n'
    html += "</table>\n"

    html += '<hr>\n<div class="footer">'
    html += f'<p>📬 法考每日监控系统自动生成 | {today}</p>'
    html += "<p>数据来源：B站API、DuckDuckGo搜索</p>"
    html += "<p>Powered by GitHub Actions ☁️ | 真正的无人值守</p>"
    html += "</div>\n</body></html>"

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
        print("✅ 邮件发送成功")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


def main():
    print(f"===== 法考每日资讯监控 =====")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. B站检查
    print("[1/3] 检查B站名师动态...")
    bilibili_results = {}
    for name, info in TEACHERS.items():
        print(f"  检查 {name}...")
        result = check_bilibili_update(info["uid"], name)
        bilibili_results[name] = result

    # 2. 搜索法考资讯
    print("\n[2/3] 搜索法考热点资讯...")
    news_items = search_fakao_news()
    print(f"  获取到 {len(news_items)} 条资讯")

    # 3. 发送邮件
    print("\n[3/3] 构建报告并发送邮件...")
    html = build_html_report(bilibili_results, news_items)
    today_str = datetime.now().strftime("%m/%d")
    subject = f"【法考日报】{today_str} | 名师动态+热点资讯"

    send_email(subject, html)
    print("\n✅ 任务完成!")


if __name__ == "__main__":
    main()
