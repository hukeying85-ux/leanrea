#!/usr/bin/env python3
# 生成《抗菌肽深度学习1个月全流程优化计划》修订版 docx（基于审查意见全面修正，带时间戳，不覆盖原文件）
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import datetime

TS = "20261109_2245"
OUT_NAME = f"抗菌肽深度学习方案_三次审查修订与最终执行版_V3_{TS}.docx"

doc = Document()

# ---------- 基础样式 ----------
normal = doc.styles["Normal"]
normal.font.name = "宋体"
normal.font.size = Pt(10.5)
normal.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")

def set_cell_bg(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color_hex)
    tcPr.append(shd)

def add_heading(text, level=1, color=(0x1F, 0x4E, 0x79)):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(14 if level == 1 else 12 if level == 2 else 11)
    r.font.color.rgb = RGBColor(*color)
    r.font.name = "黑体"
    r.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
    p.space_before = Pt(10 if level == 1 else 6)
    p.space_after = Pt(4)
    return p

def add_para(text, bold=False, size=10.5, italic=False, color=None, space_after=4):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    r.font.size = Pt(size)
    if color:
        r.font.color.rgb = RGBColor(*color)
    p.space_after = Pt(space_after)
    return p

def add_bullet(text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_prefix:
        r1 = p.add_run(bold_prefix)
        r1.bold = True
        r1.font.size = Pt(10.5)
    r2 = p.add_run(text)
    r2.font.size = Pt(10.5)
    p.space_after = Pt(2)
    return p

def add_table(headers, rows, widths=None, header_bg="1F4E79"):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(headers):
        cell = t.cell(0, j)
        cell.text = ""
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True
        r.font.size = Pt(9.5)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        r.font.name = "黑体"
        r.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        set_cell_bg(cell, header_bg)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i + 1, j)
            cell.text = ""
            p = cell.paragraphs[0]
            r = p.add_run(str(val))
            r.font.size = Pt(9)
            r.font.name = "宋体"
            r.element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            if i % 2 == 1:
                set_cell_bg(cell, "F2F6FB")
    if widths:
        for j, w in enumerate(widths):
            for i in range(len(rows) + 1):
                t.cell(i, j).width = Inches(w)
    return t

# ================= 封面 =================
for _ in range(3):
    doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("抗菌肽深度学习1个月全流程优化计划")
r.bold = True
r.font.size = Pt(22)
r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
r.font.name = "黑体"
r.element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("（最终定稿 · 落实审查意见 · 带时间戳 · 不覆盖原文件）")
r.font.size = Pt(13)
r.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
r.italic = True

doc.add_paragraph()
add_table(
    ["项目", "内容"],
    [
        ["论文题目", "基于深度学习的阿尔茨海默病(AD)患者与健康对照者肠道微生物组中抗菌肽(AMP)的差异性分析"],
        ["英文题目", "Differential Analysis of Antimicrobial Peptides in Gut Microbiota of AD Patients vs. Healthy Controls Using Deep Learning"],
        ["所属学科", "生命科学学院 · 生物学 · 生物化学与分子生物学方向"],
        ["文科号 / 指导教师", "2024110316 · 申莲"],
        ["计划周期", "2026-11-09 至 2026-12-09（共 30 天 / 4 阶段）"],
        ["本版生成时间", f"2026-11-09 {TS[8:10]}:{TS[10:12]}"],
        ["版本号", f"v{TS}_三次审查修订与最终执行版_DualAMP-Lite 主线 + 诚实文献声明 + 审查回应表 + P0技术修正"],
        ["文档性质", "三次审查修订与最终执行版（V3），供另一位 AI 审查及导师评阅，P0项修正后可作为正式执行版"],
        ["存放位置", "Google Drive 文件夹：16_抗菌肽深度学习建模学习总结_2026-11-08"],
        ["版本管控", "本文件为带时间戳的新版，不覆盖云盘内任何历史版本；历史版本保留供对照"],
        ["核心模型", "基于 ESM-2 冻结主干 + 多尺度 1D-CNN + 生物物理先验的自组装分类架构（不宣称已有直接对应高分SCI）"],
        ["性能目标表述", "CD-HIT 0.4 低同源测试集 AUC ≥ 0.88 为假设性参考，最终以独立测试结果为准，不作为强制验收指标"],
    ],
    widths=[1.8, 4.7],
)
doc.add_paragraph()
add_para("本计划基于云盘文件夹内全部 9 份历史文件综合整理，并落实两轮外部审查AI的全部修正意见。本文档为 V3 最终执行版，包含完整的审查意见回应表（§1.3）和 P0/P1/P2 级技术修正清单（§1.4），说明每条审查问题的判断、严重程度、修正措施及对应文档章节，供另一位 AI 审查及导师评阅。P0 项（Aliphatic Index 公式、Cross-Attention 结构缺陷、ESM-2 BOS/CLS 用法、AD 队列记录核对等）已全部修正，可作为正式执行版。", italic=True, size=9.5, color=(0x7F, 0x7F, 0x7F))

doc.add_page_break()

# ================= §1 现状盘点 =================
add_heading("§1 现状盘点：9 份历史文件综合（云盘文件夹全部材料）", 1)
add_para("云盘文件夹 `16_抗菌肽深度学习建模学习总结_2026-11-08` 内共 9 个文件（7 份 .docx + 2 份 Google Docs）。本版在继承现有材料的同时，对其中与审查意见冲突的部分已做标注与修正。", size=10.5)

add_table(
    ["#", "文件名", "类型", "核心定位（本版本继承关系与修正提示）"],
    [
        ["F1", "开题.docx", "已完成", "开题报告定稿：AD-80-枸橼 + APH 假设 + 菌落组装必要性；作为论文第1章立论依据，保留其科学假设，不重复推导"],
        ["F2", "抗菌肽深度学习建模方法学总结.docx", "已完成", "四类主流建模路线拆解，作为 §3 选型依据"],
        ["F3", "总结.docx", "已完成（需修正）", "公开数据库与清洗标准：原文按 APD3 ~3,940 条记录，但 APD 已更新至 APD6（2026年），官方 2024 年天然已知活性 AMP 下载集为 3,306 条；DRAMP 4.0 30,260 条记录包含专利等，不能等同实验验证正样本。本版已在 §4 重新设计数据来源。"],
        ["F4", "抗菌肽深度学习1个月全流程优化计划_整合版_DualAMP-Lite_2026-11-09_1530.docx", "已完成（本修订版基于此）", "原30天整合版，作为直接蓝本；本版对其中过高交付承诺、虚假数值指标、AD四组分描述等已修正"],
        ["F5", "抗菌肽深度学习1个月全流程跟踪实践手册_DualAMP_Net.docx", "已完成", "DualAMP-Net 30天实操手册：4库下载、三层负样本、模型选型、训练参数、10折交叉验证、图表输出标准"],
        ["F6", "抗菌肽深度学习1个月全流程跟踪实践手册_V2简合优化版_DeepMetaAMP.docx", "已完成", "DeepMetaAMP V2.0 整合升级版：5 Seeds × 10-Fold，外部验证 AMPSphere + GenPept-Curated-2025。审查意见指出：AMPSphere 863,498 条为计算发现候选肽，不能全部当实验阳性标签；GenPept-Curated-2025 为 2026 预印本，11,000 条，可作为补充基准但不能等同实验验证集。"],
        ["F7", "AD通道微生物组抗菌肽深度学习研究全新新方案_HierMetaAMP.docx", "已完成（第二阴兵）", "HierMetaAMP 22周重构方案：LoRA 微调 + 层次化多任务 + 四大脑区菌落拓扑。本30天计划明确 NOT 做 HierMetaAMP 主线，仅预留接口，防范资源冲突"],
        ["F8", "论文课题方案：基于深度学习的通道微生物组抗菌肽预测模型设计、文献综述与时间规划 (DeepMetaAMP)", "已完成（Google Docs，需修正）", "顶层课题方案：原方案提及 AD 五期分层队列。审查意见指出：PRJNA798058 并非 NC/SCD/MCI/AD 四组，PRJNA489760 需按样本类型筛选，PRJNA679346 需逐一确认认知状态。本版已在 §4.2 更正 AD 队列描述，暂不使用“五阶段 AD 分层分析”结论。"],
        ["F9", "隔壁农药残留抗菌肽课题规划", "已完成（Google Docs，独立课题）", "独立课题（农药残留AMP），与本AD肠道微生物组课题数据来源与目标不同，本计划不复用其数据，避免课题间混淆"],
    ],
    widths=[0.4, 2.6, 1.0, 3.5],
)

