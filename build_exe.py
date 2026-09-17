# -*- coding: utf-8 -*-
"""
打包脚本：把 audio_cardpoint.py 打成 exe（免安装 Python，双击即用）

产出：
  1. dist\\音频卡点工具.exe                 单文件版（一个文件搞定，要求的交付格式）
  2. dist\\音频卡点工具\\音频卡点工具.exe     文件夹版（启动最快，日常推荐；整个文件夹一起拷走）

用法：双击 build_exe.bat，或在本目录执行  python build_exe.py
     只打包其中一个：  python build_exe.py onefile     /     python build_exe.py onedir

打包细节（含 Tcl 无用数据的裁剪）在 audio_cardpoint.spec 里配置。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "audio_cardpoint.spec")
APP = "BeatMark"

# 可用环境变量覆盖，默认就是下面的标准路径
DIST = os.environ.get("BEAT_DIST", os.path.join(HERE, "dist"))
WORK = os.environ.get("BEAT_WORK", os.path.join(HERE, "_build"))


def build(mode):
    env = dict(os.environ, BEAT_MODE=mode)
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", DIST, "--workpath", os.path.join(WORK, mode),
            SPEC]
    print("开始打包 %s …" % mode)
    r = subprocess.run(args, cwd=HERE, env=env)
    if r.returncode != 0:
        print("打包失败，退出码 %d" % r.returncode)
        return None
    if mode == "onefile":
        return os.path.join(DIST, APP + ".exe")
    return os.path.join(DIST, APP, APP + ".exe")      # onedir 版在子目录里


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    result = []
    for mode in ("onefile", "onedir"):
        if only and only != mode:
            continue
        f = build(mode)
        if f and os.path.exists(f):
            print("  完成：%s（%.1f MB）" % (f, os.path.getsize(f) / 1048576.0))
            result.append(f)
    print("\n打包完毕。目标机器无需安装 Python 和任何依赖库，双击 exe 即可运行。")
    for p in result:
        print("  " + p)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
