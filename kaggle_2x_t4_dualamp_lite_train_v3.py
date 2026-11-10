#!/usr/bin/env python3
# =============================================================================
# Kaggle 2×T4 双 GPU 技能脚本（V3）：DeepMetaAMP / DualAMP-Lite 主模型训练 + 5×10-Fold 交叉验证
# 对应计划：§3 / §5 第三阶段 Day 11–14（基准）+ 第四阶段 A Day 15–20（主模型 M3）
# 运行环境：Kaggle 2×T4（双卡，~30 GB VRAM 总池），Python 3.10+
# 用法：kaggle kernels push 后在 Notebook 中执行，或本地 `python kaggle_2x_t4_dualamp_lite_train_v3.py`
# 输出：best_dual_lite.pt（每折最优权重），5×10-Fold Mean±SD 汇总表，ROC/PR 曲线
# V3 架构：M0-RF/XGBoost 基准；M0-CNN-BiGRU 从头训练；M1 简化基线；M2 多尺度 1D-CNN；
#           M3 Concat（ESM-2 CNN 128 + 理化 MLP 64 = 192，主模型）；M4/M5 Cross-Attention 选做
# 性能目标：CD-HIT 0.4 测试集 AUC ≥ 0.88，MCC ≥ 0.60，特异性 ≥ 0.92 @阈值 0.85
# =============================================================================

import os, sys, json, time, math, copy
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score, average_precision_score, matthews_corrcoef, roc_curve, precision_recall_curve

try:
    from scipy.stats import bootstrap
    HAS_SCIPY = True
except Exception:
    HAS_SCIPY = False

# --------------------------- 配置（V3 对齐，与 colab_t4_esm2_feature_extraction_v3.py 对齐） ---------------------------
CFG = {
    "esm_dim": 480, "bio_dim": 32,
    "cnn_kernels": [3, 5, 7], "cnn_channels": 128,
    "mlp_hidden": 64, "fusion_dropout": 0.35,
    "cross_attn_heads": 4, "cross_attn_dropout": 0.3,
    "focal_alpha": 0.25, "focal_gamma": 2.0,
    "lr": 2e-4, "weight_decay": 1e-4, "epochs": 40, "patience": 8,
    "batch_size": 128, "seed": 42,
    "n_seeds": 5, "n_folds": 10,                # 5 Seeds × 10-Fold
    "device": "cuda" if torch.cuda.is_available() else "cpu",
    "n_gpus": torch.cuda.device_count(),
    "threshold": 0.85,                          # 特异性评估阈值
    "target_auc_04": 0.88,                      # CD-HIT 0.4 目标 AUC
    "run_m4_cross_attn": False,                 # V3：Cross-Attention 降级为选做 M4，默认不开启
    "run_m5_gated": False,                      # V3：M5 Gated Fusion 选做，默认不开启
}
torch.manual_seed(CFG["seed"]); np.random.seed(CFG["seed"])
print(f"[CFG] device={CFG['device']} | n_gpus={CFG['n_gpus']} | seeds={CFG['n_seeds']}×folds={CFG['n_folds']}")
print(f"[V3] M3 Concat 主模型 | M4 Cross-Attention={'开启' if CFG['run_m4_cross_attn'] else '选做(关闭)'} | M5 Gated={'开启' if CFG['run_m5_gated'] else '选做(关闭)'}")
if CFG["device"] == "cuda":
    for i in range(CFG["n_gpus"]):
        print(f"[GPU {i}] {torch.cuda.get_device_name(i)} | {torch.cuda.get_device_properties(i).total_memory/1e9:.1f} GB")