doc.add_paragraph()
add_heading("§1.3 外部审查意见回应表（逐条落实）", 2)
add_para("本表对外部审查AI提出的六个核心审查项目及详细问题，逐条给出判断、严重程度、修正措施及对应文档章节，供审查AI与导师核对。", size=10.5)

add_table(
    ["审查项目", "审查判断", "严重程度", "修正措施（本版落实）", "对应章节"],
    [
        ["ESM-2 + 多尺度 CNN + 理化特征架构", "技术路线成立，但架构需要简化和明确", "中", "采用阶梯式推进：先简化基线（ESM-2 Mean Pooling + 32D 理化 + 浅层 MLP），再加入多尺度 1D-CNN 支路，最后通过消融证明 Cross-Attention/Gated Fusion/Focal Loss 必要性；Focal Loss 超参数在验证集上网格搜索，不作为固定值", "§3.2"],
        ["AMP 正负样本构建", "数据库有价值，但标签质量及数据偏倚没有解决", "高", "跨数据库按序列去重；仅保留明确实验验证记录；APD6 替代过时 APD3（官方 3,306 条）；DRAMP 4.0 不等同实验验证正样本；MIC 元数据记录；Scrambled 仅作挑战集", "§4.1"],
        ["CD-HIT 0.4 低同源测试", "方向正确，现有切分与交叉验证描述不够严谨", "高", "全部序列统一去重聚类 + Group-based Split；明确 CD-HIT 覆盖率参数；StandardScaler 仅训练集拟合；外部验证集不参与模型选择；配对比较 + 按同源簇 Bootstrap 置信区间", "§5"],
        ["5 Seeds × 10-Fold", "可以执行，但统计分析设计需要调整", "中高", "不能把 50 个折当 50 个独立观测做普通 t 检验；同一独立测试集上配对比较；推荐方案 A（分组交叉验证 + 外部验证集）或方案 B（先固定独立测试集）择一", "§5"],
        ["AD 队列分析", "存在明确的数据分组错误和缺少丰度分析的问题", "很高", "PRJNA798058 并非 NC/SCD/MCI/AD 四组，暂不使用“五阶段 AD 分层分析”；先制作样本级元数据表确认可比组别；AMP 分类与 AD 差异增加 reads 回贴、丰度定量、标准化、混杂因素校正完整分析链", "§4.2, §4.3"],
        ["30 天全部交付", "可以完成缩减后的模型研究，不能保证当前全部产出", "很高", "交付物清单大幅缩减（§6）；所有性能指标改为“假设性参考”，最终以独立测试集为准，不作为强制验收指标", "§6, §7"],
    ],
    widths=[1.8, 1.9, 0.9, 3.2, 0.9],
)

doc.add_paragraph()
add_heading("§1.4 P0/P1/P2 级技术修正清单（三次审查必须落实）", 2)
add_para("本表汇总两轮外部审查发现的全部技术问题，标注优先级与修正状态，供审查AI与导师逐项核对。", size=10.5)

add_table(
    ["优先级", "修正项目", "审查发现的问题", "V3 修正措施", "对应章节", "状态"],
    [
        ["P0", "Aliphatic Index 公式", "原公式 AI=100(1.8V+2.9I+3.9L)/L 缺少丙氨酸且系数对应错误", "改为 ExPASy ProtParam 标准：AI=X(Ala)+2.9X(Val)+3.9[X(Ile)+X(Leu)]，X 为摩尔百分比", "§3.3", "已修正"],
        ["P0", "Cross-Attention 结构缺陷", "Key/Value 长度仅1，softmax 输出恒为1，不是真正的交叉注意力", "主模型改为 Concat（ESM-2 CNN 128维 + 理化特征 MLP 64维 = 192维）；真正多Token Cross-Attention 降级为选做 M4", "§3.2", "已修正"],
        ["P0", "ESM-2 全局分支 BOS/CLS 用法", "官方预训练模型不建议使用 BOS 特征作为全局语义向量", "使用 Masked Mean Pooling，仅包含真实氨基酸残基，不含 BOS/EOS/Padding", "§3.2", "已修正"],
        ["P0", "PRJNA798058 164条记录核对", "不能未经证实直接认定为技术重复", "修改为“164个 BioSample/Experiment 记录与93名受试者之间的对应关系尚待核验”，建立 Subject-BioSample-Experiment-Run 关系表", "§4.2", "已修正"],
        ["P0", "PRJNA679346 43 vs 106 差异", "原研究43份样本与当前页面106条记录存在差异", "从 NCBI 导出全部106条记录，按 BioSample ID 与原论文43份样本清单匹配，只纳入具有明确诊断标签的样本", "§4.2", "已修正"],
        ["P0", "细菌 AMP 专项训练层", "训练数据主要来自动物来源 AMP，与肠道细菌 AMP 存在领域偏移", "增加细菌 AMP 专项数据层（General AMP + Bacterial AMP + Negative Background + Hard Negative + Scrambled），单独报告细菌来源 AMP 测试结果", "§4.1", "已修正"],
        ["P0", "cAMP 核苷酸参考集", "Bowtie2 需要核苷酸序列，不能直接用氨基酸序列比对 DNA reads", "建立双重序列索引：cAMP_aa.fasta（模型预测）+ cAMP_nt.fasta（Bowtie2 回贴）+ cAMP_mapping.tsv 对应关系", "§4.3", "已修正"],
        ["P0", "DESeq2 输入 counts", "不能将 CPM/TPM 输入 DESeq2，官方要求原始整数 counts", "主分析使用原始整数 counts 构建计数矩阵，CPM/TPM 仅作为描述性丰度，不进入 DESeq2", "§4.3", "已修正"],
        ["P1", "AAC 与理化特征冗余处理", "AAC 20维天然存在线性约束（总和=1），Length/MW 高度相关", "计算训练集相关性矩阵，高度相关特征分组，比较保留/去除后模型性能，SHAP 不过度解释单个相关变量，不强行凑齐32维", "§3.3", "已修正"],
        ["P1", "成熟肽加工与基因簇注释", "细菌前体肽可能经过 Leader peptide 切割、修饰、环化等，直接预测前体序列可能不准确", "增加二次注释步骤：Precursor peptide、Leader peptide、Mature peptide region、Transport genes、Modification genes、BGC context（antiSMASH RiPP）", "§4.3", "已修正"],
        ["P1", "固定测试集与交叉验证关系", "50次训练不能作为50个独立统计样本", "明确三层结构：开发集（Group 5-Fold CV + 5 Seeds，用于模型选择和超参数调优）/ 独立测试集（一次最终评估，完全不接触训练）/ 外部验证集（AMPSphere 实验验证子集，不参与任何模型选择）", "§5", "已修正"],
        ["P1", "AMPSphere 实验测试集使用", "79条阳性无法计算 Specificity/MCC/F1/AUROC，需阴性样本", "核对原始研究100条体外测试肽（79条阳性+21条阴性），作为独立测试集；863,498条候选序列仅用于候选识别和新颖性分析，不用于计算实验验证准确率", "§5", "已修正"],
        ["P1", "P6 条件交付", "四天完成0.78 TB 三队列原始数据处理不现实", "P6 改为条件交付：若已有组装和 ORF 数据，做完整样本级丰度分析；否则30天内先完成一个发现队列完整分析，另外两个队列完成元数据审计和独立验证准备", "§6", "已修正"],
        ["P2", "85%共识度删除", "无量化方法，不是独立专家一致性检验结果", "删除“85%共识度”表述，改为定性表述", "§1", "已修正"],
        ["P2", "SHAP/Helical Wheel 精简", "不强制补图，按真实结果确定", "SHAP 和 Helical Wheel 作为可选可解释性分析，不列为必做交付物", "§6", "已修正"],
        ["P2", "DeLong 检验使用", "DeLong 不能用于证明 MCC 差异不显著，p>0.05 不代表等效", "AUROC 用 DeLong 配对检验；MCC 用配对 Bootstrap；AUPRC 用配对 Bootstrap；多重比较 FDR 校正；预先设定等效界值", "§5", "已修正"],
        ["P2", "文件规范性", "14列实际列出16个字段；中英文题名语义不完全对应；CONSORT 流程图不冒用", "统一列数，统一题名表述，使用队列样本纳入与排除流程图替代 CONSORT", "§1, §6", "已修正"],
    ],
    widths=[0.6, 1.5, 2.2, 2.6, 0.9, 0.7],
)

