"""Registration terms for PRC minor protection and IP notices."""

from __future__ import annotations

from typing import Any

LEGAL_VERSION = "2026.09.18"
AGE_GROUPS = ("adult", "teen", "child")

MINOR_TITLE = "未成年人保护及监护人同意条款"
IP_TITLE = "知识产权保护声明"

MINOR_BODY = """
为落实《中华人民共和国未成年人保护法》《中华人民共和国个人信息保护法》《未成年人网络保护条例》等规定，您在注册、登录并使用「数理助理」前，须阅读并同意本条款。

一、使用对象
1. 本应用提供高中数学试卷浏览、练习、会员服务及答卷识别等功能，主要面向已完成义务教育阶段的学习者。
2. 已满十八周岁的用户，可自行阅读本条款并注册。
3. 已满十四周岁未满十八周岁的未成年人，应在监护人知情、同意并指导下注册和使用本应用。
4. 未满十四周岁的儿童，须由监护人代为注册；监护人应代为阅读本条款、隐私说明及知识产权声明，并作出同意。未经监护人同意，我们不会为未满十四周岁的儿童创建账号。

二、监护人同意
监护人为未成年人（含儿童）注册或允许其使用本应用，即表示监护人确认：
1. 已完整阅读本条款及《知识产权保护声明》；
2. 同意我们为实现注册登录、会员开通、学习服务之目的，处理该未成年人的手机号码、设备信息、学习记录、答卷照片等必要个人信息；
3. 将教育、监督未成年人合理使用网络产品，防止沉迷、防止传播或泄露题库内容；
4. 可联系运营方查询、更正、删除相关个人信息或申请注销账号。

三、个人信息与保护
1. 我们仅在实现账号认证、会员权益、题库学习、答卷评分等目的所必需的范围内处理个人信息。
2. 不会向未成年人推送与学习无关的干扰信息，不会要求未成年人提供与服务无关的个人信息。
3. 答卷照片仅用于识别作答并评分，不作为公开展示内容。

四、拒绝或撤回
如您或监护人不同意本条款，请停止注册并退出应用。已注册用户可由监护人申请停止使用或注销账号。

本条款版本：{version}
""".strip().replace("{version}", LEGAL_VERSION)

IP_BODY = """
为保护著作权人及本应用运营方的合法权益，依据《中华人民共和国著作权法》《信息网络传播权保护条例》等规定，您在注册前须阅读并同意本声明。

一、权利归属
1. 本应用中的试卷、题干、答案、解析、详解、知识点编排、公式排版、界面设计、软件代码及其汇编成果，其知识产权归原权利人或依法获得授权的运营方所有。
2. 用户依法享有其自行拍摄的答卷照片之权利，但授权我们在评分所必需的范围内使用该等照片。

二、许可范围
我们仅授予注册用户在本应用内、为个人学习目的使用题库内容的有限的、不可转让的、非独占许可。该许可不包括复制、改编、汇编、公开传播、信息网络传播、出售、出租、反向工程或向第三方提供题库数据。

三、禁止行为
未经权利人或运营方书面许可，您不得：
1. 将试卷、答案、解析截图、复制、下载后用于传播、分享到社群、网盘或任何公开渠道；
2. 以爬虫、外挂、破解或其他技术手段批量获取、转存题库；
3. 将内容用于培训班、商业辅导、制作盗版资料或其他营利活动；
4. 删除、隐匿或篡改权利管理信息。

四、违约与责任
如违反本声明，我们有权立即中止或终止账号与会员服务，并依法追究停止侵害、赔偿损失等法律责任。对涉嫌违法犯罪的，将向有权机关报告。

五、侵权投诉
权利人如认为本应用内容侵犯其合法权益，可通过应用内公示的联系方式提出通知，我们将依法及时处理。

本声明版本：{version}
""".strip().replace("{version}", LEGAL_VERSION)


def legal_public_config() -> dict[str, Any]:
    return {
        "version": LEGAL_VERSION,
        "age_groups": [
            {"code": "adult", "label": "已满18周岁"},
            {"code": "teen", "label": "已满14周岁未满18周岁"},
            {"code": "child", "label": "未满14周岁（须监护人代为注册）"},
        ],
        "documents": [
            {"id": "minor", "title": MINOR_TITLE, "body": MINOR_BODY},
            {"id": "ip", "title": IP_TITLE, "body": IP_BODY},
        ],
        "guardian_required_for": ["teen", "child"],
    }


def validate_registration_consent(
    *,
    age_group: str,
    accept_minor_terms: bool,
    accept_ip_terms: bool,
    guardian_consent: bool,
    terms_version: str,
) -> dict[str, Any]:
    group = (age_group or "").strip().lower()
    version = (terms_version or "").strip()
    if version != LEGAL_VERSION:
        raise ValueError("条款已更新，请重新阅读并同意最新版本后再注册。")
    if group not in AGE_GROUPS:
        raise ValueError("请选择您的年龄情况。")
    if not accept_minor_terms:
        raise ValueError("须阅读并同意《未成年人保护及监护人同意条款》后才能注册。")
    if not accept_ip_terms:
        raise ValueError("须阅读并同意《知识产权保护声明》后才能注册。")
    if group != "adult" and not guardian_consent:
        raise ValueError("未满十八周岁须由监护人阅读并同意上述条款后，方可注册使用。")
    return {
        "version": LEGAL_VERSION,
        "age_group": group,
        "minor_terms": True,
        "ip_terms": True,
        "guardian": bool(guardian_consent or group == "adult"),
    }