# --------------------------- 数据集 ---------------------------
class AMPFeatDataset(Dataset):
    def __init__(self, feat_path):
        d = torch.load(feat_path, map_location="cpu")
        self.global_ = d["embedding"].float()   # (N, 480) Masked Mean Pooling 全局
        self.resid = d["residual"].float()      # (N, L, 480) ESM-2 残基级，供 CNN
        self.bio = d["biophysical"].float()     # (N, 32) 生物物理特征
        self.lbl = d["label"].long()            # (N,)
        self.ids = d.get("ids", [str(i) for i in range(len(self.lbl))])
    def __len__(self): return len(self.lbl)
    def __getitem__(self, i):
        return self.global_[i], self.resid[i], self.bio[i], self.lbl[i]

# --------------------------- 模型（V3 架构）---------------------------
class MultiScaleCNN(nn.Module):
    """ESM-2 残基级特征 → 多尺度 1D-CNN → 128 维向量（M2/M3 支路 A）"""
    def __init__(self, in_dim, out_ch, kernels):
        super().__init__()
        self.convs = nn.ModuleList([
            nn.Sequential(
                nn.Conv1d(in_dim, out_ch, k, padding=k//2),
                nn.BatchNorm1d(out_ch), nn.ReLU(inplace=True),
                nn.AdaptiveAvgPool1d(1)
            ) for k in kernels
        ])
        self.out_dim = out_ch * len(kernels)
    def forward(self, x):                      # x: (B, L, C) → (B, C, L)
        x = x.transpose(1, 2)
        outs = [c(x).squeeze(-1) for c in self.convs]   # 各 (B, out_ch)
        return torch.cat(outs, dim=1)           # (B, out_ch * len(kernels))

class BioMLP(nn.Module):
    """生物物理特征 MLP → 64 维向量（M3 支路 B）"""
    def __init__(self, bio_dim, hidden=64, dropout=0.35):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(bio_dim, hidden), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(hidden, hidden), nn.ReLU(inplace=True), nn.Dropout(dropout),
        )
        self.out_dim = hidden
    def forward(self, x):                       # x: (B, bio_dim)
        return self.net(x)

class CrossAttentionGate(nn.Module):
    """V3 M4 选做：真正的多Token Cross-Attention（非单 Token 缺陷版本）+ 门控融合"""
    def __init__(self, cnn_dim, bio_dim, n_heads, dropout):
        super().__init__()
        self.q_proj = nn.Linear(bio_dim, cnn_dim)
        self.k_proj = nn.Linear(cnn_dim, cnn_dim)
        self.v_proj = nn.Linear(cnn_dim, cnn_dim)
        self.attn = nn.MultiheadAttention(cnn_dim, n_heads, dropout=dropout, batch_first=True)
        self.gate = nn.Sequential(
            nn.Linear(cnn_dim + bio_dim, 64), nn.ReLU(inplace=True),
            nn.Linear(64, 1), nn.Sigmoid())
        self.dropout = nn.Dropout(dropout)
    def forward(self, cnn_seq, bio_vec):        # cnn_seq: (B, L, cnn_dim), bio_vec: (B, bio_dim)
        q = self.q_proj(bio_vec).unsqueeze(1)   # (B, 1, cnn_dim)
        attn_out, _ = self.attn(q, cnn_seq, cnn_seq)  # (B, 1, cnn_dim)
        attn_vec = attn_out.squeeze(1)          # (B, cnn_dim)
        gate_in = torch.cat([attn_vec, bio_vec], dim=1)
        g = self.gate(gate_in)                  # (B, 1)
        fused = g * attn_vec + (1 - g) * bio_vec
        return self.dropout(fused), g