doc.add_paragraph()
add_heading("§1.5 三判断标准评估总结（能否实现 / 能否得到可信结果 / 能否支撑论文结论）", 2)
add_table(
    ["评估维度", "能否实现（30天）", "能否得到可信结果", "能否支撑论文结论", "说明"],
    [
        ["ESM-2 冻结特征提取", "是（单卡 T4，单轮约 4 分钟）", "是（多篇顶刊验证）", "是（可作为方法学基础）", "技术风险低"],
        ["正负样本高质量构建（含细菌 AMP 层）", "是（需人工标签审核，时间紧张）", "条件成立（需完成去重、标签审核、细菌 AMP 分层）", "是（数据质量决定论文可信度）", "审查意见 #3 核心"],
        ["低同源独立测试（固定测试集）", "是（Group-based Split 可执行）", "是（避免同源泄漏）", "是（提升模型可信度）", "审查意见 #4 核心"],
        ["AD 队列差异分析（元数据核对后）", "部分（元数据确认后才能确定组别）", "不确定（取决于元数据质量和样本量）", "不确定（需丰度定量 + 混杂因素校正）", "审查意见 #1、#2 核心，风险很高"],
        ["模型架构消融与选择（Concat 为主）", "是（先简化后复杂，M4/M5 选做）", "是（消融可证明模块必要性）", "是（可支持方法学章节）", "审查意见 #5 核心"],
        ["30 天全部原交付物", "否（承诺过高）", "否（部分指标无依据）", "否（无法保证所有产出）", "审查意见 #6 核心，已缩减，P6 条件交付"],
    ],
    widths=[1.8, 1.6, 1.8, 1.8, 1.5],
)

doc.add_page_break()

# ================= §2 总体定位（修正版） =================
add_heading("§2 总体定位：30 天聚焦一个可落地的研究问题", 1)
add_para("核心策略：不追求模型堆砌，只追求“可复现 + 可解释 + 能支撑论文第3章”。30 天只攻一个主模线（基于 ESM-2 冻结主干的 AMP 二分类器），两个基准模型（RF/XGBoost + 1D-CNN+BiGRU）作为对照。HierMetaAMP 明确作为第二阴兵预留接口，不纳入 30 天主线。", size=10.5)

add_para("【审查意见落实】30 天交付承诺已缩减：不再承诺 6 张 300 DPI 主图、8,000 字第3章、AD 五期分层差异分析等过高产出；具体交付物见 §6，所有性能数值改为“假设性参考”，最终以独立测试集结果为准。", italic=True, size=10, color=(0xC0, 0x39, 0x2B))

add_table(
    ["判定维度", "本30天计划（主线，修正后）", "明确不做 / 预留接口"],
    [
        ["模型主线", "基于 ESM-2 冻结主干（esm2_t12_35M） + 多尺度 1D-CNN（k=3,5,7，残基级特征） + 生物物理先验（32维，完整定义） + 浅层融合分类头；起步采用简化模型，再通过消融证明复杂模块增益", "HierMetaAMP（LoRA + 层次化多任务 + 四大脑区菌落拓扑）：22周重构方案，仅在 §9 预留多任务标签接口，30天不纳入"],
        ["数据侧重", "AD 肠道微生物组 AMP 候选筛选，但先完成样本级元数据表确认，暂不使用“NC/SCD/MCI/AD 四组”或“五阶段 AD 分层”结论", "隔壁农药残留 AMP 课题（独立课题，不复用其数据，防混淆）"],
        ["计算资源", "单卡消费级显卡 / Colab T4 / Kaggle 2×T4；ESM-2 离线提取单轮约 4 分钟", "不依赖 AlphaFold2/ESMFold 3D 结构预测动态模拟（短肽在水中为无规则卷，计算开销大且置信度低）"],
        ["交付物", "见 §6 缩减后的交付物清单；所有性能指标均为假设性参考", "不产出完整的生物实验验证湿实验方案；不承诺 AUROC 0.978、MCC 0.795 等具体数值"],
    ],
    widths=[1.5, 3.0, 3.0],
)

doc.add_page_break()

# ================= §3 模型选型（V3 修正版） =================
add_heading("§3 模型选型：ESM-2 冻结 + 序列语义与理化特征融合（Concat 为主）", 1)
add_para("对四类建模路线的对比结论（继承 F2 方法学总结，并结合两轮审查意见修正）：", size=10.5)

add_table(
    ["路线", "代表模型", "优点", "缺点 / 本计划决策（V3 修正后）"],
    [
        ["传统手工特征 + 树模型", "RF / XGBoost + AAC/DPC/PseAAC (32–138D)", "参数少、训练快（10分钟）、特征重要度可解释", "丢失了肽序位置信息，0.4 低同源集表现一般，作为基准 M0-RF/XGBoost 保留"],
        ["从头训练序列DL", "1D-CNN + BiGRU + Masked Attention (无 ESM-2)", "端到端、保留局部基序", "小样本下易过拟合，0.4 低同源集 AUC 明显下降，作为基准 M0-CNN-BiGRU 保留"],
        ["3D 结构图网络", "AlphaFold2/ESMFold + GAT / GCN", "结构信息丰富", "短肽在水中无规则卷，pLDDT 低，计算开销大，明确排除作为主模型"],
        ["预训练语言模型 + 浅头", "ESM-2 (t12_35M 冻结) + 多尺度 1D-CNN + 生物物理先验 + Concat 融合", "进化语义 + 生物域先验 + 小样本友好 + 可解释；Cross-Attention 因单 Token 结构缺陷降级为选做", "本计划主模线，架构见 §3.2（Concat 为主，M4/M5 选做）"],
    ],
    widths=[1.4, 2.2, 2.2, 2.7],
)

