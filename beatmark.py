# -*- coding: utf-8 -*-
"""
BeatMark - 音频卡点工具（纯本地离线版）
=================================================================
用途：给剪辑找卡点。导入音频 -> 选算法 -> 调参数 -> 分析 -> 试听 -> 导出时间戳。

特性：
  * 全部解码与计算在本机完成，不联网、无任何网络请求，音频不出本机。
  * 三种卡点算法：① Onset 瞬态起音检测（默认，剪辑卡点推荐）② 音量峰值检测 ③ 等间隔卡点（按固定秒数均匀分布）
  * 参数：灵敏度阈值 / 最小卡点间隔（Onset、峰值）或 间隔秒数（等间隔） / 全局时间偏移
  * 波形预览 + 卡点竖线标记 + 播放试听与时间指针
  * 导出 TXT（每行一个秒数）与 CSV（时间(秒), 时间(毫秒)）

运行：  python beatmark.py
打包：  双击 build_exe.bat  ->  生成 dist\\BeatMark.exe（单文件，免装 Python）
自检：  BeatMark.exe --selftest 音频文件 [--algo onset|peak] [--sensitivity 50]

版本：1.3.0    许可：MIT License    作者：Lyajjyurot
=================================================================
"""
import os
import sys
import csv
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

try:
    import miniaudio                      # 本地解码：MP3 / WAV / FLAC / OGG ...
    HAS_MINIAUDIO = True
except Exception:
    HAS_MINIAUDIO = False

try:
    import aubio                          # 若环境里有 aubio 则优先用它做起音检测
    HAS_AUBIO = True
except Exception:
    HAS_AUBIO = False

APP_TITLE = "BeatMark"
__version__ = "1.3.0"
ALGO_ONSET = "onset"
ALGO_PEAK = "peak"
ALGO_INTERVAL = "interval"
ALGO_LABELS = [
    "① Onset 瞬态起音检测（推荐）",
    "② 音量峰值检测",
    "③ 等间隔卡点（按固定秒数均匀分布）",
]
ALGO_BY_LABEL = {
    ALGO_LABELS[0]: ALGO_ONSET,
    ALGO_LABELS[1]: ALGO_PEAK,
    ALGO_LABELS[2]: ALGO_INTERVAL,
}
ALGO_DEFAULT_INTERVAL = 1.0     # 等间隔模式默认间隔（秒）

WIN = 1024        # 起音检测分析窗长（样本），与 aubio 默认一致
HOP = 512         # 帧移


# ----------------------------------------------------------------------
# 1. 音频解码（本地）
# ----------------------------------------------------------------------
def load_audio(path):
    """解码任意支持格式 -> (int16 单声道 numpy 数组, 采样率)

    注意：miniaudio 按“文件名”打开时无法处理中文/非 ASCII 路径
    （Windows 下会直接报 failed to decode file），
    所以这里先用 Python 把文件读进内存，再用内存解码。
    """
    if not HAS_MINIAUDIO:
        raise RuntimeError("缺少音频解码库 miniaudio，无法读取音频。")
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        raise RuntimeError("文件内容为空。")
    try:
        sr = int(miniaudio.get_file_info(path).sample_rate) or 44100
    except Exception:
        sr = 44100                      # 取不到原始采样率时兜底（重采样不改变时间轴）
    # nchannels=1 就地混单声道，sample_rate 传原始采样率，避免重采样造成时间漂移
    dec = miniaudio.decode(
        data, output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1, sample_rate=sr)
    pcm = np.frombuffer(bytes(dec.samples), dtype="<i2")
    return pcm, sr