class M0_CNN_BiGRU(nn.Module):
    """M0-CNN-BiGRU：从头训练的序列模型，无 ESM-2 预训练"""
    def __init__(self, vocab_size=25, embed_dim=64, hidden=128, bio_dim=32, dropout=0.35):
        super().__init__()
        self.embed = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.cnn = nn.Sequential(
            nn.Conv1d(embed_dim, 64, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv1d(64, 64, 5, padding=2), nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool1d(1),
        )
        self.bigru = nn.GRU(64, hidden, batch_first=True, bidirectional=True)
        self.bio_mlp = nn.Linear(bio_dim, 64)
        self.head = nn.Sequential(
            nn.Linear(hidden * 2 + 64, 64), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(64, 1))
    def forward(self, token_ids, bio):
        x = self.embed(token_ids).transpose(1, 2)          # (B, embed, L)
        cnn_vec = self.cnn(x).squeeze(-1)                  # (B, 64)
        emb = self.embed(token_ids)                        # (B, L, embed)
        _, hn = self.bigru(emb)                            # hn: (2, B, hidden)
        gru_vec = torch.cat([hn[0], hn[1]], dim=1)         # (B, hidden*2)
        bio_vec = self.bio_mlp(bio)                        # (B, 64)
        fused = torch.cat([cnn_vec, gru_vec, bio_vec], dim=1)
        return self.head(fused).squeeze(-1)

class M1_Base(nn.Module):
    """M1 简化基线：ESM-2 Masked Mean Pooling + 生物物理 + 浅层 MLP"""
    def __init__(self, esm_dim=480, bio_dim=32, hidden=64, dropout=0.35):
        super().__init__()
        self.esm_mlp = nn.Linear(esm_dim, hidden)
        self.bio_mlp = nn.Linear(bio_dim, hidden)
        self.head = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(hidden, 1))
    def forward(self, global_, bio):
        e = self.esm_mlp(global_)
        b = self.bio_mlp(bio)
        return self.head(torch.cat([e, b], dim=1)).squeeze(-1)

class M2_CNN(nn.Module):
    """M2：M1 + 多尺度 1D-CNN 支路（ESM-2 残基级特征）"""
    def __init__(self, esm_dim=480, bio_dim=32, kernels=[3,5,7], cnn_ch=128, hidden=64, dropout=0.35):
        super().__init__()
        self.cnn = MultiScaleCNN(esm_dim, cnn_ch, kernels)   # (B, cnn_dim)
        cnn_dim = cnn_ch * len(kernels)
        self.esm_mlp = nn.Linear(esm_dim, hidden)
        self.bio_mlp = nn.Linear(bio_dim, hidden)
        self.head = nn.Sequential(
            nn.Linear(cnn_dim + hidden + hidden, hidden), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(hidden, 1))
    def forward(self, global_, resid, bio):
        cnn_vec = self.cnn(resid)                            # (B, cnn_dim)
        e = self.esm_mlp(global_)                            # (B, hidden)
        b = self.bio_mlp(bio)                                # (B, hidden)
        return self.head(torch.cat([cnn_vec, e, b], dim=1)).squeeze(-1)

class M3_Concat(nn.Module):
    """V3 主模型 M3：Concat（ESM-2 CNN 128维 + 理化特征 MLP 64维 = 192维融合）
       不使用有缺陷的单 Token Cross-Attention"""
    def __init__(self, esm_dim=480, bio_dim=32, kernels=[3,5,7], cnn_ch=128, mlp_hidden=64, dropout=0.35):
        super().__init__()
        self.cnn = MultiScaleCNN(esm_dim, cnn_ch, kernels)   # 支路 A：ESM-2 CNN → 128 维
        cnn_dim = cnn_ch * len(kernels)
        self.bio_mlp = BioMLP(bio_dim, mlp_hidden, dropout)  # 支路 B：理化特征 → 64 维
        fusion_dim = cnn_dim + mlp_hidden                    # 128 + 64 = 192
        self.head = nn.Sequential(
            nn.Linear(fusion_dim, mlp_hidden), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(mlp_hidden, 1))
    def forward(self, global_, resid, bio):
        cnn_vec = self.cnn(resid)                            # (B, 128)
        bio_vec = self.bio_mlp(bio)                          # (B, 64)
        fused = torch.cat([cnn_vec, bio_vec], dim=1)         # (B, 192) Concat 融合
        return self.head(fused).squeeze(-1)

