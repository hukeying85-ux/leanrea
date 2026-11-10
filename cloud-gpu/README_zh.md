# gpu-relay（临时，GPU 任务完成后删除）

用途：把 Kaggle / Colab 凭据经私有 Google Drive 金库 → RSA 加密信封 → GitHub Actions
中继的方式使用，凭据与运行产物从不进入本仓库（仓库为 public）。

- `scripts/`：来自私有技能包 `15_Colab与Kaggle云端算力Skills_持久登录_2026-11-08`
- `jobs/queue.json`：任务队列（push 到本文件即触发中继）
- `relay_pubkey.pem`：中继首次运行后自动提交的公钥，用于加密信封

任务结束后按 SKILL.md 隐私规则：`git rm -rf cloud-gpu .github/workflows/gpu-relay.yml`。
