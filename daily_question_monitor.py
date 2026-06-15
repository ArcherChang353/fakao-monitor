#!/usr/bin/env python3
"""
法考每日一题更新监控 - 每天8:30执行
搜索8位法考名师最新每日一题，比对state.json追踪更新
发现新题时发送含链接的通知邮件（不抓取题目全文）
"""

import os
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from ddgs import DDGS

# ============ 配置 ============
QQ_EMAIL = "jewelljaja@foxmail.com"
QQ_SMTP_CODE = os.environ["QQ_SMTP_CODE"]
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465

STATE_FILE = "state_daily_questions.json"

# 8位老师搜索配置
TEACHERS = {
    "李佳（行政法）": {
        "queries": [
            "行政法李佳 每日一题 2026",
            "site:weibo.com 行政法李佳 每日一题",
        ],
        "active": True,
        "platform": "微博/知乎/B站",
    },
    "柏浪涛（刑法）": {
        "queries": [
            "柏浪涛 刑法 每日一题 2026",
            "site:tieba.baidu.com 柏浪涛 每日一题",
        ],
        "active": True,
        "platform": "微博/贴吧/知乎",
    },
    "孟献贵（民法）": {
        "queries": [
            "孟献贵 民法 每日一题 2026",
            "site:weibo.com 孟献贵 每日一题",
        ],
        "active": True,
        "platform": "微博/搜狐",
    },
    "戴鹏（民诉）": {
        "queries": [
            "戴鹏 民诉 每日一题 2026",
        ],
        "active": False,  # 无独立每日一题系列
        "platform": "B站课程合集",
    },
    "左宁（刑诉）": {
        "queries": [
            "左宁 刑诉 每日一题 2026",
            "site:sohu.com 左宁 每日一题",
        ],
        "active": True,
        "platform": "微博/搜狐/知乎",
    },
    "杨帆（三国法）": {
        "queries": [
            "杨帆 三国法 每日一题 2026",
        ],
        "active": False,  # 2026版尚未开始
        "platform": "微博(暂未更新2026)",
    },
    "马峰（理论法）": {
        "queries": [
            "马峰 理论法 每日一题 2026",
        ],
        "active": False,  # 2026版尚未开始
        "platform": "微博(暂未更新2026)",
    },
    "郄鹏恩（商经知）": {
        "queries": [
            "郄鹏恩 商经知 每日一题 2026",
            "site:weibo.com 郄鹏恩 每日一题",
        ],
        "active": True,
        "platform": "微博/知乎",
    },
}


def load_state():
    """加载上次追踪状态"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    """保存追踪状态"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def extract_latest_question(snippets):
    """
    从搜索结果摘要中提取最新题号和信息
    返回: (question_number, url, title, date_text) 或 None
    """
    patterns = [
        r'(?:第|题)(\d{1,3})\s*(?:题|道|天)',
        r'每日一题\s*[\(（]?\s*(\d{1,3})\s*[\)）]?\s*[\(（\-]',
        r'(\d{1,3})\s*[\)）道题]',
        r'每日一题\s*(\d{1,3})',
        r'已更新至?\s*(\d{1,3})\s*[道题]',
        r'(\d{1,3})\s*[道题].*每日一题',
    ]

    best_q = 0
    best_url = ""
    best_title = ""
    best_date = ""

    for item in snippets:
        title = item.get("title", "")
        body = item.get("body", "")
        url = item.get("href", "")
        combined = title + " " + body

        for pat in patterns:
            matches = re.findall(pat, combined, re.IGNORECASE)
            for m in matches:
                try:
                    q_num = int(m)
                    if q_num > best_q:
                        best_q = q_num
                        best_url = url
                        best_title = title
                except ValueError:
                    pass

        # 尝试提取日期
        date_patterns = [
            r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
            r'(\d{1,2}月\d{1,2}日)',
            r'(\d{1,2}[-/]\d{1,2})',
            r'(\d+)\s*(?:天|小时)前',
        ]
        for dp in date_patterns:
            dm = re.search(dp, combined)
            if dm:
                best_date = dm.group(1)
                break

    if best_q > 0:
        return (best_q, best_url, best_title[:100], best_date)
    return None


