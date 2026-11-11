# DualAMP-Lite 交付总结（2026-11-10）

> 本文汇总本轮工作的**产物位置、数据核验、云端 GPU 链路、V4 流水线状态**与待办。
> 所有数字均为可复核的实测值；标注「demo」的一律不构成科学结论。

---

## 1. 一句话结论

| 事项 | 状态 |
|---|---|
| 原始数据下载（APD6 / DRAMP5 / BAGEL4 / UniProt） | ✅ 完成，主要数据集与官方/论文计数逐一核对一致 |
| UniProt（此前报「未下载成功」） | ✅ **实际早已下载完整**，并用 Kaggle 独立复现，逐字节一致 |
| 云端 GPU（Kaggle 2×T4） | ✅ 已连通并实跑，产物经私有 Drive 回传 |
| 云端 GPU（Colab） | ⚠️ 凭据有效但账户 0.00 compute units，暂不可用 |
| V4 可复现流水线 | ✅ 11 阶段跑通，D1–D20 = 20/20 `ok`，测试 87/87 |
| 真实 ESM-2 训练 | ⛔ 未开始（等阳性集审核 + 弱阴性截取定稿） |

---

## 2. Google Drive 交付位置

### 2.1 主交付目录 `DualAMP_Lite_原始数据_2026-11-10/`

```
DualAMP_Lite_原始数据_2026-11-10/
├── DualAMP_Lite_原始数据下载总结_2026-11-10.docx   ← 08:00Z 版（另有时间戳快照见 2.2）
├── manifests/           4 个清单（来源、SHA256×271、计数、版本）
└── raw/
    ├── APD6/            天然 3,306 + 细菌 410 + 来源说明
    ├── DRAMP5/          7 个 xlsx + commit 锁定 + README
    ├── Bacterial_AMP/   563 条细菌来源候选 + BAGEL4 提交号
    │   └── BAGEL4_reference/   class1/2/3、Lantibiotics、context
    └── UniProt/         查询式、版本、样例、下载脚本
        ├── download_20261110T064455Z/          06:44Z 原始下载（4 文件，未被改动）
        └── Kaggle_uniprot_20261110T070333Z/    07:03Z Kaggle 独立复现（5 文件）
```

### 2.2 独立快照目录（新建，防同名覆盖）

`DualAMP_Lite_UniProt补下_Kaggle_20261110T0818Z/`（My Drive 根目录）

```
README_说明.md
uniprot_bacteria_cytoplasm_reviewed.fasta.gz      27,721,477 B  md5 4f0bd8c8…2ed6
uniprot_bacteria_cytoplasm_reviewed.tsv.gz         3,704,283 B  md5 7830d540…4f75
uniprot_download_manifest_kaggle_20261110T0703Z.json
UniProt_Kaggle补下结果_20261110T0703Z.md
gpu_relay_report_uniprot_tsv_20261110T0703Z.json
DualAMP_Lite_原始数据下载总结_快照20261110T0800Z.docx
```

### 2.3 覆盖事件说明

主交付目录里的 `DualAMP_Lite_原始数据下载总结_2026-11-10.docx` 在 **08:00:21Z 被同名文件替换**
（id `1ih5loq…` → `16X8sVe…`，41,089 B → 40,687 B），属另一会话的重复写入，与 UniProt 上传无关
（`raw/UniProt/download_20261110T064455Z/` 下 4 个文件的 `modifiedTime` 仍等于 `createdTime`，未被触碰）。
08:00Z 版本已做时间戳快照存入 2.2 目录。

---

## 3. 数据核验

| 数据集 | 记录数 | 状态 |
|---|---|---|
| APD6 天然 AMP | 3,306 | ✅ 与官方首/尾记录逐条比对一致 |
| APD6 细菌 AMP | 410 | ✅ 410 个 APD ID 逐条重建；**仅作来源标签，不与天然集相加** |
| DRAMP 5.0 General / Patent | 12,784 / 18,715 | ✅ 与论文一致 |
| DRAMP5 其余 5 表 | 39,125 / 96 / 179 / 6,321 / 110 | ✅ |
| DRAMP5 细菌来源候选 | 563（A 类 276 显式 + B 类 287 属名） | ⚠️ 候选表，进正样本前需人工审核 |
| BAGEL4 参考 | class1 499 / class2 229 / class3 93 / Lantibiotics 3,567 / context 788 | ✅ 仅参考，不混入核心训练 |
| UniProt 细菌胞质（Swiss-Prot） | **117,172** 条（FASTA 与 TSV 一致） | ✅ Release 2026_04，两次独立下载逐字节一致 |

版本锁定：DRAMP 5.0 `e124e9d`，BAGEL4 `dcb961a`，APD6 APD2024a（官方 2026-01 更新），UniProt 2026_04。

### 3.1 UniProt 校验值

| 文件 | 字节 | md5 | sha256 |
|---|---|---|---|
| `…reviewed.fasta.gz` | 27,721,477 | `4f0bd8c89d14faec13d059441a742ed6` | `53edcd309eb1855b1c982ebf661216c8ca6fce287ae37045b0577e50e6cefb1a` |
| `…reviewed.tsv.gz` | 3,704,283 | `7830d5408bc15e2be943d448ffbc4f75` | `0f9b6bb2c818b36f6c2f697bac5b9d7edb06a178c5da619f34321dbdb92ec88b` |

