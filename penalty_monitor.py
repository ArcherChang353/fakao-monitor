#!/usr/bin/env python3
"""
法律咨询公司 & 网推所处罚监控 - 每天11:00执行
定位：网推所从业人员风险预警，精准搜索行业处罚/监管/负面动态
通过QQ邮箱推送到 jewelljaja@foxmail.com
"""

import os
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

# 精准搜索关键词组（聚焦网推所 & 法律咨询公司的处罚/监管/风险）
SEARCH_QUERIES = [
    # 网推所专项（最优先）
    "网推所 处罚 司法局",
    "网推律所 司法局 处罚",
    "网络推广 律师事务所 司法局 处罚",
    "律所 虚假宣传 司法局 处罚",
    "网推所 乱象 调查",
    # 法律咨询公司专项
    "法律咨询公司 司法局 处罚",
    "法律咨询公司 违规 处罚",
    "法律咨询公司 专项整治 司法局",
    "法律咨询公司 被查 司法局",
    # 律师/律所与法律咨询公司合作违规
    "律师 法律咨询公司 违规合作 司法局 处罚",
    "律所 法律咨询公司 合作 处罚",
    # 行业监管动态
    "法律咨询公司 网推 整治 司法局",
    "律师 网络推广 行政处罚 司法局",
    # 律师协会处分（网推相关）
    "律师协会 处分 网络推广",
    "律所 行业处分 违规宣传",
]

# 必须排除的关键词（非目标内容）
EXCLUDE_KEYWORDS = [
    "法考", "备考", "真题", "精讲", "课程", "讲义", "每日一题",
    "招聘", "诚聘", "招贤纳士", "加入我们", "薪资",
    "律师函", "胜诉案例", "成功案例", "客户见证",  # 律所宣传
    "直播", "公开课", "免费咨询",  # 营销内容
    "品牌营销推广", "营销推广", "推广方式",  # SEO营销文章
    "中国台湾", "台湾法律", "大城县",  # 不相关地域
    "唇膏", "犯罪嫌疑人", "女律师",  # 与网推所模式无关的个案
    "PDF", "epaper",  # PDF报纸页面
    "榨菜", "小吃", "食品",  # 不相关行业
]


def search_penalty_cases():
    """搜索法律咨询公司/网推所处罚案例"""
    all_results = []

    try:
        with DDGS() as ddgs:
            for q in SEARCH_QUERIES:
                try:
                    results = list(ddgs.text(q, max_results=5, region="cn-zh"))
                    for r in results:
                        title = r.get("title", "")
                        snippet = r.get("body", "")
                        combined = (title + " " + snippet).lower()

                        # 排除无关内容
                        if any(kw in combined for kw in EXCLUDE_KEYWORDS):
                            continue

                        all_results.append({
                            "title": title,
                            "url": r.get("href", ""),
                            "snippet": snippet[:300],
                            "query": q,
                        })
                except Exception as e:
                    print(f"  搜索 '{q[:25]}...' 失败: {e}")
    except Exception as e:
        print(f"  搜索模块初始化失败: {e}")

    # 去重
    seen = set()
    unique = []
    for item in all_results:
        key = item["title"] + item["url"]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def extract_penalty_info(result):
    """从结果中提取处罚关键信息"""
    title = result.get("title", "")
    snippet = result.get("snippet", "")
    combined = title + snippet

    info = {
        "entity": "",      # 被处罚主体
        "penalty": "",     # 处罚类型
        "reason": "",      # 处罚原因
        "authority": "",   # 处罚机关
        "date": "",        # 处罚日期
    }

    # 提取主体
    entity_patterns = [
        r'([^\s，,。]+?(?:律师事务[所务]|法律咨询[服务]?公司|法律公司|法务公司))',
    ]
    for pat in entity_patterns:
        m = re.search(pat, combined)
        if m:
            info["entity"] = m.group(1)
            break

    # 提取处罚类型
    if "吊销" in combined:
        info["penalty"] = "吊销执业证书"
    elif "停业" in combined:
        m = re.search(r'停业.*?(\d+[个]?月)', combined)
        info["penalty"] = f"停业整顿{m.group(1)}" if m else "停业整顿"
    elif "警告" in combined:
        info["penalty"] = "警告"
    elif "罚款" in combined:
        m = re.search(r'罚款.*?(\d[\d,.]*\s*万?元?)', combined)
        info["penalty"] = f"罚款{m.group(1)}" if m else "罚款"
    elif "处分" in combined:
        info["penalty"] = "行业处分"
    elif "训诫" in combined:
        info["penalty"] = "训诫"
    elif "通报批评" in combined:
        info["penalty"] = "通报批评"

    # 提取处罚机关
    authority_patterns = [
        r'([^\s，,。]*?司法局)',
        r'([^\s，,。]*?律师协会)',
    ]
    for pat in authority_patterns:
        m = re.search(pat, combined)
        if m:
            info["authority"] = m.group(1)
            break

    # 提取原因关键词
    reasons = []
    reason_keywords = [
        ("虚假宣传", "虚假宣传"),
        ("违规收案", "违规收案"),
        ("私自收费", "私自收费"),
        ("超范围经营", "超范围经营"),
        ("未登记", "未登记备案"),
        ("诈骗", "涉嫌诈骗"),
        ("利益冲突", "利益冲突"),
        ("违规广告", "违规广告/推广"),
        ("非律师", "非律师以律师名义执业"),
        ("不正当竞争", "不正当竞争"),
        ("网络推广", "网络推广违规"),
        ("无证", "无证经营"),
    ]
    for kw, label in reason_keywords:
        if kw in combined:
            reasons.append(label)

    info["reason"] = "、".join(reasons) if reasons else ""

    return info


