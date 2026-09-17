# 音频卡点工具

> 给剪辑找卡点的本地小工具：导入音频 → 自动识别鼓点/重音位置 → 导出时间戳，直接粘进剪映、PR、AE 对轨。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)](#下载使用)
[![No Network](https://img.shields.io/badge/%E7%BD%91%E7%BB%9C-%E5%AE%8C%E5%85%A8%E7%A6%BB%E7%BA%BF-success.svg)](#隐私与安全)

Python + Tkinter 写的，依赖极少（numpy + miniaudio），可打包成**单文件 exe**，目标机器不需要装 Python 和任何依赖库。

![界面示意](screenshots/ui-preview.svg)

## 功能

- **三种卡点算法**，针对不同场景
  - ① **Onset 瞬态起音检测**（默认，剪辑卡点推荐）：识别声音的起跳边缘，捕捉鼓点敲击瞬间。不会被长音、持续人声误触发，卡点时间对齐节拍更准。
  - ② **音量峰值检测**：找波形振幅最高点。适合定位音频的高潮/响度位置，缺点是标记会轻微滞后，长音容易产生多余标记。
  - ③ **等间隔卡点**：从 0 秒起每隔设定的"间隔秒数"均匀放一个卡点。适合需要固定节奏/定时间隔的场景（如卡点视频固定节奏、转场定时）。
- **三个可调参数**（按算法自动切换）：灵敏度阈值 + 最小卡点间隔（Onset、峰值用）/ 间隔秒数（等间隔用）+ 全局时间偏移（毫秒，用来补偿音频延迟）。
- **波形预览**：画布上画出波形，识别出的卡点用竖线标记；支持播放试听，播放时显示绿色时间指针；点击波形任意位置可跳转播放。改完参数点【分析音频】即重新计算并刷新。
- **两种导出格式**：TXT（每行一个秒数）与 CSV（时间(秒), 时间(毫秒)）。
- **重置**：一键清空当前音频、波形和卡点标记，方便换下一首。

## 下载使用

到 [Releases](../../releases) 下载 `音频卡点工具.exe`，双击运行即可，**不需要安装 Python 和任何依赖库**。

> - 首次运行 Windows 可能提示"已保护你的电脑/未知发布者"，点"更多信息 → 仍要运行"即可（PyInstaller 打包的 exe 没有代码签名，属于正常现象）。
> - 单文件 exe 每次启动都要先把自身解包到临时目录，文件越多启动越慢。本项目已经裁掉了用不到的资源，但如果你的机器杀软较严格，首次启动仍可能需要十几秒；想快的话可以用自源码打包出的**文件夹版**（同目录下的 `dist\音频卡点工具\`），启动通常在 1 秒内。

## 使用流程

1. **选择音频文件** —— 支持 MP3 / WAV / FLAC / OGG 等常见格式（中文路径、中文文件名都支持）
2. **选择卡点算法** —— 剪辑卡点选 ①，找高潮位置选 ②，要均匀踩点选 ③
3. **调整参数** —— 见下表
4. 点 **【分析音频】** —— 波形上出现红色卡点竖线
5. **播放试听** —— 核对卡点是否落在重音上，对不上就调参数重算，或用全局时间偏移整体微调
6. **导出 TXT / CSV** —— 拿去剪映、AE、PR 里对轨

## 参数说明

| 参数 | 范围 | 默认 | 作用 | 怎么调 |
| --- | --- | --- | --- | --- |
| 灵敏度阈值 | 0 ~ 100 | 50 | 阈值越高，只有明显的重鼓点会被标记（① ② 使用） | 卡点太碎/太多少 → 调大；漏掉轻鼓点 → 调小 |
| 最小卡点间隔 | ≥ 0 秒 | 0.15 | 两个卡点之间的最小间隔，防止同一个鼓点被重复标记（① ② 使用） | 鼓点非常密时可调小到 0.1；只想留每拍 → 调到 0.5 左右 |
| 间隔秒数 | > 0 秒 | 1.0 | 等间隔模式下两个卡点的间距（③ 使用） | 想要每 0.5 秒一个卡点 → 填 0.5；想要 2 秒一个 → 填 2 |
| 全局时间偏移 | 毫秒（可正可负） | 0 | 所有卡点统一向后（正）/ 向前（负）平移 | 卡点整体比画面早或晚一点点时，用它整体补偿 |

## 两种算法的实测表现

用 120BPM 鼓点 + 持续长音（pad）+ 纯长音的合成音频做过量化验证：

| 场景 | Onset 瞬态起音 | 音量峰值 |
| --- | --- | --- |
| 120BPM 鼓点 17 下 | 17/17 全部命中，误差 < 5ms | 17/17 命中，但比真实起始点晚约 8~25ms |
| 纯持续长音（无鼓点） | **0 个误报** | 会产生多余标记（算法固有特性） |
| 主歌（持续人声）+ 副歌（120BPM 鼓点） | 副歌 12/12 命中，主歌 0 误报 | 副歌 12/12 命中 |

结论：**要卡得准就用 ①**；② 只适合快速定位"哪里最响"。

## 导出格式

`导出 TXT` —— 每行一个卡点时间，单位秒，三位小数：

```
6.002
6.502
7.001
7.500
```

`导出 CSV` —— 两列，方便导入剪映、AE 查阅（用 Excel 打开也不会乱码）：

```csv
时间(秒),时间(毫秒)
6.002,6002
6.502,6502
7.001,7001
```

## 从源码运行

> 直接跑源码**不需要打包**：`audio_cardpoint.py` 本身就是完整程序，改完代码重新运行就生效。
> 打包成 exe 只是为了让**没装 Python 的人**也能用，或者方便分发。

### 方式一：双击 `run_source.bat`（Windows 最省事）

第一次运行会自动创建 `.venv` 虚拟环境并安装依赖（需要已装 Python 3.8+），之后每次双击就直接打开界面。

想用命令行功能也可以直接传参数：

```bat
run_source.bat --version
run_source.bat --selftest 音频文件.mp3 --algo peak --sensitivity 60
run_source.bat --selftest 音频文件.mp3 --algo interval --interval 0.5
```

### 方式二：手动命令行

```bash
git clone <本仓库地址>
cd <仓库目录>

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python audio_cardpoint.py
```

装依赖慢的话可以换国内源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 命令行自检（不开界面）

改完算法或打包后，用自检模式快速验证结果是否正确：

```bash
python audio_cardpoint.py --selftest 音频文件.mp3
python audio_cardpoint.py --selftest 音频文件.mp3 --algo peak --sensitivity 60 --min-gap 0.2 --offset 30
python audio_cardpoint.py --selftest 音频文件.mp3 --algo interval --interval 0.5
python audio_cardpoint.py --version
```

输出示例：

```
文件: song.mp3
采样率: 44100 Hz  时长: 13.000 s  算法: onset  引擎: 内置 SpectralFlux（等效 aubio）
灵敏度: 50  最小间隔: 0.150s  间隔: 1.000s  偏移: 0.0 ms
卡点数量: 13
前 20 个卡点(秒): 6.002, 6.502, 7.001, 7.500, ...
```

## 自己打包 exe

```bash
pip install pyinstaller
# 双击 build_exe.bat，或：
python build_exe.py
```

产物：

- `dist\音频卡点工具.exe` —— 单文件版，一个文件走天下
- `dist\音频卡点工具\音频卡点工具.exe` —— 文件夹版，启动快（推荐日常使用）

打包配置在 `audio_cardpoint.spec`。里面做了一件重要的事：把 Tcl 的时区数据（`tzdata`）和多语言提示（`msgs`）从打包内容里剔除——这三个目录占了 700 多个文件，而本工具完全用不到。单文件 exe 的启动耗时和"打包进去的文件数量"基本成正比（在本机实测每个文件约 40ms），裁剪后单文件版启动时间从 84 秒降到约 16 秒，文件夹版始终在 1 秒左右。

## 常见问题

**播放没声音 / 提示音频设备不可用？**
程序用的是系统默认输出设备（miniaudio / WASAPI）。检查系统输出设备是否正常、是否被其他软件独占；不播放也不影响分析与导出。

**Q: 为什么没有用 aubio？**
项目原本就是按 aubio 的算法设计的。但 aubio 在 PyPI 上**没有 Windows 预编译包**（官方只提供 conda 渠道），没有 C 编译器就无法安装和打包，所以内置了一个按 aubio 默认检测器思路实现的等效版本：相对谱通量（spectral flux）+ 自适应中值阈值 + 局部极大值，参数与 aubio 默认一致（Hann 窗 1024、帧移 512）。如果你本机装了 aubio（`conda install -c conda-forge aubio`），程序会自动优先调用 `aubio.onset("default")`，不需要改代码。

**Q: 音频会上传到网上吗？**
不会。全部解码和分析都在本机完成，代码里没有任何网络请求，断网也能正常用。测试时可以自己断网验证。

**Q: 支持哪些格式？**
miniaudio 支持的都能读：MP3、WAV、FLAC、OGG 等。视频文件里的音轨请先提取成音频再导入。

## 目录结构

```
.
├─ audio_cardpoint.py      主程序（单文件，约 800 行）
├─ audio_cardpoint.spec    PyInstaller 打包配置（含资源裁剪）
├─ build_exe.py            打包脚本
├─ build_exe.bat           双击打包
├─ requirements.txt        运行依赖
├─ screenshots/            README 用的界面示意图
├─ LICENSE
└─ CHANGELOG.md
```

## 技术栈

| 用途 | 方案 |
| --- | --- |
| 界面 | Tkinter（Python 自带） |
| 音频解码 | miniaudio（自带 mp3/wav/flac/ogg 解码器，纯 wheel 依赖） |
| 播放 | miniaudio PlaybackDevice（WASAPI） |
| 数值计算 | NumPy（FFT 谱通量、包络、局部极值） |
| 起音检测 | 相对谱通量 + 自适应中值阈值（等效 aubio 默认检测器） |
| 打包 | PyInstaller 单文件 / 文件夹 |

## 贡献

欢迎提 Issue 和 PR。改算法或参数映射的话，建议先用 `--selftest` 跑一遍上面的三类测试音频（精确节拍、纯长音、主歌+副歌），确认命中率和误报没有变差。

## 许可

[MIT License](LICENSE) © 2026 Lyajjyurot