add_heading("§3.2 模型架构：修正后的双分支表示（消除技术矛盾）", 2)
add_para("原方案存在技术矛盾：ESM-2 输出 (N, L, 480) 若先平均池化成 (N, 480)，即丢失了残基位置顺序，无法再用于残基级多尺度卷积。V3 修正后保留两种表示：", size=10.5)

add_table(
    ["分支", "输入表示", "用途", "说明（V3 修正）"],
    [
        ["支路 A（局部基序）", "ESM-2 残基级特征 (N, L, 480)，不池化", "多尺度 1D-CNN (k=3,5,7) 提取局部序列基序，后全局最大池化", "保留位置顺序信息，供 CNN 捕获氨基酸模式"],
        ["支路 B（全局表征）", "ESM-2 Masked Mean Pooling (N, 480) + 生物物理先验", "全局序列表征与理化性质并行，接浅层 MLP 分类头", "使用 Masked Mean Pooling（仅含真实氨基酸残基，不含 BOS/EOS/Padding），不使用 BOS/CLS 作为全局语义向量"],
        ["融合头（主模型 M3）", "支路 A 输出 (128维) + 支路 B 理化特征 MLP 输出 (64维) 拼接", "Concat 得到 192维融合向量 → 浅层 MLP (64→1) 输出 AMP 置信度 logit", "不使用 Cross-Attention（单 Token Key/Value 结构缺陷）；Concat 最稳定、最易实现和验证"],
        ["融合头（选做 M4/M5）", "真正多 Token Cross-Attention 或 Gated/FiLM 融合", "理化特征编码为 32 个特征 Token，与残基级 ESM 表示做交叉注意力", "M4/M5 降级为选做，需额外定义特征 Token 编码、类型嵌入、尺度处理、聚合方法，实现和解释成本更高"],
    ],
    widths=[1.4, 2.2, 2.4, 2.0],
)

add_para("【模型实验排序（V3 推荐）】不建议一开始就叠加所有模块。推荐实验顺序：", size=10.5)
add_table(
    ["模型", "结构", "是否必做", "用途"],
    [
        ["M0-RF/XGBoost", "理化特征 + 树模型", "是", "基准模型，建立通用 AMP 分类能力下限"],
        ["M0-CNN-BiGRU", "从头训练序列网络（无 ESM-2）", "是", "基准模型，验证 ESM-2 先验必要性"],
        ["M1", "ESM-2 Masked Mean Pooling + 浅层 MLP", "是", "ESM-2 全局表征基线"],
        ["M2", "ESM-2 残基级 + 多尺度 1D-CNN", "是", "验证残基级 CNN 是否有增益"],
        ["M3", "ESM-2 CNN + 理化特征 Concat (192维)", "核心主模型", "M2 + 理化特征，验证理化先验是否提供显著增益"],
        ["M4", "真正多 Token Cross-Attention", "选做", "仅在 M3 显示明确增益后再考虑"],
        ["M5", "Gated/FiLM Fusion", "选做", "仅在 M3 显示明确增益后再考虑"],
    ],
    widths=[1.2, 2.6, 0.8, 2.9],
)

add_para("【关键消融比较】M3 与去掉理化特征后的 M2 做对比。如果 M3 明显优于 M2，才能证明加入生物物理先验确实有贡献；如果 M2 和 M3 差异不明显，应诚实报告理化特征未提供显著增益，而不是强行宣称双路架构优越。", size=10.5, italic=True)

add_heading("§3.3 生物物理特征完整定义（V3 修正：公式与冗余处理）", 2)
add_para("原方案列出的项目仅 29 维，V3 补充为完整定义，并修正了 Aliphatic Index 计算公式和 Boman Index 来源说明：", size=10.5)

add_table(
    ["#", "特征组", "具体指标", "维数", "计算依据与公式（V3 修正）"],
    [
        ["1", "氨基酸组成 (AAC)", "20 种标准氨基酸摩尔百分比", "20", "ProteinAnalysis.get_amino_acids_percent()，注意：20维总和恒等于1，存在线性约束"],
        ["2", "全局理化性质", "分子量 (kDa)、净电荷 @pH 7.4、等电点 (归一化 /14)、GRAVY、不稳定指数 (归一化 /100)、芳香性", "6", "Bio.SeqUtils.ProtParam；净电荷需明确 N 端、C 端电荷贡献及各基团 pKa 参数，H 在 pH 7.4 下不简单当作完全带正电"],
        ["3", "两亲疏水性导数", "α-螺旋疏水力矩 (Eisenberg, 100° 旋转)、正带电残基比例 (KRH)、负带电残基比例 (DE)、疏水残基比例 (AILMFWVY)、α-螺旋形成倾向残基比例 (AEMQLW)", "5", "Kyte-Doolittle 疏水度，Eisenberg 两亲性"],
        ["4", "补充指标", "肽长度、正负电荷残差数之差、不稳定指数是否 > 40 标记 (0/1)", "3", "长度直接计算；电荷残差数之差 = 正带电数 - 负带电数；不稳定指数标记阈值 40"],
        ["合计", "", "", "32", ""],
    ],
    widths=[0.5, 1.8, 2.2, 0.6, 2.9],
)

add_para("【Aliphatic Index 公式修正（P0 必修）】原公式 AI=100(1.8V+2.9I+3.9L)/L 缺少丙氨酸且系数对应错误，V3 改为 ExPASy ProtParam 标准：", size=10.5)
add_para("AI = X(Ala) + 2.9 × X(Val) + 3.9 × [X(Ile) + X(Leu)]", size=10.5)
add_para("其中 X 为氨基酸摩尔百分比。若使用 0–1 的小数比例，则需要乘以 100。Aliphatic Index 原本主要用于描述蛋白质脂肪族侧链体积与热稳定性关系，用于短肽 AMP 分类可作为描述符，但不能直接解释为抗菌能力或膜破坏能力。", size=10.5)

add_para("【Boman Index 来源固定（P0 必修）】Boman Index = Σ ΔG(氨基酸侧链) / L。必须明确：使用哪一套 20 种氨基酸侧链自由能数值、自由能来源、单位、正负号约定。建议使用经过核验的 APD 或 Peptides 包规则，并通过已知序列进行计算结果交叉验证。", size=10.5)

add_para("【特征冗余处理（P1 必修）】不为了凑齐 32 维而强行保留所有特征。V3 流程：", size=10.5)
for item in [
    "1. 先保留原始特征定义；",
    "2. 计算训练集内部的相关性矩阵（AAC 20维天然存在线性约束，总和=1；Length 与 MW 高度相关；Aliphatic Index 与部分 AAC 特征重叠；Boman Index 与 GRAVY 可能相关）；",
    "3. 对高度相关（r > 0.85）的特征进行分组；",
    "4. 比较保留与去除相关特征后的模型性能；",
    "5. SHAP 不单独过度解释高度相关的单个变量；",
    "6. 实际得到 29 维、30 维或 32 维，只要有明确的生物物理依据，都比为了凑齐 32 维更合理。",
]:
    add_bullet(item)

