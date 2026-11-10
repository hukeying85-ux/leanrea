#!/usr/bin/env python3
"""
motion_photo.py —— 把「静态壁纸 + 循环短片」打包成手机认得的动态照片格式

  android  Google / Samsung「动态照片 (Motion Photo)」：一个 JPG 里带着 MP4（XMP GCamera:MicroVideo + Container:Directory），
           相册里长按会动；Samsung One UI / Pixel 可以直接「设为锁屏壁纸」变成动态锁屏。纯 Python，不依赖 exiv2。
           格式细节同 mihir-io/MotionPhotoMuxer：JPG 末尾直接拼 MP4，XMP 里写视频长度（从文件尾倒数的偏移）。
  ios      iPhone「实况照片 (Live Photo)」= 一张 JPG + 一段 MOV，靠同一个 ContentIdentifier 配对：
           MOV 用 ffmpeg 写 com.apple.quicktime.content.identifier（这一半稳）；JPG 需要 MakerNotes:ContentIdentifier，
           而 exiftool 不能给非 iPhone 照片从零造 Apple MakerNotes → 这一半在沙箱里写不进去（脚本会如实打印）。
           所以 iOS 的落地路径是：把 MP4/MOV 交给 intoLive（App Store，免费）或 RhetTbull/makelive（Mac）生成实况照片，
           再在 iPhone 上设为锁屏（iOS 17+ 支持实况壁纸）。本脚本的 ios 模式只负责把配对用的 MOV + JPG 准备好。

用法：
  python3 scripts/motion_photo.py android IMG.png CLIP.mp4 --out OUT_DIR        # → OUT_DIR/<name>.MP.jpg
  python3 scripts/motion_photo.py ios     IMG.png CLIP.mp4 --out OUT_DIR        # → OUT_DIR/<name>.JPG + <name>.MOV
  [--exiftool PATH]（默认 ~/exiftool/exiftool，沙箱里 git clone https://github.com/exiftool/exiftool 即可，纯 Perl）
"""
import argparse, os, shutil, subprocess, sys, uuid
import cv2

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # noqa: BLE001
    FFMPEG = "ffmpeg"

XMP = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>'
       '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       '<rdf:Description rdf:about="" xmlns:GCamera="http://ns.google.com/photos/1.0/camera/" '
       'xmlns:Container="http://ns.google.com/photos/1.0/container/" xmlns:Item="http://ns.google.com/photos/1.0/container/item/" '
       'GCamera:MicroVideo="1" GCamera:MicroVideoVersion="1" GCamera:MicroVideoOffset="{n}" GCamera:MicroVideoPresentationTimestampUs="0" '
       'GCamera:MotionPhoto="1" GCamera:MotionPhotoVersion="1" GCamera:MotionPhotoPresentationTimestampUs="0">'
       '<Container:Directory><rdf:Seq>'
       '<rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="image/jpeg" Item:Semantic="Primary" Item:Length="0" Item:Padding="0"/></rdf:li>'
       '<rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="video/mp4" Item:Semantic="MotionPhoto" Item:Length="{n}" Item:Padding="0"/></rdf:li>'
       '</rdf:Seq></Container:Directory></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')


def to_jpeg(img_path, out_path, quality=93):
    im = cv2.imread(img_path, cv2.IMREAD_COLOR)
    cv2.imwrite(out_path, im, [cv2.IMWRITE_JPEG_QUALITY, quality])


def insert_app1_xmp(jpeg_bytes, xmp_str):
    """在 SOI 之后（若有 APP0/EXIF 则在它们之后）插入 XMP APP1 段。"""
    assert jpeg_bytes[:2] == b"\xff\xd8", "不是 JPEG"
    pos = 2
    while pos + 4 <= len(jpeg_bytes) and jpeg_bytes[pos] == 0xFF and jpeg_bytes[pos + 1] in (0xE0, 0xE1):
        seglen = int.from_bytes(jpeg_bytes[pos + 2:pos + 4], "big")
        pos += 2 + seglen
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp_str.encode("utf-8")
    seg = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    return jpeg_bytes[:pos] + seg + jpeg_bytes[pos:]


def android(img, clip, out_dir, name):
    tmp = os.path.join(out_dir, name + ".tmp.jpg")
    to_jpeg(img, tmp)
    with open(tmp, "rb") as f:
        jpg = f.read()
    os.remove(tmp)
    with open(clip, "rb") as f:
        mp4 = f.read()
    out = os.path.join(out_dir, name + ".MP.jpg")
    with open(out, "wb") as f:
        f.write(insert_app1_xmp(jpg, XMP.format(n=len(mp4))) + mp4)
    print("[android]", out, f"{os.path.getsize(out)//1024} KB (jpg {len(jpg)//1024} + mp4 {len(mp4)//1024})")
    return out


def ios(img, clip, out_dir, name, exiftool):
    cid = str(uuid.uuid4()).upper()
    jpg = os.path.join(out_dir, name + ".JPG")
    mov = os.path.join(out_dir, name + ".MOV")
    to_jpeg(img, jpg)
    if not (exiftool and os.path.exists(exiftool)):
        exiftool = shutil.which("exiftool")
    if not exiftool:
        sys.exit("需要 exiftool：git clone --depth 1 https://github.com/exiftool/exiftool ~/exiftool")
    # 注意：exiftool 不能从零创建 Apple MakerNotes，所以对「非 iPhone 拍的」JPG 这一步通常写不进去（文件 unchanged）；
    # 能写进去的只有本来就带 Apple MakerNotes 的照片。写不进去时，MOV 仍带 identifier，去手机上用 intoLive 配对即可。
    r = subprocess.run([exiftool, "-overwrite_original", "-q", f"-ContentIdentifier={cid}", jpg], capture_output=True, text=True)
    if r.returncode:
        print("[ios] exiftool:", r.stderr.strip())
    chk = subprocess.run([exiftool, "-s", "-ContentIdentifier", jpg], capture_output=True, text=True).stdout.strip()
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", clip, "-c:v", "copy", "-an", "-movflags", "use_metadata_tags+faststart",
                    "-metadata", f"com.apple.quicktime.content.identifier={cid}", "-f", "mov", mov], check=True)
    print("[ios]", jpg, "+", mov, "| id", cid, "| jpg 写入:", chk or "失败（真机用 intoLive/makelive 配对）")
    return jpg, mov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["android", "ios"])
    ap.add_argument("image")
    ap.add_argument("clip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name")
    ap.add_argument("--exiftool", default=os.path.expanduser("~/exiftool/exiftool"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.image))[0]
    if a.kind == "android":
        android(a.image, a.clip, a.out, name)
    else:
        ios(a.image, a.clip, a.out, name, a.exiftool)


if __name__ == "__main__":
    main()
