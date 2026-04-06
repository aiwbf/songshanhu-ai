from __future__ import annotations

from .models import CaseProfile, ClassificationResult


def build_materials_template(result: ClassificationResult, profile: CaseProfile) -> list[str]:
    codes = set(result.case_codes or result.candidate_case_codes)
    materials: list[str] = []
    if not codes:
        return ["先确认学段、户籍、工作地、房产所在地和优待身份，再生成定制材料清单。"]

    if "台湾学生" in codes:
        materials.extend(
            [
                "监护人签署的《东莞市台湾学生入学申请书》和《台湾学生就读义务教育阶段学校申请表》",
                "学生与监护人的户籍誊本、台湾身份证、台湾居民来往大陆通行证或台湾居民居住证",
                "监护人在莞就业或投资证明，如营业执照、劳动合同、工资单、社保与纳税清单",
                "转学或非起始年级补充在读证明",
                "如委托监护，补充公证委托书、委托监管协议和受托监护人身份证明",
            ]
        )
        return materials

    if "华侨华人" in codes:
        materials.extend(
            [
                "市侨务部门要求的申请登记材料",
                "祖籍东莞、在莞投资或在莞就业的证明材料",
                "监护人与学童身份证明及关系证明",
                "如为转学或非起始年级，补充在读证明",
            ]
        )
        return materials

    base = ["父母及学童户口簿、身份证、出生证"]
    if profile.is_transfer_or_non_starting:
        base.append("学童在读证明")
    materials.extend(base)

    if "A1" in codes:
        materials.append("房产证明或已备案购房合同")
        materials.append("不动产查房证明")
    if {"A2", "A3"} & codes:
        materials.extend(
            [
                "房产或居住证明；如东莞无房，补充无房证明",
                "学历/学位验证材料或职称证书及查验截图",
                "近两年社保缴费明细或在编在职工作证明",
                "2021-2023 年个人所得税纳税记录",
            ]
        )
    if {"B1", "B2", "B3"} & codes:
        materials.extend(
            [
                "学历/学位验证材料或职称证书及查验截图",
                "近两年社保缴费明细或在编在职工作证明",
                "2021-2023 年个人所得税纳税记录",
                "人才证明、工作证明或企业指标证明",
            ]
        )
    if "优才卡" in codes:
        materials.append("优才卡持卡证明，以及工作地或自有房产所在地证明")
    if "优粤卡" in codes:
        materials.append("优粤卡持卡证明，以及工作地或居住地证明")
    if "荣誉市民" in codes:
        materials.append("荣誉市民证明，以及工作单位或自有房产所在地证明")
    if "C" in codes:
        materials.append("东莞市积分入学要求的积分方证件及居住/工作/房产证明")

    deduped: list[str] = []
    seen = set()
    for item in materials:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def build_steps_template(result: ClassificationResult, profile: CaseProfile) -> list[str]:
    codes = set(result.case_codes or result.candidate_case_codes)
    if result.primary_case_code == "单位账号注册与审核":
        return [
            "单位先在线下提交账号申请表、统一社会信用代码证复印件和招生管理员身份证复印件",
            "教育部门审核通过后，向招生管理员短信下发账号密码",
            "管理员登录松山湖入学管理平台补充单位信息并上传盖章资料",
            "报名期内审核员工申请并提交教育部门复核",
            "审核完成后打印《2024 年松山湖中小学、幼儿园入学信息表》，签名盖章后交窗口",
        ]
    if result.primary_case_code == "报名资料修改":
        return [
            "登录松山湖入学管理平台",
            "进入报名信息页，点击右上角“修改资料”",
            "仅单位未审核或审核不通过的申请可修改",
            "按审核意见修正后重新提交，等待复核结果",
        ]
    if result.primary_case_code == "房产解锁":
        return [
            "进入松山湖入学管理平台的“家庭户学位申请房锁定查询”",
            "先查询锁定情况，再点击“申请解锁”",
            "按页面要求填写信息并上传所需资料",
            "提交后等待审核；如属同一家庭多子女同校场景，可致电 0769-38881212 转 1 备案",
        ]
    if result.primary_case_code == "房产锁定":
        return [
            "先在平台查询学位申请房锁定状态",
            "确认锁定原因是历史使用、同址多家庭还是同年多家庭申报",
            "如需继续申报，按平台提示或官方热线要求补交解锁材料",
        ]

    if "C" in codes and not ({"A1", "A2", "A3", "B1", "B2", "B3"} & codes):
        return [
            "在东莞市义务教育阶段学校统一招生平台完成报名",
            "按积分入学要求提交积分方资料并等待初审/复审",
            "在规定时间内填报志愿并查看录取结果",
        ]

    steps = []
    if profile.is_transfer_or_non_starting:
        steps.append("非起始年级或转学学童主要走松山湖入学管理平台")
    else:
        steps.append("小学一年级和初中一年级的 A/B 类先报东莞市统一招生平台，再报松山湖入学管理平台")
    if {"A2", "B1", "B2", "B3"} & codes:
        steps.append("A2/B 类所在单位需先完成单位账号注册或年度信息更新")
        steps.append("单位管理员审核通过后，个人申请才算完成提交")
    steps.append("在报名期内同步填报志愿并上传材料，注意两平台截止时间不同")
    steps.append("关注初审、复审、志愿确认和录取公布节点")
    return steps


def build_risk_template(result: ClassificationResult, evidence_warnings: list[str], profile: CaseProfile) -> list[str]:
    risks = list(evidence_warnings)
    codes = set(result.case_codes or result.candidate_case_codes)
    if result.status == "need_follow_up":
        risks.append("当前资料不足以稳定落类，先补最少必要信息再下最终结论。")
    if {"A1", "A2", "A3"} & codes:
        risks.append("A 类涉及房产、户籍类型和学位申请房锁定，字段错误会直接改变类别。")
    if {"B1", "B2", "B3"} & codes:
        risks.append("B 类结果依赖单位审核、社保个税归属和人才/指标证明，业务 FAQ 不能替代正式审核。")
    if "C" in codes:
        risks.append("C 类属于积分入学，最终安排受积分排序和志愿填报影响。")
    if profile.is_transfer_or_non_starting:
        risks.append("转学和非起始年级受空余学位及既往安排限制，不能按起始年级规则直接类推。")
    if "房产解锁" in codes or "房产锁定" in codes or profile.property_locked:
        risks.append("房产锁定/解锁属于高风险操作节点，应以平台状态和教育部门审核结果为准。")

    deduped: list[str] = []
    seen = set()
    for item in risks:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped
