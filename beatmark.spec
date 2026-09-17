# -*- coding: utf-8 -*-
"""
PyInstaller 打包配置（build_exe.py 会自动调用本文件，一般不用手动改）

为什么要自定义 spec：
  打包出来约 1000 个文件，其中 ~590 个是 Tcl 的时区数据(tzdata)、
  ~145 个是 Tcl/Tk 的多语言提示(msgs)，本工具完全用不到。
  单文件 exe 每次启动都要把这些文件解包出来，文件越多启动越慢，
  排除后启动时间大约缩短到原来的 1/4。

打包模式由环境变量 BEAT_MODE 控制：onefile（默认）/ onedir
"""
import os

APP = "BeatMark"
MODE = os.environ.get("BEAT_MODE", "onefile")
ROOT = os.path.dirname(os.path.abspath(SPEC))          # noqa: F821  (SPEC 由 PyInstaller 注入)

# 不打包的 Tcl/Tk 数据目录（路径片段）
DROP_PARTS = ("/tzdata/", "/msgs/")
KEEP_NAMES = ("encoding",)

a = Analysis(                                          # noqa: F821
    [os.path.join(ROOT, "beatmark.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=["_cffi_backend"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["soundfile", "pygame", "matplotlib", "PIL", "scipy", "pytest",
              "numpy.f2py", "numpy.distutils", "numpy.testing"],
    noarchive=False,
)


def _keep(entry):
    """True 表示保留该数据文件"""
    dest = entry[0].replace("\\", "/")
    if any(part in ("/" + dest) for part in KEEP_NAMES):
        return True
    return not any(p in dest for p in DROP_PARTS)


_before = len(a.datas)
a.datas = [d for d in a.datas if _keep(d)]
print("[beat.spec] 数据文件 %d -> %d（已排除 Tcl 时区/多语言数据）"
      % (_before, len(a.datas)))

pyz = PYZ(a.pure)                                      # noqa: F821

if MODE == "onefile":
    exe = EXE(                                         # noqa: F821
        pyz, a.scripts, a.binaries, a.datas, [],
        name=APP, debug=False, bootloader_ignore_signals=False,
        strip=False, upx=False, console=False, disable_windowed_traceback=False,
        argv_emulation=False, target_arch=None, codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(                                         # noqa: F821
        pyz, a.scripts, [], exclude_binaries=True,
        name=APP, debug=False, strip=False, upx=False, console=False,
        disable_windowed_traceback=False,
    )
    coll = COLLECT(                                    # noqa: F821
        exe, a.binaries, a.datas, strip=False, upx=False, name=APP,
    )
