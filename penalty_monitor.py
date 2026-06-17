#!/usr/bin/env python3
"""
法律咨询公司 & 网推所处罚监控 - 每天11:00执行
搜索各地对法律咨询公司、网推所的行政处罚/行业处分
通过QQ邮箱推送到 jewelljaja@foxmail.com
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
from ddgs import DDGS

# ============ 配置 ============
QQ_EMAIL = "jewelljaja@foxmail.com"
QQ_SMTP_CODE = os.environ["QQ_SMTP_CODE"]
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

# 多轮搜索关键词
SEARCH_QUERIES = [
    "法律咨询公司 违规 处罚 司法局 2026",
    "律师事务所 行政处罚 停业整顿 2026",
    "网推所 违规 司法局 处罚",
    "法律咨询公司 诈骗 判决 2025 2026",
    "律师 与 法律公司 合作 违规 处罚",
    "司法局 法律咨询公司 超范围经营",
]


def search_penalty_cases():
    """搜索法律咨询公司/网推所处罚案例"""
    all_results = []

    try:
        with DDGS() as ddgs:
            for q in SEARCH_QUERIES:
                try:
                    results = list(ddgs.text(q, max_results=3, region="cn-zh"))
                    for r in results:
                        all_results.append(
                            {
                                "title": r["title"],
                                "url": r["href"],
                                "snippet": r.get("body", "")[:200],
                                "query": q,
                            }
                        )
                except Exception as e:
                    print(f"  搜索 '{q[:20]}...' 失败: {e}")
    except Exception as e:
        print(f"  搜索模块初始化失败: {e}")

    # 去重排序
    seen_urls = set()
    unique = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique.append(item)

    # 按关键词分组
    return unique[:15]


def categorize_results(results):
    """将结果按类别分组"""
    categories = {
        "🚫 律所处罚/停业整顿": [],
        "⚖️ 法律咨询公司违规": [],
        "📋 行业规范/新规": [],
        "🔍 其他相关": [],
    }

    for r in results:
        title = r["title"].lower()
        if any(kw in title for kw in ["律所", "律师事务", "停业", "吊销", "整顿", "处罚决定"]):
            categories["🚫 律所处罚/停业整顿"].append(r)
        elif any(kw in title for kw in ["法律咨询公司", "法律公司", "法务公司", "超范围"]):
            categories["⚖️ 法律咨询公司违规"].append(r)
        elif any(kw in title for kw in ["规定", "办法", "通知", "规范", "整治", "专项行动"]):
            categories["📋 行业规范/新规"].append(r)
        else:
            categories["🔍 其他相关"].append(r)

    return {k: v for k, v in categories.items() if v}


def build_html_report(categories):
    """构建HTML邮件报告"""
    today = datetime.now().strftime("%Y年%m月%d日")

    html = f"""<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; color: #333; line-height: 1.8; }}
h2 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 6px; }}
h3 {{ color: #2c3e50; margin-top: 20px; }}
.card {{ background: #fdf2f2; border-left: 4px solid #e74c3c; padding: 10px 16px; margin: 8px 0; border-radius: 4px; }}
.card-info {{ background: #f0f8ff; border-left-color: #3498db; }}
.card-rule {{ background: #fffdf0; border-left-color: #f39c12; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.snippet {{ color: #666; font-size: 13px; margin-top: 4px; }}
hr {{ border: none; border-top: 1px dashed #ccc; margin: 20px 0; }}
.footer {{ color: #999; font-size: 12px; margin-top: 20px; }}
.warn {{ background: #ffeaa7; padding: 8px 12px; border-radius: 4px; margin: 12px 0; }}
</style></head><body>
<h2>⚖️ 法律咨询公司 & 网推所处罚监控 | {today}</h2>

<div class="warn">
🔔 <strong>法考关联提示</strong>：此类案例涉及《律师法》第47-50条、行政处罚程序、律师执业纪律——行政法&司法制度高频考点
</div>
"""

    icon_map = {
        "🚫 律所处罚/停业整顿": "card",
        "⚖️ 法律咨询公司违规": "card-info",
        "📋 行业规范/新规": "card-rule",
        "🔍 其他相关": "card-info",
    }

    for cat_name, items in categories.items():
        html += f"<h3>{cat_name}</h3>\n"
        for item in items:
            css_class = icon_map.get(cat_name, "card-info")
            snippet = item.get("snippet", "")[:150]
            html += f"""<div class="{css_class}">
<a href="{item['url']}"><strong>{item['title']}</strong></a>
<div class="snippet">{snippet}...</div>
</div>\n"""

    html += f"""
<hr>
<h3>📌 关注要点</h3>
<ol>
<li><strong>《律师法》第50条</strong>——律师事务所有下列行为之一的，由设区的市级或者直辖市的区人民政府司法行政部门视情节给予警告、停业整顿、吊销执业证书</li>
<li><strong>以不正当手段承揽业务</strong>——这是当前"网推+法律公司"模式被处罚的核心定性</li>
<li><strong>行政法考点</strong>——行政处罚的设定、实施机关、程序、听证</li>
</ol>

<hr>
<div class="footer">
<p>📬 处罚监控系统自动生成 | {today}</p>
<p>数据来源：DuckDuckGo搜索 | 公开司法行政公告</p>
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
        print("✅ 邮件发送成功")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


def main():
    print(f"===== 法律咨询公司 & 网推所处罚监控 =====")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. 搜索
    print("[1/3] 搜索处罚案例...")
    results = search_penalty_cases()
    print(f"  获取到 {len(results)} 条结果")

    # 2. 分类
    print("\n[2/3] 分类整理...")
    categories = categorize_results(results)
    for cat, items in categories.items():
        print(f"  {cat}: {len(items)}条")

    # 3. 发送
    print("\n[3/3] 构建报告并发送邮件...")
    html = build_html_report(categories)
    today_str = datetime.now().strftime("%m/%d")
    subject = f"【处罚监控】{today_str} | 法律咨询公司 & 网推所违规案例"

    send_email(subject, html)
    print("\n✅ 任务完成！")


if __name__ == "__main__":
    main()