def assess_risk(info, title, snippet):
    """评估对你所在网推所的风险等级"""
    combined = (title + snippet).lower()

    # 高危：直接与网推所/网络推广相关
    if any(kw in combined for kw in ["网推所", "网络推广", "虚假宣传", "违规广告"]):
        return "🔴 高危"

    # 中危：与法律咨询公司合作、超范围经营等
    if any(kw in combined for kw in ["法律咨询公司", "超范围", "违规合作", "法律公司"]):
        return "🟡 中危"

    # 低危：一般律所处罚但模式相关
    if any(kw in combined for kw in ["律师事务", "律所", "司法局", "行政处罚"]):
        return "🟢 关注"

    return "⚪ 一般"


def is_relevant_to_wangtuisuo(title, snippet):
    """二次验证：判断是否与网推所/法律咨询公司风险相关"""
    combined = (title + snippet).lower()

    # 必须先命中一个核心主题词
    core_topics = [
        "网推所", "网推律所", "网络推广", "虚假宣传", "违规广告",
        "法律咨询公司", "法律咨询有限", "法律公司", "法务公司",
        "律师事务所 处罚", "司法局 处罚", "律所 处罚",
        "专项整治", "整治行动", "整治乱象",
        "违规合作", "违规经营", "超范围经营",
        "行业处分", "行政处罚 律",
        "冒充律师", "非律师", "无证经营",
    ]
    if not any(kw in combined for kw in core_topics):
        return False

    # 排除明显不相关的内容
    exclude_topics = [
        "唇膏", "犯罪嫌疑人给", "给犯罪嫌疑人",  # 个别律师个案，与网推所模式无关
        "PDF", "epaper", "数字报",  # PDF报纸页面（重复/无内容）
        "品牌营销推广", "怎么做品牌", "推广方式", "网络推广方式",  # 营销教学文章
        "大城县", "中国台湾", "台湾法律",  # 不相关地域
        "榨菜", "小吃", "食品", "保温材料",  # 不相关行业
        "女律师将", "律师给",  # 个别花边新闻
        "ZARA", "服装", "时装", "耐克", "Nike",  # 其他行业的虚假宣传
        "尿素", "肥料", "农药", "化肥", "饲料",  # 农资行业
        "扶贫", "脱贫攻坚", "扫黑除恶",  # 政府其他工作
        "t66y.com", "草榴", "1024",  # 垃圾网站
        "mini.eastday", "东方头条",  # 低质聚合站
    ]
    if any(kw in combined for kw in exclude_topics):
        return False

    # 必须包含法律行业词（防止其他行业的处罚混入）
    legal_indicators = [
        "律师", "律所", "法律", "司法", "法务",
        "法律服务", "执业", "辩护", "诉讼",
        "司法局", "律师协会", "律协",
        "网推", "接案", "揽案",
    ]
    if not any(kw in combined for kw in legal_indicators):
        return False

    return True