doc.add_page_break()

# ================= §3.5 文献核验与学术诚实声明（保留并精简） =================
add_heading("§3.5 模型选型的文献核验与学术诚实声明（供审查）", 2)
add_para("本计划主模线名为“基于 ESM-2 冻结主干的 AMP 分类器”。为避免学术误导，对其文献支撑情况做如下诚实核验：", size=10.5)

add_heading("§3.5.1 各模块的已有高分SCI支撑", 3)
add_table(
    ["模块", "已有高分SCI支撑（2024–2026）", "支撑程度"],
    [
        ["ESM-2 冻结主干", "Nature Comm 2024 deepAMP[3]；Science Advances 2025 AMP-Designer[10]；Frontiers in Pharmacology 2026 ESM-2+ML 虚拟筛选[1]；J. Chem. Inf. Model. 2024 ESM-2+图DL[6]；Cell Biomaterials 2025 AMP-Diffusion[2]；Scientific Reports 2025 CG-AMP[7]；Briefings in Bioinformatics 2025 Pepxml[5]；J. Cheminform. 2026 PepGraphormer[8]", "充分（多篇顶刊验证 ESM-2 对 AMP 预测有效）"],
        ["ESM-2 + 生物物理先验双支路", "Bhatnagar et al. 2024 ESM-2嵌入+QSAR描述符融合[5]；CG-AMP Sci Rep 2025 双模块架构[7]", "较强（理念一致）"],
        ["多尺度 1D-CNN (k=3,5,7)", "Deep-AmPEP30 Mol. Ther. Nucleic Acids 2020[1]", "中等（经典方法）"],
        ["Cross-Attention + Gated Fusion", "PMC 2026 双扩散模型框架使用 Cross-Attention[5]；AMP 领域未见该精确组合的高分SCI", "中等（有相近做法，无精确组合文献）"],
        ["Focal Loss", "源于目标检测 (Lin et al. 2017)；AMP 预测领域未见专门验证该超参数组合的高分SCI", "弱（通用技术，视为可调超参数）"],
    ],
    widths=[2.0, 4.0, 1.5],
)

add_para("【关于“DualAMP-Lite / DeepMetaAMP”名称的诚实声明】经检索 Nature Communications、Science Advances、J. Chem. Inf. Model. (ACS)、Scientific Reports (Nature)、Briefings in Bioinformatics、Cell Biomaterials 等近两年高分SCI，未发现名为“DeepMetaAMP”或“DualAMP”的已发表模型论文。相近名称包括 DMAMP (TCBB 2024)、deepAMP (Nature Comm 2024)、AMP-DualTransNet (2026)、XAMP (bioRxiv 2025, SJTU，ESM-2+Transformer 双引擎，中位数 AUC 0.972)。XAMP 与本计划双支路思想高度相近，是最近学术基准。", size=10.5, italic=True)

add_heading("§3.5.2 建议的文献引用格式（审查时可直接使用）", 3)
add_table(
    ["#", "文献", "期刊/年份", "DOI / 链接"],
    [
        ["[1]", "Yan J, et al. Deep-AmPEP30: Improve Short Antimicrobial Peptides Prediction with Deep Learning", "Mol. Ther. Nucleic Acids, 2020", "10.1016/j.omtn.2020.05.006"],
        ["[2]", "Latent diffusion on evolutionary-scale embeddings accelerates antimicrobial peptide discovery (AMP-Diffusion)", "Cell Biomaterials, 2025", "见 Cell Biomaterials 官网"],
        ["[3]", "A Foundation Model Identifies Broad-Spectrum Antimicrobial Peptides against Drug-Resistant Bacterial Infection (deepAMP)", "Nature Communications, 2024", "10.1038/s41467-024-51933-2"],
        ["[4]", "Chen B, et al. A Global Discovery of Antimicrobial Peptides in Deep-Sea Microbiomes Driven by an ESM-2 and Transformer-based Dual-Engine Framework (XAMP)", "bioRxiv, 2025", "10.1101/2025.11.20.689422"],
        ["[5]", "Bhatnagar P, et al. Integration of Protein Language Model Embeddings and QSAR Descriptors in a Gradient Boosting Framework for AMP Classification", "Int. J. Bioinformatics & Biostatistics, 2024/2025", "见期刊官网"],
        ["[6]", "Cordoves-Delgado G, García-Jacas CR. Predicting Antimicrobial Peptides Using ESMFold-Predicted Structures and ESM-2-Based Amino Acid Features with Graph Deep Learning", "J. Chem. Inf. Model., 2024", "10.1021/acs.jcim.3c02061"],
        ["[7]", "Li G, et al. Antimicrobial peptide prediction based on contrastive learning and gated convolutional neural network (CG-AMP)", "Scientific Reports, 2025", "10.1038/s41598-025-29666-z"],
        ["[8]", "PepGraphormer: an ESM-GAT hybrid deep learning framework for antimicrobial peptide prediction", "Journal of Cheminformatics, 2026", "10.1186/s13321-025-01144-8"],
        ["[9]", "Discovery of antimicrobial peptides in the global microbiome with machine learning (AMPSphere)", "Cell, 2024", "见 Cell 官网"],
        ["[10]", "Discovery of antimicrobial peptides with notable antibacterial potency by an LLM-based foundation model (AMP-Designer)", "Science Advances, 2025", "10.1126/sciadv.ads8932"],
    ],
    widths=[0.5, 3.2, 1.6, 2.2],
)

doc.add_page_break()

# ================= §4 数据方案（V3 全面修正） =================
add_heading("§4 数据方案：正负样本体重新设计 + AD 队列元数据核对 + AMP 分类→AD 差异完整分析链", 1)

add_heading("§4.1 正负样本体系重新设计（V3：增加细菌 AMP 专项层）", 2)
add_para("原方案将数据库下载记录直接当作 6,000–8,000 条独立实验阳性样本，存在重复、标签质量和活性阈值不一致问题。且训练数据主要来自动物来源 AMP，与肠道细菌 AMP 存在领域偏移。V3 修正后：", size=10.5)

add_table(
    ["数据层", "组成", "用途", "备注（V3 新增）"],
    [
        ["General AMP", "多来源实验验证 AMP（APD6、DBAASP v3、DRAMP 4.0、CAMPR4 仅 Experimentally Validated 记录）", "建立通用 AMP 分类能力", "APD 已更新至 APD6；官方 2024 年天然已知活性 AMP 下载集为 3,306 条，不再按 APD3 ~3,940 条计算"],
        ["Bacterial AMP", "细菌来源 bacteriocins 和其他细菌 AMP", "增强与肠道微生物组的适配性", "V3 新增：解决训练数据与真正要筛选的肠道细菌 AMP 之间的领域偏移"],
        ["Negative Background", "非 AMP 蛋白片段及其他背景序列", "识别非 AMP", "来自 UniProt 细胞内蛋白，作为弱阴性"],
        ["Hard Negative", "实验无活性肽（DBAASP 中经过实验检测但无活性的多肽）", "特异性挑战", "区分“无活性结果”与“未检测”记录"],
        ["Scrambled", "正样本序列随机打乱（保持 AAC 与净电荷不变）", "序列位置对抗测试", "仅作为额外挑战集，不作为真实生物学负样本参与训练"],
    ],
    widths=[1.2, 2.4, 1.8, 2.1],
)