# ----------------------------------------------------------------------
# 2. 卡点算法
# ----------------------------------------------------------------------
def _median_filter(x, size):
    """滑动中值（用于自适应阈值）。输出长度与输入一致（两端按边缘延拓）"""
    if x.size == 0:
        return x
    size = max(3, int(size) | 1)            # 强制奇数窗口
    if x.size < size:
        return np.full_like(x, float(np.median(x)), dtype=np.float32)
    half = size // 2
    pad = np.pad(x, half, mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(pad, size)
    return np.median(win, axis=1).astype(np.float32)


def spectral_odf(y, sr, win=WIN, hop=HOP):
    """起音检测函数 ODF：相对谱通量（谱变化量 / 当前帧谱能量之和）。

    用相对量而非绝对值，是因为它对整体响度不敏感：
    安静段落里的鼓点和响段里的鼓点得到相近的数值；
    而持续长音/持续人声的谱变化极小（实测 < 0.5%），不会被误触发。
    返回 (odf, 每帧RMS, hop)
    """
    n = y.size
    if n < win:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32), hop
    n_frames = 1 + (n - win) // hop
    hann = np.hanning(win).astype(np.float32)
    odf = np.zeros(n_frames, dtype=np.float32)
    rms = np.zeros(n_frames, dtype=np.float32)
    cols = np.arange(win)
    prev_last = None
    block = 256
    for start in range(0, n_frames, block):
        end = min(start + block, n_frames)
        idx = np.arange(start, end)[:, None] * hop + cols[None, :]
        frames = y[idx]
        rms[start:end] = np.sqrt((frames * frames).mean(axis=1))     # 原始帧能量，用于静音门限
        spec = np.abs(np.fft.rfft(frames * hann, axis=1)).astype(np.float32)
        mag = spec.sum(axis=1)
        if prev_last is None:                       # 首块第 0 帧无前帧，通量为 0
            if spec.shape[0] > 1:
                d = np.diff(spec, axis=0)
                np.maximum(d, 0, out=d)
                odf[start + 1:end] = d.sum(axis=1) / (mag[1:] + 1e-9)
        else:
            cat = np.empty((spec.shape[0] + 1, spec.shape[1]), dtype=np.float32)
            cat[0] = prev_last
            cat[1:] = spec
            d = np.diff(cat, axis=0)
            np.maximum(d, 0, out=d)
            odf[start:end] = d.sum(axis=1) / (mag + 1e-9)
        prev_last = spec[-1]
    return odf, rms, hop


def _local_maxima(x, radius):
    """在 ±radius 邻域内为最大值的点（含平台取首个）"""
    if x.size == 0:
        return np.zeros(0, dtype=bool)
    n = x.size
    radius = max(1, int(radius))
    left = np.empty(n, dtype=np.float32)
    right = np.full(n, -np.inf, dtype=np.float32)   # 右侧邻域必须排除自身，否则恒不大于
    left[:] = x
    for k in range(1, radius + 1):                  # 用滚动的窗口最大近似邻域最大
        left[k:] = np.maximum(left[k:], x[:-k])
        right[:-k] = np.maximum(right[:-k], x[k:])
    return (x >= left) & (x > right)


def _local_min(x, radius):
    """邻域最小值（含自身），用于计算峰的突出度"""
    n = x.size
    radius = max(1, int(radius))
    if n < 2:
        return x
    left = x.astype(np.float32, copy=True)
    right = x.astype(np.float32, copy=True)
    for k in range(1, radius + 1):
        left[k:] = np.minimum(left[k:], x[:-k])
        right[:-k] = np.minimum(right[:-k], x[k:])
    return np.minimum(left, right)


def _frame_times(idx, hop, sr, offset_samples):
    return (idx.astype(np.float64) * hop + offset_samples) / float(sr)


def _min_gap_sequential(times, min_gap):
    """按时间顺序保留卡点，丢弃与已保留点间隔过近的（防止同一鼓点重复标记）"""
    out = []
    for t in times:
        if not out or (t - out[-1]) >= min_gap - 1e-9:
            out.append(t)
    return out


def _min_gap_strength(times, strength, min_gap):
    """按强度优先保留卡点，间隔过近时保留更响的那个（峰值算法用）"""
    order = np.argsort(-np.asarray(strength))
    kept = []
    for i in order:
        t = times[i]
        if all(abs(t - k) >= min_gap - 1e-9 for k in kept):
            kept.append(t)
    kept.sort()
    return kept


def _apply_offset(times, offset_ms, duration):
    off = offset_ms / 1000.0
    out = []
    for t in times:
        v = t + off
        if 0.0 <= v <= duration + 1e-6:
            out.append(v)
    out.sort()
    return out


def onsets_builtin(y, sr, sensitivity):
    """① Onset 瞬态起音检测：相对谱通量 + 自适应中值阈值（等效 aubio 默认检测器思路）

    灵敏度阈值越大 -> 阈值越高 -> 只保留重鼓点；越小 -> 捕捉更细碎的鼓点。
    """
    odf, rms, hop = spectral_odf(y, sr)
    if odf.size == 0:
        return [], None
    med_k = 1.5 + sensitivity / 50.0                      # 相对中值的放大倍数
    floor = 0.020 + 0.030 * sensitivity / 100.0           # 绝对下限：压掉持续长音/颤音的数值抖动
    thr = np.maximum(_median_filter(odf, 9) * med_k, floor)
    gate = max(1e-4, 0.005 * float(rms.max()))            # 静音门限，避免底噪被当鼓点
    cand = (odf > thr) & (rms >= gate) & _local_maxima(odf, 1)
    idx = np.nonzero(cand)[0]
    times = _frame_times(idx, hop, sr, WIN / 2.0)         # 以帧中心时刻作为起音时刻
    return times.tolist(), odf