def search_teacher(name, config):
    """搜索某位老师的最新每日一题"""
    results = []
    try:
        with DDGS() as ddgs:
            for q in config["queries"]:
                r = list(ddgs.text(q, max_results=5, timelimit="m"))
                results.extend(r)
    except Exception as e:
        print(f"    DDG搜索失败: {e}")
        return None

    if not results:
        return None

    return extract_latest_question(results)


def check_all_teachers():
    """检查所有老师的更新状态"""
    state = load_state()
    updates = []
    unchanged = []
    inactive = []

    print("开始检查8位名师每日一题更新...\n")

    for name, config in TEACHERS.items():
        if not config["active"]:
            inactive.append(name)
            continue

        print(f"  🔍 {name}...")
        result = search_teacher(name, config)

        prev = state.get(name, {})
        prev_q = prev.get("last_q", 0)

        if result:
            q_num, url, title, date_str = result
            print(f"     最新: 第{q_num}题 | 上次: 第{prev_q}题")

            if q_num > prev_q:
                updates.append({
                    "name": name,
                    "platform": config["platform"],
                    "last_q": q_num,
                    "prev_q": prev_q,
                    "url": url,
                    "title": title,
                    "date": date_str,
                    "new_count": q_num - prev_q,
                })
                state[name] = {"last_q": q_num, "last_url": url, "last_date": date_str}
            else:
                unchanged.append({
                    "name": name,
                    "last_q": q_num,
                    "platform": config["platform"],
                })
                # 更新date但保持q
                if date_str:
                    state[name] = {"last_q": q_num, "last_url": url, "last_date": date_str}
        else:
            print(f"     未能获取数据")
            unchanged.append({
                "name": name,
                "last_q": prev_q,
                "platform": config["platform"],
            })

    save_state(state)
    return updates, unchanged, inactive