add_para("【正样本标签审核】仅保留有明确实验验证活性记录的序列；仅凭“数据库收录”不判定为实验验证阳性；DRAMP 4.0 的 30,260 条记录包含专利等，不等同实验验证正样本数量。正样本最终数量以去重、长度过滤、标签审核后的真实数量为准。", size=10.5)

add_para("【MIC 阈值处理】MIC 受菌株、实验条件和测定方法影响，不同来源的 MIC 不简单混合为绝对统一活性标签；记录原始 MIC、菌株、检测方法作为元数据，避免标签噪声。", size=10.5)

doc.add_paragraph()
add_heading("§4.2 AD 队列元数据核对（V3：P0 级必须修正）", 2)
add_para("原方案将 PRJNA798058 描述为 NC/SCD/MCI/AD 四组发现队列，但 NCBI BioProject 原始说明明确：该项目研究的是 43 名具有临床前 AD 生物标志物证据但认知正常的个体，以及 50 名没有 AD 证据且同样认知正常的对照者。因此不能直接划分为四个临床阶段。V3 修正如下：", size=10.5)

add_table(
    ["队列项目", "原方案描述（错误）", "V3 修正后的描述（基于 NCBI 原始说明）", "后续操作"],
    [
        ["PRJNA798058", "NC/SCD/MCI/AD 四组发现队列", "43 名临床前 AD 生物标志物阳性但认知正常个体 + 50 名认知正常对照者；不能直接划分为 NC/SCD/MCI/AD 四组", "暂不使用“五阶段 AD 分层分析”结论；先制作样本级元数据表，核对 164 个 BioSample/Experiment 记录与 93 名受试者的对应关系"],
        ["PRJNA489760", "直接作为粪便样本外部验证队列 (180 个实验记录)", "包含 AD、MCI 和正常对照的粪便与血液微生物组数据，需按样本类型（粪便/血液）筛选，不能将所有实验记录直接当作粪便样本", "按样本类型筛选粪便样本，再确认诊断标签；血液样本不参与肠道 AMP 丰度比较"],
        ["PRJNA679346", "日本人群标准 AD 队列 (43 份粪便)", "43 份人粪便宏基因组数据（日本人群），但当前 NCBI 页面显示 106 条记录，与原论文 43 份样本存在差异，需逐一核对", "导出全部 106 条 BioSample/Experiment 记录，按 BioSample ID 与原论文 43 份样本清单匹配，只纳入具有明确诊断标签的样本；22 份神经系统疾病相关样本不能直接全部定义为 AD"],
    ],
    widths=[1.3, 1.9, 2.6, 2.2],
)

add_para("【P0 必修前置任务】在任何 AD 差异分析前，先制作三个项目的样本级元数据表，明确每个样本的：诊断标签、粪便/血液样本类型、年龄、性别、BMI、测序批次。仅在元数据表确认后，再确定真正能够比较的组别。三个队列不能直接合并比较，应先独立分析，再比较一致性。", italic=True, size=10, color=(0xC0, 0x39, 0x2B))

doc.add_paragraph()
add_heading("§4.3 AMP 分类结果与 AD 差异的完整分析链（V3：P0/P1 级修正）", 2)
add_para("模型只能回答“某段氨基酸序列是否具有 AMP 样特征”，不能直接回答“AD 患者与健康对照者肠道微生物组中的 AMP 候选序列是否存在差异”。二者之间缺少样本级丰度定量环节。V3 修正后的分析链：", size=10.5)

steps = [
    "各样本独立进行宏基因组质控与组装，或在统一组装后保留样本来源信息；",
    "提取 smORF，进行序列去冗余和微生物来源核验；",
    "使用 AMP 模型对候选序列进行预测（输出置信度分数，非表达量）；",
    "将原始测序 reads 回贴到候选 ORF，获得每条候选 AMP 在每个生物学样本中的丰度（reads 计数）；",
    "按测序深度或适当标准化方法（如 TPM/CPM）进行丰度校正，仅作为描述性丰度；",
    "建立双重序列索引：cAMP_aa.fasta（AMP 模型预测、理化特征计算）+ cAMP_nt.fasta（Bowtie2/BWA 核苷酸序列比对）+ cAMP_mapping.tsv（氨基酸序列与编码核苷酸序列对应关系）；",
    "以原始整数 counts 建立基础计数矩阵，输入 DESeq2 进行差异分析（DESeq2 官方要求原始整数 counts，不能使用 CPM/TPM）；",
    "按 AD 与对照组（基于 §4.2 确认的真实可比组别）进行差异分析，并考虑年龄、性别、BMI、药物、研究队列等混杂因素；",
    "增加基因组当量归一化敏感性分析：AMP 基因覆盖度 / 单拷贝标记基因覆盖度，区分宿主微生物整体丰度升高 vs 基因相对丰度真正变化；",
    "增加成熟肽加工与基因簇注释二次分析：Precursor peptide、Leader peptide、Mature peptide region、Transport genes、Modification genes、BGC context（antiSMASH RiPP），作为候选肽生物学可信度的二次验证；",
    "不能只比较两个组的 AMP 候选序列数量，也不能把模型预测分数当作 AMP 表达量。",
]
for i, step in enumerate(steps, start=1):
    add_bullet(step, bold_prefix=f"步骤 {i}：")

add_para("【DESeq2 输入规范（P0 必修）】DESeq2 官方要求输入未标准化的整数 counts，而不是已经按测序深度标准化的 CPM/TPM。CPM/TPM 仅作为描述性丰度输出，不进入 DESeq2 模型。", size=10.5)

add_para("【Bowtie2 回贴参考（P0 必修）】Bowtie2 和 BWA 进行的是核苷酸序列比对，不能把蛋白质 FASTA 中的氨基酸序列直接交给 DNA reads 比对。必须使用 cAMP_nt.fasta 作为参考，并明确 MAPQ 阈值、唯一比对与多重比对处理规则、paired-end reads 计数规则、最低覆盖度。对不能可靠区分的高度相似候选序列，宁愿报告家族丰度，也不要强行给每条短肽分配精确丰度。", size=10.5)

doc.add_page_break()

# ================= §5 低同源验证与交叉验证统计设计（V3：固定测试集 + 开发集 + 外部验证） =================
add_heading("§5 低同源验证与交叉验证统计设计（V3 修正）", 1)
add_para("原方案虽认识到序列同源泄漏风险，但描述不够严谨。V3 修正后采用三层结构：", size=10.5)

add_table(
    ["设计层", "用途", "是否参与模型选择", "备注（V3 修正）"],
    [
        ["全部去重后的数据集", "跨数据库去重和同源聚类", "否", "所有阳性、阴性序列统一去重和相似性聚类，不能只对阳性序列处理"],
        ["开发集（Development Set）", "训练模型和超参数选择；Group 5-Fold CV + 5 个随机种子", "是", "Group-based Split，同一同源簇不跨训练/验证；超参数只根据开发集内部验证结果决定"],
        ["独立测试集（Independent Test Set）", "一次最终评估，模型架构、Focal Loss、分类阈值均不在此调整", "否", "聚类簇不能进入开发集；在同一独立测试集上进行配对比较 + 按同源簇 Bootstrap 置信区间"],
        ["外部验证集（External Validation）", "AMPSphere 实验验证子集等，完全不参与模型选择", "否", "只用于泛化能力验证，不计入任何模型调优"],
    ],
    widths=[2.0, 2.2, 1.0, 2.3],
)