查询式（快照锁定）：

```
(reviewed:true) AND (taxonomy_id:2) AND (cc_scl_term:SL-0086)
AND (length:[100 TO 5000]) AND (NOT ft_signal:*) AND (NOT ft_transmem:*)
```

获取端点 `https://rest.uniprot.org/uniprotkb/stream`（FASTA / TSV 均 `compressed=true`）。
本沙箱不通该域名，故下载在 **Kaggle 内核**执行；TSV 36.4 s 一次成功，FASTA 约 60 s。

---

## 4. 云端 GPU 链路

### 4.1 实测环境（Kaggle）

| 项 | 值 |
|---|---|
| GPU | 2 × Tesla T4，15,360 MiB / 卡 |
| torch | 2.11.0+cu130，CUDA 13.0，`device_count=2` |
| fair-esm | 2.0.0，`esm2_t12_35M_UR50D` 直接跑在 cuda |
| 前向 | 加载 1.54 s / 前向 0.747 s（8 条 AMP 序列） |
| embedding | 480 维、全部有限、最小成对余弦 0.684 |

### 4.2 Colab

ADC 凭据有效、scopes 完整、无活跃会话；账户 **0.00 compute units**，本阶段无法分配机器。

### 4.3 中继架构（用后即删）

```
私有 Drive 金库 vault.json（只读，绝不入库）
   → 一次性 RSA+AES 信封 cloud-gpu/secrets/*.enc（公钥由中继首次运行生成并提交）
   → git push 触发 GitHub Actions
   → 解密后在 runner 里调 kaggle / colab CLI
   → kernel 内产物走预授权 resumable URI 回写私有 Drive
```

每次运行后中继自动删除已消费的信封并提交；任务结束执行
`git rm -rf cloud-gpu .github/workflows/gpu-relay.yml`，仓库保持「零云凭据」。
参见 `dualamp-lite/docs/GPU_VALIDATION.md`、`dualamp-lite/docs/UNIPROT_DOWNLOAD.md`。

---

## 5. V4 流水线状态

- 入口：`dualamp-lite/run_pipeline.py --stage all`（`demo` 模式无需 torch / fair-esm）
- 模块：`dualamp_lite/v4/` 13 个（config / data / schema / split / features / qc / models /
  train / runs / evaluate / report / pipeline），V3 包级模块保留为 legacy
- 交付物：D1–D20 全量，报告内 20/20 `ok`；`SHA256/manifest_<run_id>.tsv`；`export/inference.py`、
  `MODEL_CARD.md`、`example.fasta`、`final_models/`
- 完整 demo 运行（mock 后端，**数字不可作为科学结论**）：11 阶段完成、`run_status.json` `complete: true`、
  125 个 `metrics.json`、清单 1,132 行；两次独立运行逐位一致
- 测试：`python -m unittest discover -s tests -t .` → **87 tests OK**

### 5.1 关键修复（本轮）

| 问题 | 处理 |
|---|---|
| bootstrap 内每轮都调 sklearn，evaluation 阶段卡死 >10 min | 改 numpy 计数实现，仅 AUROC/AUPRC 用 sklearn |
| `n_test` 被长表重复计数（460 = 5 seeds × 92） | 改 `sequence_id.nunique()` → 92 |
| 单阶段运行导致 D18/D19/D20 显示 `missing` | 以 `--stage all` 的 `run_status.json` 判定完整性 |
| 缺少权重指纹 | 新增 `features/esm_weights_sha256.tsv` |

---

## 6. 待办（按依赖顺序）

1. **阳性集审核**：DRAMP5 细菌来源 563 条候选（A 类 276 + B 类 287）逐条确认，剔除专利/预测条目。
2. **弱阴性截取**：用 UniProt 117,172 条做片段化 + keyword 过滤（排除 antimicrobial / bacteriocin / defensin），
   固定随机种子，产物落 `configs/sources.yaml` 引用的本地路径。
3. **真实 ESM-2 特征提取 + 25 折训练**：`scripts/run_v4.sh real`，Kaggle 2×T4；
   预计单次特征提取十几分钟量级，训练按 M1/M2/M3 × 5 seeds × 5 folds。
4. **论文/报告**：按第三版大纲填写，注明数据版本（DRAMP5 `e124e9d`、BAGEL4 `dcb961a`、UniProt 2026_04）
   与 SHA256 清单，明确 demo 数字不进入结果表。

---

## 7. 复现命令

```bash
# 测试
cd dualamp-lite && python -m unittest discover -s tests -t .        # 87 OK

# 管道自检（合成数据 + mock 编码器，勿当科学结果）
python run_pipeline.py --stage all --demo --epochs 20 --threads 2

# 真实运行（需先备好 configs/sources.yaml 指向的原始文件）
./scripts/run_v4.sh real
```

---

*本文由 Arena Agent 生成于 2026-11-10；数据核验以 Drive 中的 SHA256 清单为准。*