def onsets_aubio(y, sr, sensitivity):
    """① 若环境装有 aubio，则直接调用 aubio 的 onset 检测器"""
    o = aubio.onset("default", WIN, HOP, sr)
    o.set_threshold(0.05 + 0.005 * sensitivity)     # 灵敏度 50 -> 约 0.30（aubio 默认）
    o.set_silence(-60)
    o.set_minioi_s(0.02)
    n = y.size // HOP
    y32 = np.ascontiguousarray(y, dtype=np.float32)
    out = []
    for i in range(n):
        if o(y32[i * HOP:(i + 1) * HOP]):
            out.append(float(o.get_last_s()))
    return out


def peaks_builtin(y, sr, sensitivity):
    """② 音量峰值检测：振幅包络局部极大值，用于找高潮/响度位置

    注意：包络需要平滑，卡点位置会比重音起始点轻微滞后；持续长音容易产生多余标记。

    标记规则（v1.1 修改）：【不标记峰值本身】；改用峰值时刻前两帧进行标点
    —— 帧率按 30fps 计（每帧 1/30 秒），即 标记时刻 = 峰值时刻 - 2/30 秒，
    使卡点对齐到打击/起音到来前的位置，更贴合剪辑踩点的视觉落点。
    """
    blk = max(1, int(sr * 0.01))                    # 10ms 一块
    n = y.size // blk
    if n < 5:
        return [], None
    env = np.abs(y[:n * blk]).reshape(n, blk).mean(axis=1)
    env = np.convolve(env, np.ones(5, dtype=np.float32) / 5.0, mode="same")  # 对称平滑，无延迟
    env = env.astype(np.float32)
    emax = float(env.max())
    thr = emax * (0.15 + 0.45 * sensitivity / 100.0)     # 电平门限
    radius = max(1, int(0.030 * sr / blk))               # 30ms 邻域
    prom = emax * (0.08 + 0.20 * sensitivity / 100.0)    # 突出度：要求在邻域内真正"冒"出来
    cand = (env > thr) & _local_maxima(env, radius) & \
           ((env - _local_min(env, radius)) > prom)
    idx = np.nonzero(cand)[0]
    # 峰值时刻
    peak_times = _frame_times(idx, blk, sr, blk / 2.0)
    # 标记到峰值前两帧（30fps，每帧 1/30 秒），峰值本身不标记
    frame = 1.0 / 30.0
    times = [max(0.0, t - 2.0 * frame) for t in peak_times]
    return times, env[idx]