add_para("【CD-HIT 参数（P1 必修）】0.80 聚类需同时约束长序列覆盖率（-aL 0.8）；0.40 定义为“操作性低序列一致性测试集”，而非绝对无同源测试集。短肽 10 aa 在 40% 一致性下只有 4 个匹配残基，不能充分证明生物学同源关系。保留 MMseqs2 二次相似性抽检。", size=10.5)

add_para("【同源簇冲突审核（P1 必修）】全部序列联合聚类；同一 UniProt 母蛋白来源的片段不能跨集合；同一 AMP 的不同数据库记录不能跨集合；原始 AMP 和 scrambled 对应序列不能跨集合；正负样本同一同源簇出现冲突标签时进行人工审核。", size=10.5)

add_para("【统计检验（P2 必修）】不能把 50 个折的 AUC 当作 50 个独立观测做普通 t 检验。AUROC 用 DeLong 配对检验；MCC 用配对 Bootstrap；AUPRC 用配对 Bootstrap；给出置信区间；多重比较 FDR 校正；p > 0.05 不代表两种模型等效，需预先设定等效界值。", size=10.5)

add_para("【AMPSphere 外部验证（P1 必修）】不能只用 79 条实验阳性序列评价完整分类性能（无法计算 Specificity/MCC/F1/AUROC，缺少阴性样本）。核对原始研究的 100 条体外测试肽：79 条具有相应实验活性，其余 21 条需根据原实验条件确认具体的无活性结果。将 100 条序列作为独立测试集合，保留全部活性和无活性结果。863,498 条未经实验验证的候选序列，只用于候选识别、模型预测重叠分析、序列新颖性分析，不用于计算实验验证意义上的真实准确率。", size=10.5)

doc.add_page_break()

# ================= §6 30 天缩减后交付物清单（V3：P6 条件交付） =================
add_heading("§6 30 天缩减后交付物清单（文件级，可直接对账）", 1)
add_para("【审查意见落实】原计划交付承诺过高，已大幅缩减。P6 改为条件交付。以下仅保留 30 天内可稳妥完成的核心产出；所有性能指标为假设性参考，最终以独立测试集结果为准。", italic=True, size=10, color=(0xC0, 0x39, 0x2B))

add_table(
    ["#", "交付物", "对应章节/节次", "格式", "备注（V3 修正）"],
    [
        ["D1", "AD 三队列样本级元数据表（诊断、样本类型、年龄、性别、BMI、测序批次）", "§4.2", "CSV", "P0 必修前置任务，确定可比组别，核对 164 条记录与 93 受试者对应关系"],
        ["D2", "去重、长度过滤、标签审核后的正负样本数据集（含细菌 AMP 专项层，真实数量为准）", "§4.1", "FASTA / CSV", "不再承诺 6,000–8,000 条，以实际审核后数量为准"],
        ["D3", "train/val/test.csv（基于同源簇的 Group-based Split，三层结构）", "§5", "CSV", "明确 CD-HIT 覆盖率参数，同源不泄漏，固定独立测试集"],
        ["D4", "train_feat.pt / val_feat.pt / test_feat.pt / biophys_scaler.pkl（ESM-2 残基级 + Masked Mean Pooling + 理化特征）", "§3.2 / §3.3", "PT / PKL", "Scaler 只在训练集拟合；Aliphatic Index/Boman Index 公式已修正"],
        ["D5", "基准模型（RF / XGBoost + 理化特征；1D-CNN+BiGRU 从头训练）及对照结果", "§3", "PKL / CSV", "作为主模型对照 M0-RF/XGBoost、M0-CNN-BiGRU"],
        ["D6", "主模型简化基线（ESM-2 Masked Mean Pooling + 理化特征 + 浅层 MLP，M1）及训练权重", "§3.2", "PT", "起步模型，先建立基线"],
        ["D7", "若 M2 显示增益，补充多尺度 1D-CNN 支路及权重（M2）", "§3.2", "PT", "有条件产出，非强制"],
        ["D8", "核心主模型 M3（ESM-2 CNN + 理化特征 Concat，192维融合）及权重", "§3.2", "PT", "V3 主模型，不使用有缺陷的 Cross-Attention"],
        ["D9", "消融实验结果（M3 vs M2 去掉理化特征；M4/M5 选做）", "§3.2", "CSV / 图表", "验证理化特征是否提供显著增益；M4/M5 降级为选做"],
        ["D10", "独立测试集评估报告（AUC / AUPRC / MCC / 特异性，含 Bootstrap 置信区间）", "§5", "CSV / 文档", "所有指标为假设性参考，最终以此为准；DeLong 仅用于 AUROC，MCC 用配对 Bootstrap"],
        ["D11", "AMPSphere 实验测试集验证报告（100 条：79 阳性 + 21 阴性）", "§5", "CSV / 文档", "不使用 863,498 条计算发现候选肽作为实验阳性标签"],
        ["D12", "AD 三队列元数据核对报告（PRJNA798058/PRJNA489760/PRJNA679346）", "§4.2", "文档", "P0 必修，说明 164 vs 93 和 43 vs 106 的差异处理"],
        ["D13", "AD 宏基因组候选 AMP 筛选分析链（条件交付，P6）", "§4.3", "脚本 + 结果文档", "若已有组装和 ORF 数据，做完整样本级丰度分析；否则先完成一个发现队列，另外两个队列做元数据审计"],
        ["D14", "AD 与对照组差异分析初步结果（仅限已完成数据的队列，考虑混杂因素）", "§4.3", "文档", "暂不使用“五阶段 AD 分层”结论，不提前写差异结论"],
        ["D15", "input_sha256.tsv 及全部产出文件清单", "§8", "TSV", "用于数据完整性校验"],
    ],
    widths=[0.5, 3.0, 1.1, 0.8, 2.3],
)

doc.add_page_break()