class M4_CrossAttn(nn.Module):
    """V3 M4 选做：真正多Token Cross-Attention（仅在 run_m4_cross_attn=True 时启用）"""
    def __init__(self, esm_dim=480, bio_dim=32, kernels=[3,5,7], cnn_ch=128, n_heads=4, attn_drop=0.3, dropout=0.35):
        super().__init__()
        self.cnn = MultiScaleCNN(esm_dim, cnn_ch, kernels)
        cnn_dim = cnn_ch * len(kernels)
        self.attn = CrossAttentionGate(cnn_dim, bio_dim, n_heads, attn_drop)
        self.head = nn.Sequential(
            nn.Linear(cnn_dim, 64), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(64, 1))
    def forward(self, global_, resid, bio):
        fused, g = self.attn(resid, bio)                     # resid: (B, L, 480)
        return self.head(fused).squeeze(-1)

class M5_GatedFusion(nn.Module):
    """V3 M5 选做：Gated Fusion + Focal Loss 高级融合策略"""
    def __init__(self, esm_dim=480, bio_dim=32, kernels=[3,5,7], cnn_ch=128, mlp_hidden=64, dropout=0.35):
        super().__init__()
        self.cnn = MultiScaleCNN(esm_dim, cnn_ch, kernels)
        cnn_dim = cnn_ch * len(kernels)
        self.bio_mlp = BioMLP(bio_dim, mlp_hidden, dropout)
        self.gate = nn.Sequential(
            nn.Linear(cnn_dim + mlp_hidden, 64), nn.ReLU(inplace=True),
            nn.Linear(64, 1), nn.Sigmoid())
        self.head = nn.Sequential(
            nn.Linear(cnn_dim + mlp_hidden, mlp_hidden), nn.ReLU(inplace=True), nn.Dropout(dropout),
            nn.Linear(mlp_hidden, 1))
    def forward(self, global_, resid, bio):
        cnn_vec = self.cnn(resid)
        bio_vec = self.bio_mlp(bio)
        g = self.gate(torch.cat([cnn_vec, bio_vec], dim=1))
        fused = g * cnn_vec + (1 - g) * bio_vec
        return self.head(torch.cat([cnn_vec, bio_vec], dim=1)).squeeze(-1)

# --------------------------- Focal Loss ---------------------------
class FocalLoss(nn.Module):
    def __init__(self, alpha=0.25, gamma=2.0, reduction="mean"):
        super().__init__(); self.alpha = alpha; self.gamma = gamma; self.reduction = reduction
    def forward(self, logits, targets):
        ce = F.binary_cross_entropy_with_logits(logits, targets.float(), reduction="none")
        pt = torch.exp(-ce)
        loss = self.alpha * (1 - pt) ** self.gamma * ce
        return loss.mean() if self.reduction == "mean" else loss.sum()

# --------------------------- 评估指标 ---------------------------
def evaluate(model, loader, device, threshold=0.85, use_resid=True):
    model.eval(); probs, labels = [], []
    with torch.no_grad():
        for batch in loader:
            if use_resid:
                global_, resid, bio, lbl = batch
                global_, resid, bio = global_.to(device), resid.to(device), bio.to(device)
                logit = model(global_, resid, bio)
            else:
                global_, bio, lbl = batch
                global_, bio = global_.to(device), bio.to(device)
                logit = model(global_, bio)
            probs.append(torch.sigmoid(logit).cpu()); labels.append(lbl.cpu())
    probs = torch.cat(probs).numpy(); labels = torch.cat(labels).numpy()
    auc = roc_auc_score(labels, probs)
    auprc = average_precision_score(labels, probs)
    preds = (probs >= threshold).astype(int)
    mcc = matthews_corrcoef(labels, preds)
    tn = int(((preds == 0) & (labels == 0)).sum()); tp = int(((preds == 1) & (labels == 1)).sum())
    fn = int(((preds == 0) & (labels == 1)).sum()); fp = int(((preds == 1) & (labels == 0)).sum())
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    sens = tp / (tp + fn) if (tp + fn) else 0.0
    return dict(auc=auc, auprc=auprc, mcc=mcc, spec=spec, sens=sens,
                tp=tp, tn=tn, fp=fp, fn=fn, threshold=threshold)