def categorize_results(results):
    """按风险类型分组"""
    categories = {
        "🔴 高危·网推所/虚假宣传处罚": [],
        "🟡 中危·法律咨询公司违规": [],
        "🟢 关注·律所处罚（模式相关）": [],
        "📋 行业监管·新规/整治": [],
    }

    for r in results:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        combined = (title + snippet).lower()

        # 先二次验证相关性
        if not is_relevant_to_wangtuisuo(title, snippet):
            continue

        # 行业监管类（优先级最高，因为整治/新规对所有从业者都重要）
        if any(kw in combined for kw in ["专项整治", "整治行动", "整治乱象", "新规", "专项检查", "整治网推", "整治法律咨询"]):
            categories["📋 行业监管·新规/整治"].append(r)
        # 网推/虚假宣传（直接关联网推所业务模式）
        elif any(kw in combined for kw in ["网推所", "网推律所", "网络推广", "虚假宣传", "违规广告", "竞价排名"]):
            categories["🔴 高危·网推所/虚假宣传处罚"].append(r)
        # 法律咨询公司违规
        elif any(kw in combined for kw in ["法律咨询公司", "法律公司", "法务公司", "法律咨询有限"]):
            categories["🟡 中危·法律咨询公司违规"].append(r)
        # 律所处罚（可能涉及网推所同类问题）
        elif any(kw in combined for kw in ["律师事务所", "律所", "司法局 行政处罚", "行业处分"]):
            # 进一步判断是否与网推模式相关
            if any(kw in combined for kw in ["违规合作", "虚假", "推广", "广告", "宣传", "网络"]):
                categories["🔴 高危·网推所/虚假宣传处罚"].append(r)
            else:
                categories["🟢 关注·律所处罚（模式相关）"].append(r)
        else:
            pass  # 不放入任何分类 = 过滤掉

    return {k: v for k, v in categories.items() if v}


