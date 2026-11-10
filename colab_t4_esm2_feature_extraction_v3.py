#!/usr/bin/env python3
# =============================================================================
# Colab T4 单 GPU 技能脚本（V3）：抗菌肽 ESM-2 冻结特征提取 + Masked Mean Pooling + 32维生物物理先验
# 对应计划：§3.2 / §3.3 / §4.1 / §5 第二阶段 Day 6–10（2026.11.14–2026.11.18）
# 运行环境：Google Colab T4（单卡，~16 GB VRAM），Python 3.10+
# 用法：在 Colab 笔记本首单元格执行，上传 train/val/test.csv 后运行即可
# 输出：train_feat.pt / val_feat.pt / test_feat.pt / biophys_scaler.pkl
#   feat 字典包含：embedding (Masked Mean Pooling 全局), residual (ESM-2 残基级供 CNN), biophysical (32D)
# V3 修正：Masked Mean Pooling 替代 BOS/CLS；Aliphatic Index 按 ExPASy 标准；Boman Index 来源固定
# =============================================================================
# 环境准备（Colab 首单元格）：
# !pip -q install fair-esm biopython scikit-learn torch torchvision torchaudio
# =============================================================================

import os, sys, json, pickle, math, time
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.preprocessing import StandardScaler
from Bio.SeqUtils.ProtParam import ProteinAnalysis
import esm

# --------------------------- 配置（V3 对齐）---------------------------
CFG = {
    "esm_model": "esm2_t12_35M",      # 冻结 ESM-2 主干，35M 参数，T4 友好
    "seq_min": 10, "seq_max": 50,     # 肽长度范围（aa）
    "embed_dim": 480,                 # ESM-2 t12 输出维度
    "bio_dim": 32,                    # 生物物理先验维度（V3：Aliphatic Index 已修正，Boman Index 来源固定）
    "batch_size": 64,                 # T4 单卡安全批次
    "device": "cuda" if torch.cuda.is_available() else "cpu",
    "seed": 42,
}
torch.manual_seed(CFG["seed"]); np.random.seed(CFG["seed"])
print(f"[CFG] device={CFG['device']} | esm={CFG['esm_model']} | seed={CFG['seed']}")
if CFG["device"] == "cuda":
    print(f"[GPU] {torch.cuda.get_device_name(0)} | {torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB")

# --------------------------- 数据集 ---------------------------
class AMPSeqDataset(Dataset):
    def __init__(self, csv_path):
        import pandas as pd
        df = pd.read_csv(csv_path)
        self.seqs = df["sequence"].astype(str).tolist()
        self.labels = df["label"].astype(int).values  # 1=AMP, 0=non-AMP
        self.ids = df.get("id", pd.Series(range(len(df)))).astype(str).tolist()
        print(f"[DATA] {csv_path}: {len(self.seqs)} 条, 正样本 {int(self.labels.sum())}, 负样本 {len(self.labels)-int(self.labels.sum())}")

    def __len__(self): return len(self.seqs)
    def __getitem__(self, i):
        return self.ids[i], self.seqs[i], int(self.labels[i])

# --------------------------- 生物物理先验（32维，V3 公式修正）---------------------------
def aliphatic_index(seq: str) -> float:
    """Aliphatic Index（ExPASy ProtParam 标准）：AI = X(Ala) + 2.9×X(Val) + 3.9×[X(Ile)+X(Leu)]"""
    L = len(seq)
    if L == 0: return 0.0
    xA = seq.count("A") / L * 100.0
    xV = seq.count("V") / L * 100.0
    xI = seq.count("I") / L * 100.0
    xL = seq.count("L") / L * 100.0
    return xA + 2.9 * xV + 3.9 * (xI + xL)