def build_report(updates, unchanged, inactive):
    """构建HTML邮件报告"""
    today = datetime.now().strftime("%Y年%m月%d日")
    weekday = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][datetime.now().weekday()]
    has_new = len(updates) > 0

    html = f"""<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; color: #333; line-height: 1.8; }}
h2 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 6px; }}
h3 {{ color: #2c3e50; }}
.alert {{ background: #ffeaa7; border-left: 4px solid #fdcb6e; padding: 12px 16px; margin: 12px 0; border-radius: 4px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th {{ background: #2c3e50; color: #fff; padding: 8px 12px; text-align: left; }}
td {{ padding: 8px 12px; border-bottom: 1px solid #ddd; }}
tr:hover {{ background: #f9f9f9; }}
.tag-new {{ display: inline-block; background: #e74c3c; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
.tag-ok {{ display: inline-block; background: #27ae60; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
.tag-inactive {{ display: inline-block; background: #95a5a6; color: #fff; padding: 2px 8px; border-radius: 3px; font-size: 12px; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.badge {{ display: inline-block; background: #e74c3c; color: #fff; border-radius: 50%; min-width: 22px; height: 22px; text-align: center; line-height: 22px; font-size: 12px; font-weight: bold; }}
hr {{ border: none; border-top: 1px dashed #ccc; margin: 20px 0; }}
.footer {{ color: #999; font-size: 12px; margin-top: 20px; }}
.note {{ background: #eaf2f8; padding: 12px; border-radius: 4px; margin: 10px 0; font-size: 14px; }}
</style></head><body>
<h2>📝 法考每日一题更新监控 | {today} {weekday}</h2>
"""

    # 新题提醒区
    if has_new:
        html += f'<div class="alert">🔔 <strong>发现新题！</strong>以下老师有新的每日一题更新，点击链接即可查看：</div>\n'
        html += '<table>\n<tr><th>老师</th><th>最新题号</th><th>新增数量</th><th>平台</th><th>查看链接</th></tr>\n'
        for u in updates:
            badge = f'<span class="badge">+{u["new_count"]}</span>'
            link = f'<a href="{u["url"]}">🔗 点击查看</a>' if u["url"] else "—"
            html += f'<tr><td><strong>✨ {u["name"]}</strong></td><td>第{u["last_q"]}题 <span class="tag-new">NEW</span></td><td>{badge}</td><td>{u["platform"]}</td><td>{link}</td></tr>\n'
        html += '</table>\n'
    else:
        html += '<div class="alert">✅ 今日暂无新题更新，所有老师进度与上次检查一致。</div>\n'

    # 全量进度表
    html += '<h3>📊 全部老师进度总览</h3>\n'
    html += '<table>\n<tr><th>老师</th><th>科目</th><th>最新题号</th><th>状态</th></tr>\n'

    # 更新了的
    for u in updates:
        name = u["name"].replace("（", " ").replace("）", "")
        parts = name.split(" ")
        html += f'<tr><td><strong>{parts[0]}</strong></td><td>{parts[1] if len(parts)>1 else ""}</td><td>第{u["last_q"]}题 <span class="badge">+{u["new_count"]}</span></td><td><span class="tag-new">📈 有更新</span></td></tr>\n'

    # 未变化的
    for u in unchanged:
        name = u["name"].replace("（", " ").replace("）", "")
        parts = name.split(" ")
        q = u["last_q"] or "?"
        status = f'<span class="tag-ok">未变化</span>' if u["last_q"] else '<span style="color:#999">待首次检测</span>'
        html += f'<tr><td>{parts[0]}</td><td>{parts[1] if len(parts)>1 else ""}</td><td>第{q}题</td><td>{status}</td></tr>\n'

    # 未开始
    for name in inactive:
        name_clean = name.replace("（", " ").replace("）", "")
        parts = name_clean.split(" ")
        html += f'<tr><td>{parts[0]}</td><td>{parts[1] if len(parts)>1 else ""}</td><td>尚未开始</td><td><span class="tag-inactive">2026版未发布</span></td></tr>\n'

    html += '</table>\n'

    # 提示
    html += '<div class="note">💡 <strong>说明：</strong>本监控通过搜索引擎追踪题号变化，不抓取题目全文。题目内容请点击链接到原平台查看。<br>'
    html += '5位教师已启动2026每日一题（李佳、柏浪涛、孟献贵、左宁、郄鹏恩），3位尚未发布（戴鹏、杨帆、马峰）。<br>'
    html += '微博API审核通过后，将升级为完整题目抓取。」</div>\n'

    html += '<hr>\n<div class="footer">'
    html += f'<p>📬 法考每日一题监控系统自动生成 | {today}</p>'
    html += '<p>Powered by GitHub Actions ☁️ | 云端执行 · 不依赖个人电脑</p>'
    html += '</div>\n</body></html>'

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
    print(f"===== 法考每日一题更新监控 =====")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    updates, unchanged, inactive = check_all_teachers()

    print(f"\n📊 结果汇总:")
    print(f"  有更新: {len(updates)} 位老师")
    print(f"  无变化: {len(unchanged)} 位老师")
    print(f"  未发布: {len(inactive)} 位老师")

    if updates:
        print("\n🆕 新题详情:")
        for u in updates:
            print(f"  ✅ {u['name']}: +{u['new_count']}题 → 第{u['last_q']}题 | {u.get('url','')}")

    # 构建报告
    html = build_report(updates, unchanged, inactive)
    today_str = datetime.now().strftime("%m/%d")
    tag = "🆕有更新" if updates else "无变化"
    subject = f"【法考每日一题】{today_str} | {tag} | 8位名师进度追踪"

    send_email(subject, html)
    print("\n✅ 任务完成!")


if __name__ == "__main__":
    main()
