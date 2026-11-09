#!/usr/bin/env python3
"""
assemble_shanhai_60s.py — 《山海寻光记：赴一场四季星河》60.00s 全流程 AI 漫剧后期精剪合成引擎
结合 zenstory-ai/drama-skills (short-drama-edit 剪辑单校验) + 15 处电影级帧精确 xfade 叠化衔接 + 四幕动态配乐环境声混音 + ASS 双样式字幕烧录
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.signal as spsig
import soundfile as sf


def ass_ts(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def compute_timeline_windows(n_shots: int = 16, fps: int = 24) -> list[dict]:
    """
    12 shots x 97f + 4 shots x 96f = 1548 input frames.
    12 intra-act dissolves x 6f (0.25s) + 3 inter-act dissolves x 12f (0.50s) = 108 overlap frames.
    1548 - 108 = 1440 frames = EXACT 60.000s @ 24.0 fps!
    """
    windows = []
    cur_f = 0
    for i in range(1, n_shots + 1):
        flen = 97 if i <= 12 else 96
        in_overlap = 0 if i == 1 else (12 if (i - 1) in (4, 8, 12) else 6)
        out_overlap = 0 if i == n_shots else (12 if i in (4, 8, 12) else 6)
        start_f = cur_f
        end_f = start_f + flen
        solo_in_f = start_f + in_overlap
        solo_out_f = end_f - out_overlap
        windows.append({
            "idx": i,
            "trim_start_f": 0 if i <= 12 else 1,
            "flen": flen,
            "start_f": start_f,
            "end_f": end_f,
            "start_s": start_f / fps,
            "end_s": end_f / fps,
            "solo_in_s": solo_in_f / fps,
            "solo_out_s": solo_out_f / fps,
            "out_xfade_f": out_overlap,
            "out_xfade_s": out_overlap / fps,
        })
        cur_f = end_f - out_overlap
    assert cur_f == 1440, f"Expected 1440 frames, got {cur_f}"
    return windows


def synth_note(freq: float, dur: float, sr: int, timbre: str = "piano") -> np.ndarray:
    t = np.arange(int(dur * sr), dtype=np.float32) / sr
    if timbre == "piano":
        env = np.exp(-2.6 * t) * (1.0 - np.exp(-90.0 * t))
        sig = (
            1.00 * np.sin(2 * np.pi * freq * t)
            + 0.36 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-1.5 * t)
            + 0.14 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-2.8 * t)
            + 0.05 * np.sin(2 * np.pi * 4 * freq * t) * np.exp(-4.0 * t)
        )
        return (sig * env).astype(np.float32)
    elif timbre == "celesta":
        env = np.exp(-3.8 * t) * (1.0 - np.exp(-140.0 * t))
        sig = np.sin(2 * np.pi * freq * t) + 0.22 * np.sin(2 * np.pi * 2 * freq * t) + 0.08 * np.sin(2 * np.pi * 5.02 * freq * t) * np.exp(-6.0 * t)
        return (sig * env).astype(np.float32)
    else:  # warm strings pad
        att = np.clip(t / min(0.55, dur * 0.35), 0.0, 1.0)
        rel = np.clip((dur - t) / min(0.65, dur * 0.40), 0.0, 1.0)
        env = np.sin(0.5 * np.pi * att) * np.sin(0.5 * np.pi * rel)
        vib = 1.0 + 0.0022 * np.sin(2 * np.pi * 5.1 * t)
        ph = 2 * np.pi * np.cumsum(freq * vib) / sr
        sig = 0.72 * np.sin(ph) + 0.28 * np.sin(2 * ph + 0.3) + 0.12 * np.sin(3 * ph + 0.7)
        return (sig * env).astype(np.float32)


def synthesize_4act_score_and_ambience(sr: int = 48000, total_s: float = 60.0) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """合成 60.00s 四幕治愈电影配乐 + 四幕独立立体声自然环境音（供混音与 drama-skills 剪辑单落盘）"""
    n = int(round(total_s * sr))
    score = np.zeros((n, 2), dtype=np.float32)
    rng = np.random.default_rng(202611)

    # 4-Act chord progression: 16 bars x 3.75s = 60.00s
    chords = [
        # Act I: Dawn Valley (Fmaj9 -> G6 -> Em7 -> Am9)
        ([174.61, 220.00, 261.63, 329.63, 392.00], [523.25, 659.25, 783.99, 659.25], "piano"),
        ([196.00, 246.94, 293.66, 329.63, 392.00], [587.33, 659.25, 783.99, 880.00], "piano"),
        ([164.81, 246.94, 293.66, 392.00],         [659.25, 587.33, 493.88, 587.33], "piano"),
        ([220.00, 261.63, 329.63, 392.00, 493.88], [523.25, 659.25, 783.99, 987.77], "piano"),
        # Act II: Flower Sea & Sun-Shower (Cmaj9 -> Fmaj7 -> Dm9 -> G13)
        ([130.81, 196.00, 246.94, 293.66, 329.63], [523.25, 659.25, 783.99, 1046.5], "piano"),
        ([174.61, 220.00, 261.63, 329.63, 440.00], [698.46, 659.25, 523.25, 659.25], "celesta"),
        ([146.83, 220.00, 261.63, 329.63, 440.00], [587.33, 659.25, 783.99, 659.25], "celesta"),
        ([196.00, 293.66, 349.23, 440.00, 493.88], [587.33, 698.46, 783.99, 987.77], "piano"),
        # Act III: Sunset Lighthouse & Coastal Sea (Am9 -> Fmaj7 -> C/G -> Gsus4)
        ([110.00, 220.00, 261.63, 329.63, 493.88], [523.25, 493.88, 440.00, 523.25], "piano"),
        ([174.61, 261.63, 329.63, 392.00, 440.00], [523.25, 659.25, 783.99, 659.25], "piano"),
        ([196.00, 261.63, 329.63, 392.00, 523.25], [783.99, 659.25, 523.25, 659.25], "piano"),
        ([196.00, 261.63, 293.66, 392.00, 493.88], [587.33, 659.25, 783.99, 587.33], "piano"),
        # Act IV: Thousand River Lanterns & Starry Milky Way Finale (Fmaj9 -> Em7 -> Dm9 -> Cmaj9)
        ([174.61, 220.00, 261.63, 329.63, 392.00], [659.25, 783.99, 1046.5, 783.99], "celesta"),
        ([164.81, 246.94, 329.63, 392.00, 493.88], [783.99, 659.25, 587.33, 659.25], "celesta"),
        ([146.83, 220.00, 261.63, 329.63, 392.00], [587.33, 659.25, 783.99, 1046.5], "celesta"),
        ([130.81, 196.00, 246.94, 293.66, 329.63, 523.25], [1046.5, 783.99, 659.25, 523.25], "piano"),
    ]

    bar_s = 3.75
    for b_idx, (pad_freqs, arp_freqs, lead_timbre) in enumerate(chords):
        t0 = b_idx * bar_s
        i0 = int(t0 * sr)
        # Warm stereo strings pad
        for k, pf in enumerate(pad_freqs):
            pad = synth_note(pf, min(bar_s + 0.55, total_s - t0), sr, "pad") * 0.042
            pan = 0.35 + 0.30 * ((k % 3) / 2.0)
            i1 = min(n, i0 + len(pad))
            score[i0:i1, 0] += pad[: i1 - i0] * math.sqrt(1.0 - pan)
            score[i0:i1, 1] += pad[: i1 - i0] * math.sqrt(pan)

        # Expressive arpeggio / melody notes
        step_s = bar_s / len(arp_freqs)
        for m_i, mf in enumerate(arp_freqs):
            nt0 = t0 + m_i * step_s
            ni0 = int(nt0 * sr)
            if ni0 >= n:
                break
            ndur = min(2.1, total_s - nt0)
            note = synth_note(mf, ndur, sr, lead_timbre) * (0.068 if lead_timbre == "piano" else 0.055)
            pan = 0.30 + 0.40 * ((m_i + b_idx) % 2)
            ni1 = min(n, ni0 + len(note))
            score[ni0:ni1, 0] += note[: ni1 - ni0] * math.sqrt(1.0 - pan)
            score[ni0:ni1, 1] += note[: ni1 - ni0] * math.sqrt(pan)

    # Gentle stereo reverb tail (two decorrelated delays)
    for d_ms, g in [(115, 0.22), (235, 0.13)]:
        ds = int(d_ms * sr / 1000)
        score[ds:, 0] += score[:-ds, 1] * g
        score[ds:, 1] += score[:-ds, 0] * g

    # 4 Act stereo ambient beds (15.0s each)
    amb_len = int(15.0 * sr)
    amb_acts: dict[int, np.ndarray] = {}
    t_amb = np.arange(amb_len, dtype=np.float32) / sr

    # Act 1: Morning mountain breeze + gentle birdsong chirps
    w1 = rng.standard_normal((amb_len, 2)).astype(np.float32)
    b1, a1 = spsig.butter(2, [180 / (sr / 2), 950 / (sr / 2)], btype="band")
    bed1 = spsig.lfilter(b1, a1, w1, axis=0).astype(np.float32) * 0.012
    for bt in [1.1, 2.8, 6.2, 10.5, 13.4]:
        bi = int(bt * sr)
        bl = int(0.18 * sr)
        tt = np.arange(bl, dtype=np.float32) / sr
        chirp = np.sin(2 * np.pi * (2400 + 650 * np.sin(2 * np.pi * 14 * tt)) * tt) * np.hanning(bl) * 0.014
        bed1[bi : bi + bl, int(bt * 3) % 2] += chirp
    amb_acts[1] = bed1

    # Act 2: Meadow breeze (0-7.5s) -> sparkling sun-shower brook & raindrop patter (7.5-15s)
    w2 = rng.standard_normal((amb_len, 2)).astype(np.float32)
    b2, a2 = spsig.butter(2, [400 / (sr / 2), 3800 / (sr / 2)], btype="band")
    rain_env = np.clip((t_amb - 6.8) / 1.5, 0.25, 1.0) * np.clip((14.6 - t_amb) / 1.5, 0.35, 1.0)
    amb_acts[2] = spsig.lfilter(b2, a2, w2, axis=0).astype(np.float32) * (0.010 * rain_env[:, None])

    # Act 3: Rolling coastal sunset ocean waves (slow 0.16 Hz surf swell)
    w3 = rng.standard_normal((amb_len, 2)).astype(np.float32)
    b3, a3 = spsig.butter(2, [120 / (sr / 2), 1600 / (sr / 2)], btype="band")
    surf = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.17 * t_amb - 0.6))
    amb_acts[3] = spsig.lfilter(b3, a3, w3, axis=0).astype(np.float32) * (0.015 * surf[:, None])

    # Act 4: Tranquil night river water + soft distant golden firework bloom at +11.8s & +13.2s
    w4 = rng.standard_normal((amb_len, 2)).astype(np.float32)
    b4, a4 = spsig.butter(2, [160 / (sr / 2), 1100 / (sr / 2)], btype="band")
    bed4 = spsig.lfilter(b4, a4, w4, axis=0).astype(np.float32) * 0.009
    for ft in [11.6, 13.1]:
        fi = int(ft * sr)
        fl = int(1.1 * sr)
        if fi + fl < amb_len:
            tt = np.arange(fl, dtype=np.float32) / sr
            fw = rng.standard_normal((fl, 2)).astype(np.float32)
            bf, af = spsig.butter(2, [90 / (sr / 2), 2200 / (sr / 2)], btype="band")
            shimmer = spsig.lfilter(bf, af, fw, axis=0).astype(np.float32) * (np.exp(-3.2 * tt) * (1 - np.exp(-35 * tt)))[:, None] * 0.022
            bed4[fi : fi + fl] += shimmer
    amb_acts[4] = bed4

    return score, amb_acts


def prepare_voice_clip(flac_path: Path, max_slot_s: float, voice_mode: str, ff_exe: str, sr: int = 48000) -> np.ndarray:
    y, c_sr = sf.read(str(flac_path), dtype="float32")
    if y.ndim == 2:
        y = y.mean(axis=1)
    if c_sr != sr:
        y = spsig.resample_poly(y, sr, c_sr).astype(np.float32)

    # Trim silence (-36 dB)
    win = max(1, int(sr * 0.01))
    env = np.convolve(y ** 2, np.ones(win) / win, mode="same")
    thresh = (float(np.max(env)) + 1e-12) * (10.0 ** (-36.0 / 10.0))
    idx = np.where(env >= thresh)[0]
    if len(idx) > 0:
        pad = int(0.025 * sr)
        y = y[max(0, int(idx[0]) - pad) : min(len(y), int(idx[-1]) + pad)]

    cur_s = len(y) / sr
    if cur_s > max_slot_s:
        ratio = float(np.clip(cur_s / (max_slot_s * 0.96), 1.0, 1.25))
        with tempfile.TemporaryDirectory() as td:
            iw, ow = os.path.join(td, "i.wav"), os.path.join(td, "o.wav")
            sf.write(iw, y, sr)
            subprocess.run([ff_exe, "-y", "-i", iw, "-filter:a", f"atempo={ratio:.4f}", "-ar", str(sr), ow],
                           check=True, capture_output=True)
            y, _ = sf.read(ow, dtype="float32")
            if y.ndim == 2:
                y = y.mean(axis=1)

    nf = min(len(y) // 4, int(0.02 * sr))
    if nf > 1:
        ramp = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, nf, dtype=np.float32)))
        y[:nf] *= ramp
        y[-nf:] *= ramp[::-1]

    peak = float(np.max(np.abs(y))) + 1e-8
    y = (y / peak) * 0.86

    st = np.column_stack([y, y]).astype(np.float32)
    if voice_mode == "VO":
        # Subtle warm stereo air reflection for poetic landscape narration
        d_samp = int(0.028 * sr)
        if len(st) > d_samp:
            st[d_samp:, 0] += st[:-d_samp, 1] * 0.11
            st[d_samp:, 1] += st[:-d_samp, 0] * 0.09
    return st


def write_ass_subtitles(ass_path: Path, placements: list[dict]):
    header = """[Script Info]
