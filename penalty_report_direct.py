#!/usr/bin/env python3
"""
法律咨询公司 & 网推所处罚日报 - 直接发送版
WorkBuddy自动化生成的定制化日报，通过SMTP直接发送
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ============ 配置 ============
QQ_EMAIL = "jewelljaja@foxmail.com"
QQ_SMTP_CODE = os.environ["QQ_SMTP_CODE"]
SMTP_SERVER = "smtp.qq.com"
SMTP_PORT = 465


def build_report_html():
    """构建2026-08-08日报HTML"""
    today = "2026年08月08日"

    html = f"""<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, 'Microsoft YaHei', sans-serif; color: #333; line-height: 1.8; max-width: 760px; margin: 0 auto; padding: 12px; }}
h2 {{ color: #c0392b; border-bottom: 2px solid #c0392b; padding-bottom: 6px; }}
h3 {{ color: #2c3e50; margin-top: 24px; }}
.case {{ background: #fff5f5; border-left: 4px solid #e74c3c; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
.policy {{ background: #f5f8ff; border-left: 4px solid #3498db; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
.trend {{ background: #fffdf0; border-left: 4px solid #f39c12; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
.tracking {{ background: #f0fff5; border-left: 4px solid #27ae60; padding: 10px 14px; margin: 8px 0; border-radius: 4px; }}
a {{ color: #2980b9; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.label {{ display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 3px; margin-right: 4px; background: #ffe0e0; color: #c0392b; }}
hr {{ border: none; border-top: 1px dashed #ccc; margin: 20px 0; }}
.footer {{ color: #999; font-size: 12px; margin-top: 20px; }}
ol, ul {{ margin: 6px 0; }}
</style></head><body>
<h2>⚖️ 法律咨询公司 &amp; 网推所处罚日报 · {today}</h2>

<h3>🔴 被处罚案例（24小时内核心）</h3>

<div class="case">
<strong>1. 山东臻美律师事务所</strong>（山东省德州市临邑县）<br>
<span class="label">利益冲突</span><span class="label">没收违法所得</span><br>
<b>处罚事由</b>：指派不同律师在同一民间借贷纠纷中分别代理原告和被告，违反利益冲突审查规定；尽管事后双方出具《利益冲突豁免函》仍被认定违法。<br>
<b>处罚结果</b>：没收违法所得7000元（2026年德州市司法局首个处罚案件）<br>
<b>决定日期</b>：2026年8月3日；<b>报道日期</b>：2026年8月7日<br>
<a href="https://new.qq.com/rain/a/20260807A0H0WD00">来源链接</a>
</div>

<div class="case">
<strong>2. 广东福阁律师事务所</strong>（深圳市南山区）<br>
<span class="label">无固定住所</span><span class="label">限期整改</span><br>
<b>处罚事由</b>：未在注册地址办公、且无固定住所，违反《律师法》相关规定<br>
<b>处罚结果</b>：责令限期整改（90日），书面报告整改情况<br>
<b>决定日期</b>：2026年8月7日（南山区司法局发出限期整改通知书）<br>
<a href="https://news.10jqka.com.cn/20260807/c678758038.shtml">来源链接</a>
</div>

<div class="case">
<strong>3. "法律咨询公司"敲诈团伙——崔某案</strong>（上海普陀）<br>
<span class="label">刑事打击</span><span class="label">5年刑期</span><br>
<b>处罚事由</b>：注册成立"法律咨询公司"，通过非法渠道购买公民信息，对证券投顾客户进行电话初筛，教唆客户以"虚假宣传""炒股亏损"等名义向持牌机构施压敲诈退款<br>
<b>处罚结果</b>：上海市普陀区法院一审判决：犯敲诈勒索罪、侵犯公民个人信息罪，数罪并罚，有期徒刑5年，罚金7万元；上海市第二中级人民法院终审裁定：驳回上诉、维持原判<br>
<b>报道日期</b>：2026年8月7日<br>
<a href="https://news.yunnan.cn/system/2026/08/07/034114697.shtml">来源链接</a>
</div>

<div class="case">
<strong>4. "法律咨询+证券投顾"双牌敲诈团伙——章某、龚某等21人</strong>（上海嘉定）<br>
<span class="label">团伙犯罪</span><span class="label">刑事强制措施</span><br>
<b>处罚事由</b>：对外包装成"法律咨询、证券投资顾问机构"，通过黑灰产获取公民信息，招募员工话术培训，组织上千客户高频拨打投诉热线、寄递举报信，逼迫企业妥协退费，从中抽取30%"维权服务费"<br>
<b>处罚结果</b>：21名犯罪嫌疑人被采取刑事强制措施，初步查证非法获利逾300万元；受害企业损失超2000万元<br>
<b>报道日期</b>：2026年8月7日<br>
<a href="https://dy.163.com/article/L3OFUDVA0514A42S.html">来源链接</a>
</div>

<div class="case">
<strong>5. 四川法邦（内江）律师事务所</strong>（四川内江市）<br>
<span class="label">不正当竞争</span><span class="label">停业整顿</span><br>
<b>处罚事由</b>：以不正当手段承揽业务、违反规定收取费用<br>
<b>处罚依据</b>：《律师法》第五十条第一款第(一)项、第(四)项、《律师和律师事务所违法行为处罚办法》第三十三条、第三十九条第(三)项、第(四)项<br>
<b>处罚结果</b>：停业整顿六个月<br>
<b>决定日期</b>：2026年7月17日；<b>公示日期</b>：2026年7月21日<br>
<a href="https://credit.neijiang.gov.cn/credit-webservice-portal/doublePublicView/penaltyDetail?id=20260721162813429917">来源链接</a>
</div>

<div class="case">
<strong>6. 右江区秉正法律服务所</strong>（广西百色市）<br>
<span class="label">收费不规范</span><span class="label">警告+整改</span><br>
<b>处罚事由</b>：未公开收费项目和收费标准、未向委托人出具有效收费凭证<br>
<b>处罚依据</b>：《基层法律服务所管理办法》第二十四条第四项、第三十六条第二项<br>
<b>处罚结果</b>：警告，限期8月7日前整改到位<br>
<b>决定日期</b>：2026年7月6日<br>
<a href="http://www.bsyj.gov.cn/xxgk/zfxxgk/fdzdgknr/jbxxgk/xzzf/t27873614.shtml">来源链接</a>
</div>

<h3>📋 政策/监管动态</h3>

<div class="policy">
<b>1. 上海警方亮剑金融黑灰产</b>：8月7日集中披露"代理维权"敲诈案——证券投顾行业首例以"敲诈勒索罪"定罪案（崔某案）和上海嘉定警方捣毁21人团伙案，标志上海正以刑事打击手段整治披"法律咨询"外衣的恶意维权产业链。
</div>

<div class="policy">
<b>2. 迁安市市监局发布风险提示</b>（8月6日）：提醒市民警惕部分法律咨询服务公司以"与法院公安有关系、承诺能成功立案追回欠款"等话术收取费用后不兑现乃至跑路，明确警示法律咨询公司常见诈骗套路。
</div>

<div class="policy">
<b>3. 惠东县法律服务市场乱象专项整治</b>（6月1日-8月31日，整治期仅剩不到一个月）：由县委政法委牵头，联合法院、检察院、公安、司法、市场监管、城管执法等部门成立专班，重点打击9类乱象。
</div>

<div class="policy">
<b>4. 云南楚雄州规范法律咨询服务机构专项整治</b>（即日起至2026年12月）：在2025年整顿成效基础上，重点整治7类行为。
</div>

<div class="policy">
<b>5. 最高法发布生态环境法典首部配套司法解释</b>（8月6日发布，8月15日施行）：明确新旧法律衔接适用的一般标准和具体规则。
</div>

<h3>💡 趋势分析</h3>

<div class="trend">
<strong>1. "代理维权"黑产进入刑事打击深水区</strong>：上海普陀崔某案（5年有期徒刑）+ 嘉定章某龚某21人团伙（300万非法获利+2000万企业损失）两起标志性案件同日（8月7日）披露，标志"披法律咨询外衣的恶意投诉敲诈"已被监管定性为有组织金融黑灰产，刑事打击力度升级。
</div>

<div class="trend">
<strong>2. 律所"无固定住所"成新雷区</strong>：广东福阁律所被南山区司法局发限期整改（8月7日），反映司法部2025年度律所检查考核已从"硬性资质"向"实际合规经营"延伸，注册地址与实际办公不一致问题正成为新一轮整治重点。
</div>

<div class="trend">
<strong>3. 利益冲突审查不可豁免化</strong>：山东臻美律所案再次确认"利益冲突豁免函"不能免除律所主动审查义务——提示律所"私下调停"模式的法律风险。
</div>

<div class="trend">
<strong>4. 基层法律服务所纳入严管视野</strong>：百色右江区秉正所被警告+限期整改（8月7日为整改截止日），显示基层法律服务所收费不规范问题正被各级司法局纳入整治清单。
</div>

<div class="trend">
<strong>5. 专项整治时间窗口收尾</strong>：惠东县专项整治（8月31日截止）、楚雄州专项整治（2026年12月截止）进入中后段，预计9-10月将密集出现处罚决定书与典型案例通报。
</div>

<h3>📌 持续跟踪重点案例</h3>

<div class="tracking">
<ul>
<li>安徽徽瀚律师事务所（芜司罚决〔2026〕2号，警告+没收4万+罚款3万）</li>
<li>黄建国律师（芜司罚决〔2026〕3号，停止执业1年+罚款4.5万）</li>
<li>湖北栖贤律师事务所（停业6个月+罚款5万）</li>
<li>湖北至南律师事务所（吊销执照，2588件投诉）</li>
<li>骆臣飞律师（吊销执业证）</li>
<li>唐付贵律师（吊销执业证）</li>
<li>陈××律师（吊销执业证）</li>
<li>盈科律所梅向荣（强制执行累计2632万元，已被上海警方刑事立案并采取强制措施）</li>
</ul>
</div>

<hr>
<div class="footer">
<p>📬 本日报由 WorkBuddy 自动化监控生成 | 搜索窗口：2026-08-07 ~ 2026-08-08</p>
<p>数据来源：百度资讯、知乎、各地司法局/律协官网（深圳南山区、广西百色、四川内江、山东德州、上海普陀/嘉定、河北承德等）</p>
<p>⚠️ 本报告仅供内部风险预警参考，不构成法律意见</p>
</div>
</body></html>"""

    return html


def send_email(subject, html_body):
    """通过QQ邮箱SMTP发送邮件"""
    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = QQ_EMAIL
    msg["To"] = QQ_EMAIL
    msg["Subject"] = subject

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
    today = datetime.now().strftime("%Y年%m月%d日")
    print(f"===== 处罚日报直发版 {today} =====")

    html = build_report_html()
    subject = f"【处罚监控】{today}"

    success = send_email(subject, html)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