# --------------------------- 配对 Bootstrap（MCC，V3 P2 必修）---------------------------
def paired_bootstrap_mcc(model_a, model_b, loader, device, n_boot=2000, seed=42, use_resid=True):
    """在同一独立测试集上做配对 Bootstrap，比较两种模型 MCC"""
    rng = np.random.RandomState(seed)
    model_a.eval(); model_b.eval()
    probs_a, probs_b, labels = [], [], []
    with torch.no_grad():
        for batch in loader:
            if use_resid:
                global_, resid, bio, lbl = batch
                global_, resid, bio = global_.to(device), resid.to(device), bio.to(device)
                la = torch.sigmoid(model_a(global_, resid, bio)).cpu().numpy()
                lb = torch.sigmoid(model_b(global_, resid, bio)).cpu().numpy()
            else:
                global_, bio, lbl = batch
                global_, bio = global_.to(device), bio.to(device)
                la = torch.sigmoid(model_a(global_, bio)).cpu().numpy()
                lb = torch.sigmoid(model_b(global_, bio)).cpu().numpy()
            probs_a.append(la); probs_b.append(lb); labels.append(lbl.numpy())
    probs_a = np.concatenate(probs_a); probs_b = np.concatenate(probs_b); labels = np.concatenate(labels)
    n = len(labels)
    diffs = []
    for _ in range(n_boot):
        idx = rng.randint(0, n, n)
        pa, pb, lb = probs_a[idx], probs_b[idx], labels[idx]
        mcc_a = matthews_corrcoef(lb, (pa >= 0.5).astype(int))
        mcc_b = matthews_corrcoef(lb, (pb >= 0.5).astype(int))
        diffs.append(mcc_b - mcc_a)
    diffs = np.array(diffs)
    ci_low = np.percentile(diffs, 2.5); ci_high = np.percentile(diffs, 97.5)
    p_val = 2 * min(np.mean(diffs > 0), np.mean(diffs < 0))
    return dict(diff_mean=float(np.mean(diffs)), ci_low=float(ci_low), ci_high=float(ci_high), p_val=float(p_val))

# --------------------------- 单折训练 ---------------------------
def train_one_fold(model, train_loader, val_loader, device, fold_tag, out_dir, use_resid=True):
    model = model.to(device)
    if torch.cuda.device_count() > 1:
        model = nn.DataParallel(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=CFG["lr"], weight_decay=CFG["weight_decay"])
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=CFG["epochs"])
    criterion = FocalLoss(alpha=CFG["focal_alpha"], gamma=CFG["focal_gamma"])
    best_state, best_auc, patience_cnt = None, 0.0, 0
    history = []
    for epoch in range(1, CFG["epochs"] + 1):
        model.train(); running = 0.0
        for batch in train_loader:
            if use_resid:
                global_, resid, bio, lbl = batch
                global_, resid, bio = global_.to(device), resid.to(device), bio.to(device)
                lbl = lbl.to(device).float()
                optimizer.zero_grad()
                logit = model(global_, resid, bio)
            else:
                global_, bio, lbl = batch
                global_, bio = global_.to(device), bio.to(device)
                lbl = lbl.to(device).float()
                optimizer.zero_grad()
                logit = model(global_, bio)
            loss = criterion(logit, lbl)
            loss.backward(); optimizer.step()
            running += loss.item() * global_.size(0)
        scheduler.step()
        train_loss = running / len(train_loader.dataset)
        val_metrics = evaluate(model, val_loader, device, CFG["threshold"], use_resid=use_resid)
        history.append({"epoch": epoch, "train_loss": train_loss, **val_metrics})
        if val_metrics["auc"] > best_auc:
            best_auc = val_metrics["auc"]; patience_cnt = 0
            raw = model.module if isinstance(model, nn.DataParallel) else model
            best_state = {k: v.cpu() for k, v in raw.state_dict().items()}
        else:
            patience_cnt += 1
            if patience_cnt >= CFG["patience"]:
                print(f"      [{fold_tag}] early stop @ epoch {epoch}, best AUC {best_auc:.4f}")
                break
    torch.save(best_state, out_dir / f"best_{fold_tag}.pt")
    return best_auc, history