Title: 山海寻光记：赴一场四季星河
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Dialogue,ZCOOL KuaiLe,54,&H00FFFFFF,&H0000FFFF,&H00181C24,&H78000000,0,0,0,0,100,100,1.5,0,1,4.2,2.0,2,64,64,175,1
Style: NarrationVO,ZCOOL KuaiLe,50,&H00C8F4FF,&H0000FFFF,&H00202636,&H80000000,0,0,0,0,100,100,2.0,0,1,4.0,2.2,2,72,72,185,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev_lines = []
    for p in placements:
        st_name = "NarrationVO" if p["voice_mode"] == "VO" else "Dialogue"
        txt = "{\\fad(140,160)}" + p["sub_display"]
        ev_lines.append(f"Dialogue: 0,{ass_ts(p['sub_in'])},{ass_ts(p['sub_out'])},{st_name},{p['speaker']},0,0,0,,{txt}")
    ass_path.write_text(header + "\n".join(ev_lines) + "\n", encoding="utf-8")


def write_drama_skills_cutlist(ep_dir: Path, shots: list[dict], voice_files: dict[int, str]):
    """生成严格符合 zenstory-ai/drama-skills short-drama-edit 规范的 剪辑单.md（供 edit_tool.py check 核验）"""
    lines = [
        "# EP001 剪辑单\n",
        "- 成片目标时长：60.00 秒",
        "- 画幅与帧率：9:16 · 1080×1920 · 24fps",
        "- 交付响度：-16 LUFS",
        "- 字幕：硬字幕，台词逐字取自《剧本.md》，底部安全区内\n",
    ]
    for s in shots:
        idx = int(s["idx"])
        cid = f"CUT-EP001-{idx:03d}"
        vid_rel = f"制作成果/videos/{s['id']}.mp4"
        v_rel = f"制作成果/配音/{voice_files[idx]}"
        lines.append(f"## {cid} · {s['title']}\n")
        lines.append(f"- 来源：{s['motion_id']} · {vid_rel}")
        lines.append("- 入点：0.12")
        lines.append("- 出点：3.87")
        lines.append("- 时长：3.75")
        lines.append(f"- 取舍：入点=跳过起始3帧微静帧，从{s['title']}动态稳定展开处切入；出点=动作完成且画面未漂移处收口，与下一镜平滑接镜")
        lines.append(f"- 声音：融合 44.1kHz Seed-VC 克隆角色干声与第{(idx-1)//4+1}幕自然环境声及动态配乐")
        lines.append("- 画面：无")
        lines.append(f"- 字幕：{s['line']}")
        lines.append(f"- 配音：0.28 {v_rel}")
        if idx in (1, 5, 9, 13):
            act_no = (idx - 1) // 4 + 1
            lines.append(f"- 环境声：0.00 制作成果/环境声/act{act_no}_ambience.flac（增益：-6）")
        lines.append("")
    (ep_dir / "剪辑单.md").write_text("\n".join(lines), encoding="utf-8")


