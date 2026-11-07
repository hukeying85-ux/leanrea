# 这里放用 relay_pubkey.pem 加密的一次性密文（*.enc，base64）。
# 例：DRIVE_UPLOAD_URI__6a4be129.enc → runner 解密成环境变量 DRIVE_UPLOAD_URI__6a4be129，
#    对应 note_id 以 6a4be129 开头的任务，把无水印原片视频直传到 Google Drive。用过即删。