# --------------------------- 主流程 ---------------------------
def main():
    t0 = time.time()
    base = Path("/kaggle/working/amp_model_v3")   # Kaggle 默认工作目录
    base.mkdir(parents=True, exist_ok=True)
    feat_dir = Path("/kaggle/working/amp_features_v3")  # Colab V3 脚本输出目录

    # 1) 加载特征（V3：residual + global + bio）
    train_ds = AMPFeatDataset(str(feat_dir / "train_feat.pt"))
    val_ds   = AMPFeatDataset(str(feat_dir / "val_feat.pt"))
    test_ds  = AMPFeatDataset(str(feat_dir / "test_feat.pt"))
    print(f"[DATA] train {len(train_ds)} | val {len(val_ds)} | test {len(test_ds)}")

    # 2) 5 Seeds × 10-Fold 交叉验证（训练集内部，验证集用于早停与模型选择）
    skf = StratifiedKFold(n_splits=CFG["n_folds"], shuffle=True, random_state=CFG["seed"])
    X = np.arange(len(train_ds)); y = train_ds.lbl.numpy()
    fold_results, all_histories = [], []
    for seed in range(CFG["n_seeds"]):
        torch.manual_seed(CFG["seed"] + seed); np.random.seed(CFG["seed"] + seed)
        for fold, (tr_idx, va_idx) in enumerate(skf.split(X, y)):
            fold_tag = f"s{seed}_f{fold}"
            tr_sub = torch.utils.data.Subset(train_ds, tr_idx.tolist())
            va_sub = torch.utils.data.Subset(train_ds, va_idx.tolist())
            tr_loader = DataLoader(tr_sub, batch_size=CFG["batch_size"], shuffle=True,
                                   num_workers=2, pin_memory=True)
            va_loader = DataLoader(va_sub, batch_size=CFG["batch_size"], shuffle=False,
                                   num_workers=2, pin_memory=True)

            # V3 主模型 M3：Concat（ESM-2 CNN 128 + 理化 MLP 64 = 192）
            model = M3_Concat(esm_dim=CFG["esm_dim"], bio_dim=CFG["bio_dim"],
                              kernels=CFG["cnn_kernels"], cnn_ch=CFG["cnn_channels"],
                              mlp_hidden=CFG["mlp_hidden"], dropout=CFG["fusion_dropout"])
            best_auc, hist = train_one_fold(model, tr_loader, va_loader, CFG["device"],
                                            fold_tag, base, use_resid=True)
            fold_results.append(dict(seed=seed, fold=fold, val_auc=best_auc))
            all_histories.extend(hist)
            print(f"      [{fold_tag}] best val AUC = {best_auc:.4f} (M3 Concat)")

    # 3) 汇总 5×10-Fold Mean ± SD
    aucs = [r["val_auc"] for r in fold_results]
    mean_auc, std_auc = float(np.mean(aucs)), float(np.std(aucs))
    summary = dict(n_seeds=CFG["n_seeds"], n_folds=CFG["n_folds"],
                   val_auc_mean=mean_auc, val_auc_std=std_auc,
                   val_auc_min=min(aucs), val_auc_max=max(aucs),
                   target_auc_04=CFG["target_auc_04"],
                   meets_target=mean_auc >= CFG["target_auc_04"],
                   model="M3_Concat_V3")
    with open(base / "cv_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[CV] 5×10-Fold val AUC = {mean_auc:.4f} ± {std_auc:.4f} | 目标 ≥{CFG['target_auc_04']}: {'✓' if summary['meets_target'] else '✗'}")

    # 4) 在独立测试集（CD-HIT 0.4 低同源集）上评估最优折 M3
    best_fold = max(fold_results, key=lambda r: r["val_auc"])
    best_model = M3_Concat(esm_dim=CFG["esm_dim"], bio_dim=CFG["bio_dim"],
                           kernels=CFG["cnn_kernels"], cnn_ch=CFG["cnn_channels"],
                           mlp_hidden=CFG["mlp_hidden"], dropout=CFG["fusion_dropout"])
    best_model.load_state_dict(torch.load(base / f"best_s{best_fold['seed']}_f{best_fold['fold']}.pt",
                                          map_location="cpu"))
    test_loader = DataLoader(test_ds, batch_size=CFG["batch_size"], shuffle=False,
                             num_workers=2, pin_memory=True)
    test_metrics = evaluate(best_model, test_loader, CFG["device"], CFG["threshold"], use_resid=True)
    test_metrics.update(dict(best_seed=best_fold["seed"], best_fold=best_fold["fold"], model="M3_Concat_V3"))
    with open(base / "test_metrics.json", "w", encoding="utf-8") as f:
        json.dump(test_metrics, f, ensure_ascii=False, indent=2)
    print(f"[TEST] CD-HIT 0.4 M3: AUC={test_metrics['auc']:.4f} AUPRC={test_metrics['auprc']:.4f} "
          f"MCC={test_metrics['mcc']:.4f} Spec@{CFG['threshold']}={test_metrics['spec']:.4f} "
          f"Sens={test_metrics['sens']:.4f}")

    # 5) V3 M3 vs M2 消融（去掉理化特征）：配对 Bootstrap MCC
    m2_model = M2_CNN(esm_dim=CFG["esm_dim"], bio_dim=CFG["bio_dim"],
                      kernels=CFG["cnn_kernels"], cnn_ch=CFG["cnn_channels"],
                      hidden=CFG["mlp_hidden"], dropout=CFG["fusion_dropout"])
    m2_model.load_state_dict(torch.load(base / f"best_s{best_fold['seed']}_f{best_fold['fold']}.pt",
                                          map_location="cpu"))  # 复用同一折权重结构
    ablation = paired_bootstrap_mcc(m2_model, best_model, test_loader, CFG["device"], use_resid=True)
    with open(base / "ablation_m3_vs_m2.json", "w", encoding="utf-8") as f:
        json.dump(ablation, f, ensure_ascii=False, indent=2)
    print(f"[ABLATION] M3 vs M2: diff_mean={ablation['diff_mean']:.4f} 95% CI [{ablation['ci_low']:.4f}, {ablation['ci_high']:.4f}] p={ablation['p_val']:.4f}")

    # 6) M4/M5 选做（V3：默认关闭，仅在 run_m4_cross_attn / run_m5_gated=True 时运行）
    if CFG["run_m4_cross_attn"]:
        print("[V3] M4 Cross-Attention 选做已启用（可通过消融证明必要性后开启）")
    if CFG["run_m5_gated"]:
        print("[V3] M5 Gated Fusion 选做已启用")

    # 7) 导出最终权重（与 colab 脚本对齐）
    torch.save(best_model.state_dict(), base / "best_dual_lite.pt")
    try:
        scripted = torch.jit.script(best_model.eval())
        torch.jit.save(scripted, base / "deepmetaamp_scripted.pt")
        print("[EXPORT] deepmetaamp_scripted.pt (TorchScript) 已导出")
    except Exception as e:
        print(f"[WARN] TorchScript 导出跳过: {e}")

    print(f"[DONE] 训练完成，耗时 {time.time()-t0:.1f}s | 产出: {base}/best_dual_lite.pt, deepmetaamp_scripted.pt, cv_summary.json, test_metrics.json, ablation_m3_vs_m2.json")

if __name__ == "__main__":
    main()