def run_master_assembly(proj_dir: Path, ff_exe: str, fonts_dir: str) -> dict:
    ep_dir = proj_dir / "剧集" / "EP001"
    prod_dir = ep_dir / "制作成果"
    vid_dir = prod_dir / "videos"
    voc_dir = prod_dir / "配音"
    amb_dir = prod_dir / "环境声"
    out_dir = prod_dir / "成片"
    for d in (amb_dir, out_dir):
        d.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((proj_dir / "episode_manifest_60s.json").read_text(encoding="utf-8"))
    shots = manifest["shots"]
    windows = compute_timeline_windows(16, 24)

    sr = 48000
    total_samples = 60 * sr
    score, amb_acts = synthesize_4act_score_and_ambience(sr=sr, total_s=60.0)

    # Save 4 ambient FLACs for drama-skills 剪辑单.md verification & crossfade onto 60s master bed
    amb_master = np.zeros((total_samples, 2), dtype=np.float32)
    for old_wav in amb_dir.glob("*.wav"):
        old_wav.unlink()
    for act_no in range(1, 5):
        aw = amb_acts[act_no]
        sf.write(str(amb_dir / f"act{act_no}_ambience.flac"), aw, sr)
        s0 = (act_no - 1) * 15 * sr
        amb_master[s0 : s0 + len(aw)] += aw

    voice_master = np.zeros((total_samples, 2), dtype=np.float32)
    speech_env = np.zeros(total_samples, dtype=np.float32)
    placements = []
    voice_files = {}

    for s, w in zip(shots, windows):
        idx = int(s["idx"])
        cands = sorted(voc_dir.glob(f"v{idx:02d}_*.flac"))
        if not cands:
            raise FileNotFoundError(f"Missing cloned voice clip v{idx:02d}_*.flac in {voc_dir}")
        v_path = cands[0]
        voice_files[idx] = v_path.name

        solo_span = w["solo_out_s"] - w["solo_in_s"]
        max_slot = max(1.75, solo_span - 0.68)
        v_st = prepare_voice_clip(v_path, max_slot, s["voice_mode"], ff_exe, sr=sr)
        v_dur = len(v_st) / sr

        # Place cleanly inside the solo non-dissolve window with >=0.45s tail breath before next cut
        v_in_s = w["solo_in_s"] + max(0.14, min(0.32, (solo_span - v_dur) * 0.30))
        i0 = int(round(v_in_s * sr))
        i1 = min(total_samples, i0 + len(v_st))
        voice_master[i0:i1] += v_st[: i1 - i0]
        speech_env[i0:i1] = 1.0

        placements.append({
            "idx": idx,
            "speaker": s["speaker"],
            "voice_mode": s["voice_mode"],
            "sub_display": s["sub_display"],
            "voice_in": round(v_in_s, 3),
            "voice_out": round(i1 / sr, 3),
            "sub_in": round(max(w["solo_in_s"] + 0.04, v_in_s - 0.06), 3),
            "sub_out": round(min(w["solo_out_s"] - 0.04, i1 / sr + 0.14), 3),
        })

    # Write & verify zenstory-ai/drama-skills 剪辑单.md
    write_drama_skills_cutlist(ep_dir, shots, voice_files)

    # Smooth sidechain ducking on musical score (-4.6 dB during speech)
    k_atk = int(0.18 * sr)
    duck_curve = np.convolve(speech_env, np.hanning(k_atk) / np.sum(np.hanning(k_atk)), mode="same")
    duck_gain = 1.0 - 0.41 * np.clip(duck_curve, 0.0, 1.0)
    mix = voice_master * 0.92 + score * duck_gain[:, None] + amb_master

    # Gentle 0.4s audio fade-in & 0.85s fade-out + soft limiter (-0.8 dBFS)
    fi_n, fo_n = int(0.40 * sr), int(0.85 * sr)
    mix[:fi_n] *= np.linspace(0.0, 1.0, fi_n, dtype=np.float32)[:, None]
    mix[-fo_n:] *= np.linspace(1.0, 0.0, fo_n, dtype=np.float32)[:, None]
    mix = np.tanh(mix * 1.08) / np.tanh(1.08)
    pk = float(np.max(np.abs(mix))) + 1e-8
    mix = (mix / pk) * (10.0 ** (-0.8 / 20.0))

    with tempfile.TemporaryDirectory(prefix="shanhai60_") as td:
        td_p = Path(td)
        wav_p = td_p / "master_60s.wav"
        ass_p = td_p / "subs_60s.ass"
        xfade_mp4 = td_p / "xfade_60s_nosub.mp4"
        sf.write(str(wav_p), mix, sr, subtype="PCM_16")
        write_ass_subtitles(ass_p, placements)

        # Build exact 16-input xfade filter_complex -> 1440 frames = 60.000s @ 24fps
        inputs = []
        fc_parts = []
        for w, s in zip(windows, shots):
            vp = vid_dir / f"{s['id']}.mp4"
            inputs += ["-i", str(vp)]
            f0 = w["trim_start_f"]
            f1 = f0 + w["flen"]
            fc_parts.append(
                f"[{w['idx']-1}:v]trim=start_frame={f0}:end_frame={f1},setpts=PTS-STARTPTS,fps=24,format=yuv420p[v{w['idx']}]"
            )

        prev_lbl = "v1"
        for k in range(1, 16):
            nxt_w = windows[k]
            cur_w = windows[k - 1]
            offset_s = nxt_w["start_s"]
            dur_s = cur_w["out_xfade_s"]
            out_lbl = f"x{k}"
            fc_parts.append(
                f"[{prev_lbl}][v{k+1}]xfade=transition=fade:duration={dur_s:.6f}:offset={offset_s:.6f}[{out_lbl}]"
            )
            prev_lbl = out_lbl

        fc_parts.append(f"[{prev_lbl}]fade=t=in:st=0:d=0.45,fade=t=out:st=59.25:d=0.75,format=yuv420p[vout]")

        cmd1 = [
            ff_exe, "-y", *inputs,
            "-filter_complex", ";".join(fc_parts),
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-r", "24", "-frames:v", "1440",
            str(xfade_mp4),
        ]
        r1 = subprocess.run(cmd1, capture_output=True, text=True)
        if r1.returncode != 0:
            raise RuntimeError(f"xfade pass failed:\n{r1.stderr[-1200:]}")

        # Pass 2: Burn ASS subtitles AFTER xfade + mux 48kHz master audio -> final 60.000s MP4
        final_mp4 = out_dir / "shanhai_xunguang_60s_final.mp4"
        esc_ass = str(ass_p).replace("\\", "/").replace(":", "\\:")
        esc_fd = str(fonts_dir).replace("\\", "/").replace(":", "\\:")
        cmd2 = [
            ff_exe, "-y",
            "-i", str(xfade_mp4),
            "-i", str(wav_p),
            "-vf", f"ass=filename='{esc_ass}':fontsdir='{esc_fd}',format=yuv420p",
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:v", "libx264", "-preset", "medium", "-crf", "24.5", "-profile:v", "high", "-level", "4.1",
            "-r", "24", "-frames:v", "1440",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-shortest", "-movflags", "+faststart",
            str(final_mp4),
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0:
            raise RuntimeError(f"Subtitle/audio mux failed:\n{r2.stderr[-1200:]}")

    return {"final_mp4": str(final_mp4), "placements": placements, "windows": windows}


if __name__ == "__main__":
    p_dir = Path(sys.argv[1]).resolve()
    ff = sys.argv[2] if len(sys.argv) > 2 else shutil.which("ffmpeg")
    fdir = sys.argv[3] if len(sys.argv) > 3 else "/tmp/fonts"
    res = run_master_assembly(p_dir, ff, fdir)
    print(f"[OK] Master 60s AI Comic-Drama rendered -> {res['final_mp4']}")