def build_html_report(categories):
    """构建HTML邮件报告（从业人员视角）"""
    today = datetime.now().strftime("%Y年%m月%d日")

    html = f"""<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; color: #333; line-height: 1.8; max-width: 700px; }}
h2 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 6px; }}
h3 {{ margin-top: 24px; }}
.card-high {{ background: #fff0f0; border-left: 4px solid #e74c3c; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
.card-mid {{ background: #fffdf0; border-left: 4px solid #f39c12; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
.card-low {{ background: #f0f8ff; border-left: 4px solid #3498db; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
.card-rule {{ background: #f5fff5; border-left: 4px solid #27ae60; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.snippet {{ color: #666; font-size: 13px; margin-top: 4px; }}
.tag {{ display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 3px; margin-right: 4px; }}
.tag-risk {{ background: #ffe0e0; color: #c0392b; }}
.tag-info {{ background: #e0f0ff; color: #2980b9; }}
.tag-reason {{ background: #fff3cd; color: #856404; }}
hr {{ border: none; border-top: 1px dashed #ccc; margin: 20px 0; }}
.footer {{ color: #999; font-size: 12px; margin-top: 20px; }}
.warn {{ background: #ffeaa7; padding: 10px 14px; border-radius: 4px; margin: 12px 0; font-size: 14px; }}
</style></head><body>
<h2>⚖️ 法律咨询公司 & 网推所处罚监控 | {today}</h2>

<div class="warn">
<strong>👤 网推所从业人员风险预警</strong>：以下信息聚焦网推所及法律咨询公司被处罚、被整治的案例与监管动态。请对照自身业务模式排查风险，及时调整合规策略。
</div>
"""

    card_map = {
        "🔴 高危·网推所/虚假宣传处罚": "card-high",
        "🟡 中危·法律咨询公司违规": "card-mid",
        "🟢 关注·律所处罚（模式相关）": "card-low",
        "📋 行业监管·新规/整治": "card-rule",
    }

    for cat_name, items in categories.items():
        html += f"<h3>{cat_name}</h3>\n"
        for item in items:
            css_class = card_map.get(cat_name, "card-low")
            info = extract_penalty_info(item)
            risk = assess_risk(info, item.get("title", ""), item.get("snippet", ""))
            snippet = item.get("snippet", "")[:200]

            # 构建标签
            tags_html = ""
            if info["entity"]:
                tags_html += f'<span class="tag tag-info">🏢 {info["entity"]}</span>'
            if info["penalty"]:
                tags_html += f'<span class="tag tag-risk">⚡ {info["penalty"]}</span>'
            if info["reason"]:
                tags_html += f'<span class="tag tag-reason">📌 {info["reason"]}</span>'

            html += f"""<div class="{css_class}">
{tags_html}<br>
<a href="{item['url']}"><strong>{item['title']}</strong></a>
<div class="snippet">{snippet}...</div>
</div>\n"""

    html += f"""
<hr>
<h3>📌 网推所合规自查清单</h3>
<ol>
<li>推广文案是否使用"包赢""100%胜诉""有关系""内部渠道"等绝对化/虚假用语？</li>
<li>法律咨询公司是否以律师名义接案、出具法律意见（超范围经营）？</li>
<li>律师与法律咨询公司之间是否存在违规分成/案源费/挂靠关系？</li>
<li>收费标准是否公示？是否存在私下收费、不开票、飞单情况？</li>
<li>网络竞价排名推广是否标注"广告"？落地页是否误导公众以为是律师直接服务？</li>
<li>案源转委托是否合规？是否存在"接案后低价转包"模式？</li>
<li>是否有冒充律师、非律师以律师名义承揽业务的行为？</li>
</ol>

<hr>
<div class="footer">
<p>📬 监控系统自动生成 | {today}</p>
<p>数据来源：公开搜索（DuckDuckGo） | 司法行政机关公告</p>
<p>⚠️ 本报告仅供内部风险预警参考，不构成法律意见</p>
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
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"定位：网推所从业人员风险预警\n")

    # 1. 搜索
    print("[1/3] 精准搜索处罚案例...")
    results = search_penalty_cases()
    print(f"  获取到 {len(results)} 条结果（已过滤无关内容）")

    if not results:
        print("  ⚠️ 今日未获取到相关处罚信息")
        # 仍然发送邮件，告知无异常
        today_str = datetime.now().strftime("%m/%d")
        html = f"""<html><head><meta charset="utf-8"></head><body>
<h2>⚖️ 处罚监控 | {today_str}</h2>
<p>今日未获取到网推所及法律咨询公司相关处罚信息。</p>
<p>暂无新增风险信号，建议仍保持关注。</p>
</body></html>"""
        send_email(f"【处罚监控】{today_str} | 今日暂无新增处罚", html)
        return

    # 2. 分类
    print("\n[2/3] 风险分类...")
    categories = categorize_results(results)
    for cat, items in categories.items():
        print(f"  {cat}: {len(items)}条")

    # 3. 发送
    print("\n[3/3] 构建报告并发送邮件...")
    html = build_html_report(categories)
    today_str = datetime.now().strftime("%m/%d")
    subject = f"【处罚监控】{today_str} | 网推所 & 法律咨询公司风险预警"

    send_email(subject, html)
    print("\n✅ 任务完成！")


if __name__ == "__main__":
    main()