# ================= §7 主要风险与应对策略（V3） =================
add_heading("§7 主要风险与应对策略（V3）", 1)
add_table(
    ["风险", "严重程度", "应对策略（V3 修正）"],
    [
        ["AD 队列分组错误：PRJNA798058 并非 NC/SCD/MCI/AD 四组；164 条记录不能直接认定为技术重复；PRJNA679346 43 vs 106 差异未核对", "很高", "暂不使用“五阶段 AD 分层分析”；先制作样本级元数据表，建立 Subject-BioSample-Experiment-Run 关系表，逐级核对"],
        ["AMP 分类结果不能直接等同于 AD 相关 AMP 差异，缺少样本级丰度定量", "很高", "执行 §4.3 完整分析链：reads 回贴（核苷酸参考） → 丰度定量 → 原始 counts 输入 DESeq2 → 标准化 → 混杂因素校正差异分析"],
        ["正负样本标签质量不足：数据库重复、MIC 阈值不一致、DRAMP 包含专利", "高", "跨数据库按序列去重；仅保留明确实验验证记录；记录 MIC 原始信息；DRAMP 不等同实验验证正样本数量"],
        ["训练数据与肠道细菌 AMP 存在领域偏移（动物来源占多数）", "高", "V3 新增细菌 AMP 专项数据层，单独报告细菌来源 AMP 测试结果，增强与肠道微生物组适配性"],
        ["同源泄漏导致指标虚高", "高", "全部序列统一去重聚类 + Group-based Split；明确 CD-HIT 覆盖率参数；外部验证集不参与模型选择"],
        ["50 个折统计检验不当（把 50 个折当 50 个独立观测）", "中高", "同一独立测试集上配对比较 + 按同源簇 Bootstrap 置信区间；DeLong 仅用于 AUROC，MCC 用配对 Bootstrap"],
        ["ESM-2 BOS/CLS 被错误用作全局特征", "中", "使用 Masked Mean Pooling，仅含真实氨基酸残基，不含 BOS/EOS/Padding"],
        ["Cross-Attention 单 Token 结构缺陷", "中", "主模型改为 Concat（128+64=192维）；真正多Token Cross-Attention 降级为选做 M4"],
        ["32 维生物物理特征强行凑齐、存在冗余", "中", "计算相关性矩阵，高度相关特征分组，比较保留/去除后性能，不强行凑齐 32 维；Aliphatic Index/Boman Index 公式已修正"],
        ["30 天交付承诺过高、P6 四天处理 0.78 TB 不现实", "很高", "P6 改为条件交付；所有性能指标改为“假设性参考”，最终以独立测试集为准"],
        ["AMPSphere 863,498 条不能全部当实验阳性标签", "中", "只使用原始研究 100 条体外测试肽（79 阳性 + 21 阴性）作为独立测试集"],
        ["细菌前体肽不等于成熟抗菌肽", "中", "增加成熟肽加工与基因簇注释二次分析（antiSMASH RiPP），作为候选肽生物学可信度的二次验证"],
    ],
    widths=[3.4, 1.0, 3.6],
)

doc.add_page_break()

# ================= §8 防 AI 协作冲突与命名规范 =================
add_heading("§8 防 AI 协作冲突与命名规范（与其他 AI 任务划清边界）", 1)
add_para("本计划严格执行“带时间戳新版、不覆盖历史、分工隔离、目录隔离”四项原则，避免与并行 AI 任务（HierMetaAMP 第二阴兵、隔壁农药残留课题、其他深度学习建模 AI）发生资源冲突或命名撞击：", size=10.5)

for item in [
    "【文件名加时间戳】所有新产出文件均按 `原文件名_V3_YYYYMMDD_HHMM.ext` 命名，绝不覆盖云盘内任何历史版本。",
    "【目录隔离】30天主线产出统一放入 `2026-11-09_DualAMP-Lite/` 子目录（dataset/ / features/ / baseline/ / model/ / ablation/ / figures/ / manuscript/ / demo/），与 HierMetaAMP、农药残留课题的目录物理隔离。",
    "【模型命名隔离】主模型权重统一命名 `best_dual_lite.pt` / `deepmetaamp_scripted.pt`；HierMetaAMP 系列若未来独立启动，另用 `hiermetaamp_*.pt` 命名空间，不混用。",
    "【数据源隔离】本计划仅使用 AD 肠道微生物组队列（PRJNA798058 等）与四大公开AMP库；不复用隔壁农药残留课题的数据，不与其模型权重或特征文件混淆。",
    "【接口预留，不抢资源】HierMetaAMP 的 LoRA 微调、层次化多任务、四大脑区菌落拓扑仅预留“多任务标签接口”预注释，30天内不分配 GPU 算力与人时，避免与“第二阴兵”抢资源。",
    "【AI 角色边界】本 AI 仅负责计划编写、代码骨架与结果归档总结；湿实验验证、动物实验、临床样本采集等由课题组另行安排，本计划不越界。",
]:
    add_bullet(item)

doc.add_page_break()

# ================= §9 附录：关键资源与代码骨架（V3 公式修正） =================
add_heading("§9 附录：关键资源与代码骨架要点（V3）", 1)
add_para("以下为可直接复制使用的关键外部资源与代码入口：", size=10.5)
add_table(
    ["资源", "说明 / 链接"],
    [
        ["APD6 抗菌肽数据库 (2026)", "https://aps.unmc.edu/AP/（替代过时的 APD3；官方 2024 年天然已知活性 AMP 下载集 3,306 条）"],
        ["DBAASP v3", "https://dbaasp.org/（MIC 与 HC50，单位换算依据）"],
        ["DRAMP 4.0 (NAR 2025)", "实验验证 AMP 库，但 30,260 条记录包含专利等，不等同实验验证正样本数量"],
        ["CAMPR4 (NAR 2023)", "实验验证 AMP 库"],
        ["AMPSphere (Cell 2024)", "Santos-Júnior et al. 全球微生物组 AMP 外部验证集；863,498 条为计算发现候选肽，不能全部当实验阳性标签"],
        ["GenPept-Curated-2025 (bioRxiv 2026)", "外部验证集，剔除 ampC/D/R/S β-内酰胺酶假阳性；11,000 条，2026 预印本，仅作补充基准"],
        ["AD 队列 PRJNA798058", "NCBI BioProject：43 名临床前 AD 生物标志物阳性认知正常个体 + 50 名认知正常对照者；164 个 BioSample/Experiment 记录与 93 名受试者对应关系尚待核验"],
        ["外部验证队列 PRJNA489760 / PRJNA679346", "需按样本类型筛选（粪便/血液）；PRJNA679346 43 份原研究样本与当前页面 106 条记录差异需逐一核对"],
        ["step1_build_dataset.py", "正负样本清洗与五层负样本构建（General/Bacterial/Negative Background/Hard Negative/Scrambled）+ 跨数据库去重、标签审核、MIC 元数据记录 + CD-HIT 去重 + Group-based Split"],
        ["step2_extract_features.py", "ESM-2 (esm2_t12_35M) 离线特征提取：残基级特征 + Masked Mean Pooling + 生物物理特征（Aliphatic Index 已修正，Boman Index 来源固定）+ StandardScaler（仅训练集拟合）"],
        ["step3_train_and_eval.py", "简化基线模型训练（M0-M3）+ 多尺度 1D-CNN 支路 + 消融实验（M3 vs M2）+ Group-based 交叉验证 + Bootstrap 置信区间 + M4/M5 选做"],
    ],
    widths=[2.8, 4.7],
)

doc.add_paragraph()
add_para("【V3 公式修正摘要】", bold=True, size=10)
add_para("1. Aliphatic Index：AI = X(Ala) + 2.9 × X(Val) + 3.9 × [X(Ile) + X(Leu)]（ExPASy ProtParam 标准，X 为摩尔百分比）", size=9.5)
add_para("2. Boman Index：固定自由能数值来源（APD 或 Peptides 包规则），明确单位与正负号约定，并通过已知序列交叉验证", size=9.5)
add_para("3. ESM-2 全局特征：Masked Mean Pooling，H_mean = (1/L) × Σ H_i，仅包含真实氨基酸残基，不含 BOS/EOS/Padding", size=9.5)
add_para("4. 主模型融合：Concat（ESM-2 CNN 128维 + 理化特征 MLP 64维 = 192维），不使用有缺陷的单 Token Cross-Attention", size=9.5)

doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("—— V3 最终执行版计划结束 ——")
r.italic = True
r.font.size = Pt(9.5)
r.font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)

doc.save(OUT_NAME)
print(f"Saved: {OUT_NAME}")