# Cloud-GPU + Kaggle AI ($10/day) Zero-Leak Relay

本目录提供沙盒受限网络环境下的 **Kaggle 双卡 GPU (`NvidiaTeslaT4` = 2×Tesla T4, 32 GB 显存)** 与 **Kaggle Benchmarks Model Proxy (`$10/day` 多模态 AI 额度)** 全自动零泄漏接力管线：

## 核心架构与隐私保证

1. **零明文隐私红线（适配 Public 仓库）**
   - 凭据（`KAGGLE_API_TOKEN`）、私有输入帧包（`PRIVATE_INPUTS_TAR_GZ`）与一次性 Google Drive 可续传上传会话 URI（`DRIVE_*_UPLOAD_URI`）均通过 `cloud-gpu/scripts/encrypt_secret.py` 进行 **RSA-4096-OAEP-SHA256 + AES-256-CBC + HMAC-SHA256** 混合信封加密（`cloud-gpu/secrets/*.enc`）。
   - `.github/workflows/gpu-relay.yml` 在内存盘中完成解密、将 `KAGGLE_API_TOKEN` 持久化于加密 Actions Cache（`~/.gpu-relay`），并**立即 `git rm` 销毁一次性信封**，从不将任何私人媒体、账号用户名、日志或产物写入 Git。

2. **Kaggle 双配额协同（GPU 配额 + `$10/day` AI 配额）**
   - **AI 额度层（0 秒 GPU 消耗）**：通过 `kaggle benchmarks auth -y` 自动签发短期 `MODEL_PROXY_URL` / `MODEL_PROXY_API_KEY`（支持 `google/gemini-3-flash-preview` 等多模态模型），执行渲染前参数规划与渲染后 5 帧时序条多模态选片。
   - **双卡 GPU 并行层（`2 × Tesla T4`）**：`cloud-gpu/scripts/kaggle_svd_ai_pipeline.py` 先单次拉取 `stabilityai/stable-video-diffusion-img2vid-xt` 纯 `fp16` 权重（约 4.6 GB），随后跨 `CUDA_VISIBLE_DEVICES=0` 与 `CUDA_VISIBLE_DEVICES=1` 双进程纯 FP16 直载显卡并行渲染多组候选片。
   - **本地终混对标封装**：`cloud-gpu/scripts/finalize_dog_replica.py` 将优选母片执行 Lanczos 几何对齐、双向块匹配运动补偿插帧（`minterpolate` 30 fps 精确帧数对齐）、`libx265` (`hvc1` / `bt709`) 重编码、原片 AAC 音轨逐比特流拷贝（`-c:a copy`），并输出左右并排逐帧对比视频与 5 帧时序对比表。

## 常用命令

```bash
# 1. 加密私有输入归档与一次性回传 URI
python3 cloud-gpu/scripts/encrypt_secret.py encrypt \
  --pubkey cloud-gpu/relay_pubkey.pem \
  --from-file /tmp/private_inputs.tar.gz \
  --out cloud-gpu/secrets/PRIVATE_INPUTS_TAR_GZ.enc

# 2. 入队 Kaggle 双卡 GPU + AI 任务
python3 cloud-gpu/scripts/gpu_ctl.py enqueue \
  --id i2v-dual-run \
  --provider kaggle \
  --mode run \
  --accelerator NvidiaTeslaT4 \
  --kernel-slug i2v-dual-gpu-runner \
  --script cloud-gpu/scripts/kaggle_svd_ai_pipeline.py \
  --script-args "--first-frame /tmp/first_frame.webp --source-strip /tmp/source_strip.jpg --out-dir /kaggle/working --steps 25 --max-candidates 4" \
  --timeout-sec 1080

# 3. 回传后本地 30fps 运动补偿插帧 + HEVC bt709 + 原片音轨封装 + 对比视频生成
.venv/bin/python cloud-gpu/scripts/finalize_dog_replica.py \
  --raw outputs/raw_best.mp4 \
  --source /path/to/source.mp4 \
  --out outputs/replica_final.mp4 \
  --compare outputs/replica_compare.mp4 \
  --sheet outputs/replica_sheet.jpg
```