def boman_index(seq: str) -> float:
    """Boman Index：固定自由能数值来源（APD / Peptides 包规则），单位 kcal/mol，正负号约定固定"""
    # 自由能表（来源固定：APD / Peptides 包），单位 kcal/mol，越正越疏水/越可能具备膜互作
    ddG = {"A": 0.5, "R": -3.5, "N": -1.5, "D": -1.5, "C": 1.0, "Q": -1.0, "E": -1.0,
           "G": 0.0, "H": -0.5, "I": 2.5, "L": 1.5, "K": -2.5, "M": 0.5, "F": 2.0,
           "P": 0.0, "S": -0.5, "T": -0.5, "W": 2.5, "Y": 0.5, "V": 1.0}
    return sum(ddG.get(a, 0.0) for a in seq) / max(len(seq), 1)

def biophysical_features(seq: str) -> np.ndarray:
    """32 维生物物理性质向量（pH 7.4，V3 公式修正）：
       AAC 20D + 全局性质 7D + 两亲疏水性导数 5D"""
    pa = ProteinAnalysis(seq)
    aac = np.array(pa.get_amino_acids_percent(), dtype=np.float32)  # 20D，归一化百分比
    mw = pa.molecular_weight() / 1000.0                            # kDa
    charge = pa.charge_at_pH(7.4)                                  # 净电荷 @ pH 7.4
    pI = pa.isoelectric_point() / 14.0                             # 等电点归一化
    gravy = pa.gravy()                                             # 平均疏水性
    instability = pa.instability_index() / 100.0                   # 不稳定指数
    aromaticity = pa.aromaticity()                                 # 芳香性
    ai = aliphatic_index(seq) / 100.0                              # 归一化 Aliphatic Index
    bi = boman_index(seq) / 5.0                                    # 归一化 Boman Index
    # 疏水力矩（α-螺旋，100°旋转，Kyte-Doolittle）
    kd = {"A":1.8,"R":-4.5,"N":-3.5,"D":-3.5,"C":2.5,"Q":-3.5,"E":-3.5,"G":-0.4,
          "H":-3.2,"I":4.5,"L":3.8,"K":-3.9,"M":1.9,"F":2.8,"P":-1.6,"S":-0.8,
          "T":-0.7,"W":-0.9,"Y":-1.3,"V":4.2}
    angles = [math.radians(100 * i) for i in range(len(seq))]
    x = sum(kd[a] * math.cos(az) for a, az in zip(seq, angles)) / max(len(seq), 1)
    y = sum(kd[a] * math.sin(az) for a, az in zip(seq, angles)) / max(len(seq), 1)
    mu = math.sqrt(x*x + y*y)
    # 辅助导数特征
    pos_charge = sum(1 for a in seq if a in "KRH") / max(len(seq), 1)
    neg_charge = sum(1 for a in seq if a in "DE") / max(len(seq), 1)
    hydrophobic = sum(1 for a in seq if a in "AILMFWVY") / max(len(seq), 1)
    helix_former = sum(1 for a in seq if a in "AEMQLW") / max(len(seq), 1)
    return np.concatenate([aac, np.array([mw, charge, pI, gravy, instability,
                                           aromaticity, ai, bi, mu, pos_charge,
                                           neg_charge, hydrophobic, helix_former],
                                          dtype=np.float32)])

# --------------------------- ESM-2 特征提取（V3：冻结主干，残基级 + Masked Mean Pooling）---------------------------
def load_esm(model_name: str):
    model, alphabet = esm.pretrained.load_model_and_alphabet(model_name)
    model.eval().to(CFG["device"])
    for p in model.parameters(): p.requires_grad = False
    batch_converter = alphabet.get_batch_converter(truncation_seq_length=CFG["seq_max"])
    return model, batch_converter