def interval_marks(duration, interval_s):
    """③ 等间隔卡点：从 0 秒起每隔 interval_s 秒放一个卡点，直到音频结尾。

    用于需要"均匀踩点"的场景（如卡点视频固定节奏、转场定时）。
    间隔秒数由用户设定（默认 1.0 秒）。
    """
    if duration <= 0 or interval_s <= 0:
        return []
    n = int(duration // interval_s)
    times = [i * interval_s for i in range(n + 1)]
    # 去掉可能因浮点误差略超过结尾的点
    return [t for t in times if t <= duration + 1e-9]


def analyze(pcm, sr, algo, sensitivity, min_gap_s, offset_ms, interval_s=None):
    """返回 (卡点秒数列表, 引擎名)"""
    y = pcm.astype(np.float32) / 32768.0
    duration = pcm.size / float(sr)
    if algo == ALGO_ONSET:
        if HAS_AUBIO:
            times = onsets_aubio(y, sr, sensitivity)
            engine = "aubio %s" % getattr(aubio, "__version__", "")
        else:
            times, _ = onsets_builtin(y, sr, sensitivity)
            engine = "内置 SpectralFlux（等效 aubio）"
        times = _min_gap_sequential(times, min_gap_s)
    elif algo == ALGO_PEAK:
        times, strength = peaks_builtin(y, sr, sensitivity)
        times = _min_gap_strength(times, strength, min_gap_s)
        engine = "内置 振幅包络峰值"
    elif algo == ALGO_INTERVAL:
        iv = interval_s if interval_s and interval_s > 0 else ALGO_DEFAULT_INTERVAL
        times = interval_marks(duration, iv)
        engine = "等间隔（每 %.2fs 一个）" % iv
    else:
        times, _ = onsets_builtin(y, sr, sensitivity)
        times = _min_gap_sequential(times, min_gap_s)
        engine = "内置 SpectralFlux（等效 aubio）"
    return _apply_offset(times, offset_ms, duration), engine


# ----------------------------------------------------------------------
# 3. 播放器（本地播放 + 播放位置）
# ----------------------------------------------------------------------
class Player:
    def __init__(self):
        self.dev = None
        self.pcm = b""
        self.frames = 0
        self.sr = 0
        self.bytes_per_frame = 2
        self.total_bytes = 0
        self.cursor = 0
        self.playing = False
        self.finished = False
        self.error = ""
        self.lock = threading.Lock()

    def load(self, pcm_bytes, sr):
        self.close()
        self.pcm = pcm_bytes
        self.sr = int(sr)
        self.frames = len(pcm_bytes) // self.bytes_per_frame
        self.total_bytes = self.frames * self.bytes_per_frame
        self.cursor = 0
        self.playing = False
        self.finished = False

    def _ensure_device(self):
        if self.dev is not None or self.sr == 0:
            return True
        if not HAS_MINIAUDIO:
            self.error = "缺少 miniaudio，无法播放"
            return False
        try:
            self.dev = miniaudio.PlaybackDevice(
                nchannels=1, sample_rate=self.sr, buffersize_msec=60)
            gen = self._gen()
            next(gen)                                # 生成器必须先启动，才能接收帧数
            self.dev.start(gen)
            return True
        except Exception as e:                       # 没有声卡/被占用等
            self.dev = None
            self.error = "音频设备不可用：%s" % e
            return False

    def _gen(self):
        """播放回调：按光标输出 PCM，暂停/结束后输出静音"""
        frames = yield b""
        frames = frames or 1024
        bpf = self.bytes_per_frame
        while True:
            with self.lock:
                if self.playing:
                    start = self.cursor * bpf
                    end = min(start + frames * bpf, self.total_bytes)
                    chunk = self.pcm[start:end]
                    self.cursor += len(chunk) // bpf
                    if self.cursor >= self.frames:
                        self.playing = False
                        self.finished = True
                    need = frames * bpf
                    if len(chunk) < need:
                        chunk = chunk + bytes(need - len(chunk))
                else:
                    chunk = bytes(frames * bpf)
            frames = yield chunk

    def play(self):
        if self.frames == 0 or not self._ensure_device():
            return False
        with self.lock:
            if self.cursor >= self.frames:
                self.cursor = 0
            self.finished = False
            self.playing = True
        return True

    def pause(self):
        with self.lock:
            self.playing = False

    def toggle(self):
        if self.playing:
            self.pause()
            return False
        return self.play()

    def stop(self):
        with self.lock:
            self.playing = False
            self.finished = False
            self.cursor = 0

    def seek(self, seconds):
        with self.lock:
            self.cursor = int(max(0.0, min(seconds, self.frames / float(self.sr or 1))) * self.sr)
            self.finished = False

    def pos(self):
        with self.lock:
            return self.cursor / float(self.sr or 1)

    def close(self):
        if self.dev is not None:
            try:
                self.dev.close()
            except Exception:
                pass
            self.dev = None


# ----------------------------------------------------------------------
# 4. 界面
# ----------------------------------------------------------------------
def fmt_time(sec):
    if sec is None:
        return "--:--.---"
    sec = max(0.0, sec)
    m = int(sec // 60)
    s = sec - m * 60
    return "%02d:%06.3f" % (m, s)


class App:
    def __init__(self, root):
        self.root = root
        self.path = None
        self.pcm = None
        self.pcm_bytes = b""
        self.sr = 0
        self.duration = 0.0
        self.marks = []
        self.player = Player()
        self.engine = ""
        self._cursor_id = None

        root.title(APP_TITLE)
        self._build_ui()
        # 按控件实际需求宽度决定窗口尺寸，保证参数与按钮不会被挤掉
        root.update_idletasks()
        need = int(self.box.winfo_reqwidth()) + 26
        root.geometry("%dx620" % max(1000, need))
        root.minsize(need, 500)
        self._redraw()
        self.root.after(40, self._tick)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- 界面搭建 ----------
    def _build_ui(self):
        pad = dict(padx=6, pady=4)

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="选择音频文件", command=self.choose_file).pack(side="left")
        ttk.Button(top, text="重置", command=self.reset).pack(side="left", padx=(6, 10))
        self.file_lbl = ttk.Label(top, text="未选择文件（支持 MP3 / WAV / FLAC / OGG）")
        self.file_lbl.pack(side="left")

        box = ttk.LabelFrame(self.root, text="卡点算法与参数")
        box.pack(fill="x", **pad)
        self.box = box

        row1 = ttk.Frame(box)
        row1.pack(fill="x", padx=6, pady=(6, 2))
        self.row1 = row1
        ttk.Label(row1, text="卡点算法：").pack(side="left")
        self.algo_var = tk.StringVar(value=ALGO_LABELS[0])
        self.algo_cb = ttk.Combobox(row1, textvariable=self.algo_var, state="readonly",
                                    width=32, values=ALGO_LABELS)
        self.algo_cb.pack(side="left")
        self.algo_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_params())

        # 最小卡点间隔（Onset / 峰值模式用）
        self.gap_group = ttk.Frame(row1)
        ttk.Label(self.gap_group, text="  最小卡点间隔(秒)：").pack(side="left")
        self.gap_var = tk.StringVar(value="0.15")
        ttk.Entry(self.gap_group, textvariable=self.gap_var, width=7).pack(side="left")

        # 间隔秒数（等间隔模式用）
        self.interval_group = ttk.Frame(row1)
        ttk.Label(self.interval_group, text="  间隔秒数(秒)：").pack(side="left")
        self.interval_var = tk.StringVar(value="%.1f" % ALGO_DEFAULT_INTERVAL)
        ttk.Entry(self.interval_group, textvariable=self.interval_var, width=7).pack(side="left")

        ttk.Label(row1, text="  全局时间偏移(毫秒，正数向后 / 负数向前)：").pack(side="left")
        self.off_var = tk.StringVar(value="0")
        ttk.Entry(row1, textvariable=self.off_var, width=7).pack(side="left")

        row2 = ttk.Frame(box)
        row2.pack(fill="x", padx=6, pady=(2, 6))
        self.row2 = row2
        ttk.Label(row2, text="灵敏度阈值（越大卡点越少，越小越细）：").pack(side="left")
        self.sens_var = tk.IntVar(value=50)
        self.sens_scale = tk.Scale(row2, from_=0, to=100, orient="horizontal", variable=self.sens_var,
                 length=190, showvalue=True, resolution=1, sliderlength=14,
                 width=12, highlightthickness=0)
        self.sens_scale.pack(side="left", padx=(0, 14))
        ttk.Button(row2, text="分析音频", command=self.run_analysis).pack(side="left")
        ttk.Button(row2, text="清空卡点", command=self.clear_marks).pack(side="left", padx=6)

        self.canvas = tk.Canvas(self.root, bg="#ffffff", highlightthickness=1,
                                highlightbackground="#c8c8c8", height=300)
        self.canvas.pack(fill="both", expand=True, padx=6)
        self.canvas.bind("<Configure>", lambda e: self._redraw())
        self.canvas.bind("<Button-1>", self._on_canvas_click)

        play = ttk.Frame(self.root)
        play.pack(fill="x", **pad)
        self.play_btn = ttk.Button(play, text="▶ 播放", width=10, command=self.toggle_play)
        self.play_btn.pack(side="left")
        ttk.Button(play, text="■ 停止", width=8, command=self.stop_play).pack(side="left", padx=6)
        self.time_lbl = ttk.Label(play, text="00:00.000 / --:--.---")
        self.time_lbl.pack(side="left", padx=10)
        self.count_lbl = ttk.Label(play, text="卡点：0 个")
        self.count_lbl.pack(side="left", padx=10)

        exp = ttk.Frame(self.root)
        exp.pack(fill="x", **pad)
        self.txt_btn = ttk.Button(exp, text="导出 TXT", command=self.export_txt, state="disabled")
        self.txt_btn.pack(side="left")
        self.csv_btn = ttk.Button(exp, text="导出 CSV", command=self.export_csv, state="disabled")
        self.csv_btn.pack(side="left", padx=6)
        self.status = ttk.Label(exp, text="就绪", foreground="#555555")
        self.status.pack(side="left", padx=10)

        # 根据当前所选算法，显示对应参数控件
        self._refresh_params()

    # ---------- 参数读取 ----------
    def _params(self):
        algo = ALGO_BY_LABEL.get(self.algo_var.get(), ALGO_ONSET)
        try:
            off = float(self.off_var.get())
        except ValueError:
            off = 0.0
            self.off_var.set("0")
        try:
            sens = int(self.sens_var.get())
        except ValueError:
            sens = 50
        try:
            gap = max(0.0, float(self.gap_var.get()))
        except ValueError:
            gap = 0.15
            self.gap_var.set("0.15")
        try:
            interval = max(1e-3, float(self.interval_var.get()))
        except ValueError:
            interval = ALGO_DEFAULT_INTERVAL
            self.interval_var.set("%.1f" % ALGO_DEFAULT_INTERVAL)
        return algo, sens, gap, off, interval

    # ---------- 参数控件随算法切换 ----------
    def _refresh_params(self):
        algo = ALGO_BY_LABEL.get(self.algo_var.get(), ALGO_ONSET)
        if algo == ALGO_INTERVAL:
            # 等间隔模式：显示"间隔秒数"，禁用灵敏度
            self.gap_group.pack_forget()
            self.interval_group.pack(side="left")
            self.sens_scale.config(state="disabled")
        else:
            # Onset / 峰值模式：显示"最小卡点间隔"，启用灵敏度
            self.interval_group.pack_forget()
            self.gap_group.pack(side="left")
            self.sens_scale.config(state="normal")
        # 不同算法需要的参数宽度不同，按当前内容重新约束窗口最小宽度
        self.root.update_idletasks()
        need = int(self.box.winfo_reqwidth()) + 26
        self.root.minsize(need, 500)
        if self.root.winfo_width() < need:
            self.root.geometry("%dx%d" % (need, self.root.winfo_height()))

    # ---------- 文件 ----------
    def choose_file(self):
        path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[("音频文件", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac *.wma"),
                       ("所有文件", "*.*")])
        if path:
            self.load_file(path)

    def load_file(self, path):
        self.stop_play()
        self.root.config(cursor="watch")
        self.status.config(text="正在解码音频…")
        self.root.update_idletasks()
        try:
            pcm, sr = load_audio(path)
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror(APP_TITLE, "读取音频失败：\n%s" % e)
            self.status.config(text="解码失败")
            return
        self.path = path
        self.pcm = pcm
        self.sr = sr
        self.duration = pcm.size / float(sr)
        self.pcm_bytes = pcm.tobytes()
        self.marks = []
        self.txt_btn.config(state="disabled")
        self.csv_btn.config(state="disabled")
        self.player.load(self.pcm_bytes, sr)
        self.file_lbl.config(text="%s  |  %d Hz  |  时长 %s" %
                                  (os.path.basename(path), sr, fmt_time(self.duration)))
        self.count_lbl.config(text="卡点：0 个")
        self.status.config(text="已解码，点击【分析音频】开始识别卡点")
        self.root.config(cursor="")
        self._redraw()

    def reset(self):
        self.stop_play()
        self.player.close()
        self.path = None
        self.pcm = None
        self.pcm_bytes = b""
        self.sr = 0
        self.duration = 0.0
        self.marks = []
        self.player.load(b"", 0)
        self.file_lbl.config(text="未选择文件（支持 MP3 / WAV / FLAC / OGG）")
        self.count_lbl.config(text="卡点：0 个")
        self.time_lbl.config(text="00:00.000 / --:--.---")
        self.txt_btn.config(state="disabled")
        self.csv_btn.config(state="disabled")
        self.status.config(text="已重置，请重新选择音频文件")
        self._redraw()

    # ---------- 分析 ----------
    def run_analysis(self):
        if self.pcm is None:
            messagebox.showinfo(APP_TITLE, "请先选择音频文件")
            return
        algo, sens, gap, off, interval = self._params()
        self.stop_play()
        self.root.config(cursor="watch")
        self.status.config(text="正在分析卡点…")
        self.root.update_idletasks()
        try:
            marks, engine = analyze(self.pcm, self.sr, algo, sens, gap, off, interval)
        except Exception as e:
            self.root.config(cursor="")
            messagebox.showerror(APP_TITLE, "分析失败：\n%s" % e)
            self.status.config(text="分析失败")
            return
        self.marks = marks
        self.engine = engine
        self.root.config(cursor="")
        state = "normal" if marks else "disabled"
        self.txt_btn.config(state=state)
        self.csv_btn.config(state=state)
        self.count_lbl.config(text="卡点：%d 个" % len(marks))
        if marks:
            self.status.config(text="分析完成 ｜ 引擎：%s ｜ 首个卡点 %s ｜ 末个卡点 %s"
                                    % (engine, fmt_time(marks[0]), fmt_time(marks[-1])))
        elif algo == ALGO_INTERVAL:
            self.status.config(text="分析完成 ｜ 引擎：%s ｜ 音频时长不足以生成间隔卡点，"
                                    "可减小间隔秒数" % engine)
        else:
            self.status.config(text="分析完成 ｜ 引擎：%s ｜ 没有识别到卡点，"
                                    "可调小灵敏度阈值或调小最小间隔" % engine)
        self._redraw()

    def clear_marks(self):
        self.marks = []
        self.count_lbl.config(text="卡点：0 个")
        self.txt_btn.config(state="disabled")
        self.csv_btn.config(state="disabled")
        self.status.config(text="已清空卡点标记")
        self._redraw()

    # ---------- 绘制 ----------
    def _x_of(self, t, w):
        return 6 + (w - 12) * (t / self.duration if self.duration > 0 else 0)

    def _t_of(self, x, w):
        return max(0.0, min(1.0, (x - 6) / max(1.0, w - 12))) * self.duration

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        self._cursor_id = None
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        ruler = 16
        top, bot = 6, h - ruler - 4
        if self.pcm is None:
            c.create_text(w / 2, h / 2, text="请先选择音频文件",
                          fill="#999999", font=("Microsoft YaHei UI", 11))
            return
        mid = (top + bot) / 2.0
        half = max(8.0, (bot - top) / 2.0 - 2)

        step = max(1, self.pcm.size // max(1, int(w - 12)))
        usable = (self.pcm.size // step) * step
        seg = self.pcm[:usable].reshape(-1, step).astype(np.float32) / 32768.0
        mx = seg.max(axis=1)
        mn = seg.min(axis=1)
        cols = mx.size
        xs = 6 + (np.arange(cols) + 0.5) * (w - 12) / cols
        ymax = np.clip(mid - mx * half, top, bot)
        ymin = np.clip(mid - mn * half, top, bot)
        # 上沿从左到右 + 下沿从右到左，拼成一个闭合的波形填充多边形
        pts = np.concatenate((np.stack((xs, ymax), axis=1).ravel(),
                              np.stack((xs[::-1], ymin[::-1]), axis=1).ravel()))
        c.create_polygon(pts.tolist(), fill="#5b8def", outline="#2f5fd0", tags="wave")

        # 时间刻度
        for t, label in self._ticks():
            x = self._x_of(t, w)
            c.create_line(x, top, x, bot, fill="#e6e6e6", tags="ruler")
            c.create_text(x + 2, h - ruler / 2 - 1, text=label, anchor="w",
                          fill="#8a8a8a", font=("Microsoft YaHei UI", 7), tags="ruler")

        self._draw_marks()

    def _ticks(self):
        if self.duration <= 0:
            return []
        for s in (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300):
            if self.duration / s <= 12:
                break
        out = []
        t = 0.0
        while t <= self.duration + 1e-9:
            out.append((t, ("%g" % t) + "s"))
            t += s
        return out

    def _draw_marks(self):
        c = self.canvas
        c.delete("marker")
        if not self.marks:
            return
        w = max(c.winfo_width(), 10)
        h = max(c.winfo_height(), 10)
        bot = h - 16 - 4
        for t in self.marks:
            x = self._x_of(t, w)
            c.create_line(x, 6, x, bot, fill="#e5484d", width=1, tags="marker")

    def _tick(self):
        if self.pcm is not None:
            pos = self.player.pos()
            self.time_lbl.config(text="%s / %s" % (fmt_time(pos), fmt_time(self.duration)))
            w = max(self.canvas.winfo_width(), 10)
            h = max(self.canvas.winfo_height(), 10)
            x = self._x_of(pos, w)
            if self._cursor_id is None:
                self._cursor_id = self.canvas.create_line(x, 6, x, h - 20,
                                                          fill="#16a34a", width=2, tags="cursor")
            else:
                self.canvas.coords(self._cursor_id, x, 6, x, h - 20)
            self.play_btn.config(text="⏸ 暂停" if self.player.playing else "▶ 播放")
            if self.player.finished:
                self.player.stop()
                self.status.config(text="播放结束")
        self.root.after(40, self._tick)

    # ---------- 播放 ----------
    def toggle_play(self):
        if self.pcm is None:
            return
        if not self.player.toggle():
            self.status.config(text=self.player.error or "已暂停")

    def stop_play(self):
        self.player.stop()

    def _on_canvas_click(self, event):
        if self.pcm is None:
            return
        self.player.seek(self._t_of(event.x, max(self.canvas.winfo_width(), 10)))

    # ---------- 导出 ----------
    def _default_name(self, ext):
        base = os.path.splitext(os.path.basename(self.path or "卡点"))[0]
        return "%s_卡点.%s" % (base, ext)

    def export_txt(self):
        if not self.marks:
            return
        path = filedialog.asksaveasfilename(
            title="导出 TXT 时间戳", defaultextension=".txt",
            initialfile=self._default_name("txt"), filetypes=[("文本文件", "*.txt")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join("%.3f" % t for t in self.marks) + "\n")
        except Exception as e:
            messagebox.showerror(APP_TITLE, "导出失败：%s" % e)
            return
        self.status.config(text="已导出 TXT：%s（%d 个卡点）" % (path, len(self.marks)))

    def export_csv(self):
        if not self.marks:
            return
        path = filedialog.asksaveasfilename(
            title="导出 CSV 时间戳", defaultextension=".csv",
            initialfile=self._default_name("csv"), filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                wr = csv.writer(f)
                wr.writerow(["时间(秒)", "时间(毫秒)"])
                for t in self.marks:
                    wr.writerow(["%.3f" % t, int(round(t * 1000))])
        except Exception as e:
            messagebox.showerror(APP_TITLE, "导出失败：%s" % e)
            return
        self.status.config(text="已导出 CSV：%s（%d 个卡点）" % (path, len(self.marks)))

    def _on_close(self):
        try:
            self.player.close()
        finally:
            self.root.destroy()


# ----------------------------------------------------------------------
# 5. 命令行自检（不需要图形界面，用于验证算法与打包结果）
# ----------------------------------------------------------------------
def selftest(args):
    if not args:
        print("用法: --selftest <音频文件> [--algo onset|peak|interval] "
              "[--sensitivity 50] [--min-gap 0.15] [--interval 1.0] [--offset 0]")
        return 2
    path = args[0]
    algo, sens, gap, off, interval = ALGO_ONSET, 50, 0.15, 0.0, ALGO_DEFAULT_INTERVAL
    for i, a in enumerate(args):
        if a == "--algo" and i + 1 < len(args):
            v = args[i + 1]
            algo = ALGO_PEAK if v == "peak" else (ALGO_INTERVAL if v == "interval" else ALGO_ONSET)
        elif a == "--sensitivity" and i + 1 < len(args):
            sens = int(args[i + 1])
        elif a == "--min-gap" and i + 1 < len(args):
            gap = float(args[i + 1])
        elif a == "--interval" and i + 1 < len(args):
            interval = float(args[i + 1])
        elif a == "--offset" and i + 1 < len(args):
            off = float(args[i + 1])
    pcm, sr = load_audio(path)
    dur = pcm.size / float(sr)
    marks, engine = analyze(pcm, sr, algo, sens, gap, off, interval)
    lines = [
        "文件: %s" % path,
        "采样率: %d Hz  时长: %.3f s  算法: %s  引擎: %s" % (sr, dur, algo, engine),
        "灵敏度: %d  最小间隔: %.3fs  间隔: %.3fs  偏移: %.1f ms" % (sens, gap, interval, off),
        "卡点数量: %d" % len(marks),
        "前 20 个卡点(秒): %s" % ", ".join("%.3f" % t for t in marks[:20]),
    ]
    text = "\n".join(lines)
    print(text)
    if getattr(sys, "frozen", False) and sys.stdout is None:
        # 打包为 GUI 版 exe 后没有控制台，把自检结果写到 exe 同目录
        with open(os.path.join(os.path.dirname(sys.executable), "selftest_result.txt"),
                  "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


def main():
    if "--version" in sys.argv or "-v" in sys.argv:
        print("%s %s" % (APP_TITLE, __version__))
        return
    if "--help" in sys.argv or "-h" in sys.argv:
        print("用法: audio_cardpoint.py [选项]\n"
              "  （不带参数）              启动图形界面\n"
              "  --selftest <音频文件>     命令行自检，打印卡点时间\n"
              "      --algo onset|peak|interval   卡点算法，默认 onset\n"
              "      --sensitivity 0-100   灵敏度阈值（Onset/峰值），默认 50\n"
              "      --min-gap 秒          最小卡点间隔（Onset/峰值），默认 0.15\n"
              "      --interval 秒         间隔秒数（等间隔），默认 1.0\n"
              "      --offset 毫秒         全局时间偏移，默认 0\n"
              "  --version                 显示版本号")
        return
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[idx + 1:]))
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", 1.25)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
