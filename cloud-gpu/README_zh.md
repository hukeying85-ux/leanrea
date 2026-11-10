# gpu-relay（临时，任务完成后删除）

用于在受限沙箱里借用 Kaggle / Colab 算力：凭据只存在私有 Google Drive 金库，
经 RSA 信封下发，运行日志与产物只写回私有 Drive，绝不进入本仓库（仓库为 public）。

- `scripts/`：私有技能包 `15_Colab与Kaggle云端算力Skills_持久登录_2026-11-08`
- `jobs/queue.json`：任务队列（push 本文件即触发中继）
- `jobs/uniprot_download.py`：本次任务——在 Kaggle 上重跑 UniProt 查询并回传 Drive

任务结束后 `git rm -rf cloud-gpu .github/workflows/gpu-relay.yml`。
