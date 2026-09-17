# 贡献指南

感谢你对音频卡点工具的关注！欢迎提交 Issue 和 Pull Request。

## 如何贡献

### 报告 Bug

1. 在 [Issues](../../issues) 中搜索是否已有相同问题
2. 如果没有，新建 Issue，包含：
   - 问题描述
   - 复现步骤
   - 期望行为与实际行为
   - 运行环境（Python 版本、操作系统等）
   - 相关错误日志或截图

### 提交功能建议

在 Issues 中新建，标题以 `[Feature]` 开头，描述你希望的功能和使用场景。

### 提交代码

1. Fork 本仓库
2. 创建你的特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'feat: 添加某某功能'`
4. 推送到你的分支：`git push origin feature/your-feature`
5. 创建 Pull Request

## 开发环境

```bash
git clone <你的 Fork 地址>
cd 卡点工具

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python audio_cardpoint.py
```

## 代码规范

- Python 代码遵循 PEP 8
- 提交信息使用[语义化版本](https://semver.org/lang/zh-CN/)格式：
  - `feat:` 新功能
  - `fix:` 修复 Bug
  - `docs:` 文档更新
  - `refactor:` 重构
  - `test:` 测试相关
  - `chore:` 构建/工具相关

## 测试

修改算法或参数映射后，建议用 `--selftest` 跑以下测试验证：

```bash
# 120BPM 鼓点测试（应全部命中）
python audio_cardpoint.py --selftest test_120bpm.mp3

# 纯长音测试（应 0 个误报）
python audio_cardpoint.py --selftest test_pad.mp3

# 主歌+副歌测试（副歌命中，主歌 0 误报）
python audio_cardpoint.py --selftest test_vocal.mp3
```

## 许可

提交的代码将采用与本项目相同的 [MIT License](LICENSE) 授权。