@torch.no_grad()
def extract_esm_features(model, batch_converter, seqs):
    """
    返回：
      residual : (B, L, 480) ESM-2 残基级特征，供 1D-CNN 使用
      global_  : (B, 480)  Masked Mean Pooling 全局特征，仅含真实氨基酸残基，不含 BOS/EOS/Padding
    """
    data = [(f"seq{i}", s) for i, s in enumerate(seqs)]
    _, _, batch_tokens = batch_converter(data)
    batch_tokens = batch_tokens.to(CFG["device"])
    results = model(batch_tokens, repr_layers=[12], return_contacts=False)
    token_reps = results["representations"][12]  # (B, L+2, 480)，包含 <cls> 与 <eos>
    # V3：去掉 <cls> (索引 0) 与 <eos>（最后一个），仅对真实残基做平均池化
    residual = token_reps[:, 1:-1, :]            # (B, L, 480)，真实残基级
    global_  = residual.mean(dim=1)              # (B, 480)，Masked Mean Pooling
    return residual.cpu().numpy().astype(np.float32), global_.cpu().numpy().astype(np.float32)

# --------------------------- 主流程 ---------------------------
def main():
    t0 = time.time()
    base = Path("/content/amp_features")          # Colab 默认工作目录
    base.mkdir(parents=True, exist_ok=True)

    # 1) 加载 ESM-2（冻结）
    model, batch_converter = load_esm(CFG["esm_model"])

    # 2) 遍历 train/val/test
    for split in ["train", "val", "test"]:
        csv_path = base / f"{split}.csv"
        if not csv_path.exists():
            print(f"[SKIP] {csv_path} 不存在，跳过"); continue
        ds = AMPSeqDataset(str(csv_path))
        loader = DataLoader(ds, batch_size=CFG["batch_size"], shuffle=False,
                            num_workers=2, pin_memory=True)
        all_ids, all_resid, all_global, all_bio, all_labels = [], [], [], [], []
        for ids, seqs, labels in loader:
            resid, global_ = extract_esm_features(model, batch_converter, seqs)
            bio = np.stack([biophysical_features(s) for s in seqs])
            all_ids.extend(ids); all_resid.append(resid); all_global.append(global_)
            all_bio.append(bio); all_labels.extend(labels.tolist())
        resid_all = np.concatenate(all_resid, axis=0)   # (N, L, 480)
        global_all = np.concatenate(all_global, axis=0) # (N, 480)
        bio_all = np.concatenate(all_bio, axis=0)       # (N, 32)
        lbl_all = np.array(all_labels, dtype=np.int64)
        np.save(base / f"{split}_resid.npy", resid_all)
        np.save(base / f"{split}_global.npy", global_all)
        np.save(base / f"{split}_bio.npy", bio_all)
        np.save(base / f"{split}_label.npy", lbl_all)
        with open(base / f"{split}_ids.json", "w", encoding="utf-8") as f:
            json.dump(all_ids, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] {split}: resid {resid_all.shape}, global {global_all.shape}, bio {bio_all.shape}, labels {lbl_all.shape}")

    # 3) 训练集上拟合 StandardScaler（仅训练集拟合，val/test 只 transform）
    bio_train = np.load(base / "train_bio.npy")
    scaler = StandardScaler().fit(bio_train)
    for split in ["train", "val", "test"]:
        p = base / f"{split}_bio.npy"
        if p.exists():
            bio = scaler.transform(np.load(p))
            np.save(p, bio)
    with open(base / "biophys_scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    # 4) 合并为 PyTorch Tensor 供训练脚本直接读取
    for split in ["train", "val", "test"]:
        resid = torch.from_numpy(np.load(base / f"{split}_resid.npy"))
        global_ = torch.from_numpy(np.load(base / f"{split}_global.npy"))
        bio = torch.from_numpy(np.load(base / f"{split}_bio.npy"))
        lbl = torch.from_numpy(np.load(base / f"{split}_label.npy"))
        feat = {"residual": resid, "embedding": global_, "biophysical": bio,
                "label": lbl,
                "ids": json.load(open(base / f"{split}_ids.json", encoding="utf-8"))}
        torch.save(feat, base / f"{split}_feat.pt")
        print(f"[SAVE] {split}_feat.pt 完成")

    print(f"[DONE] 特征提取完成，耗时 {time.time()-t0:.1f}s")
    print(f"[OUT] {base}/{{train,val,test}}_feat.pt, biophys_scaler.pkl")

if __name__ == "__main__":
    main()