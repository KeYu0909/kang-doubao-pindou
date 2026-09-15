# 永康玩AI · 拼豆助手 v0.2.0

正式技能名：`kang-doubao-pindou`。本仓库用于分发已验收的完整技能 ZIP，源代码、中文使用说明、自动测试和依赖许可都在发布附件内。

## 直接下载

**[下载完整技能包 kang-doubao-pindou.zip](https://github.com/KeYu0909/kang-doubao-pindou/releases/download/v0.2.0/kang-doubao-pindou.zip)**

[查看版本说明](https://github.com/KeYu0909/kang-doubao-pindou/releases/tag/v0.2.0)

无需 GitHub 登录。请使用上面的完整技能包，不要使用 GitHub 自动生成的 Source code 压缩包；自动压缩包仅包含本分发仓库的页面文件。

## 发给豆包

把下面这段话复制给豆包：

```text
请下载这个拼豆 Skill：
https://github.com/KeYu0909/kang-doubao-pindou/releases/download/v0.2.0/kang-doubao-pindou.zip
解压后先阅读 kang-doubao-pindou/SKILL.md 和 README.md，检查当前环境能否执行 Python 脚本及安装依赖。若可用，按说明安装并运行 doctor，再等待我上传图片。若环境不支持下载、解压或执行，请明确说明受限步骤，不要声称已安装。
```

豆包原生导入和脚本执行仍待客户端实测；公开可下载不代表豆包已安装。若豆包无法运行脚本，可按包内说明在本机运行，再回传结果。

## 功能与验收

- 全中文交互、PNG/PDF 图纸指引及 CSV 表头。
- MARD 配色；PNG、PDF、CSV 共用已确认的色号网格。
- 基于当前 PNG 展示上下文导出 PDF，保存历史版本。
- A4 整体预览、分页指南和施工页；提供标准版和大字版。
- 48 项本地自动测试与独立安装验证通过。

需要 Python 3.10+，macOS/Linux 或 Windows WSL。首次安装需要下载固定依赖。

```bash
cd kang-doubao-pindou
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python scripts/pindou.py doctor
```

完整操作请阅读 ZIP 内的 README.md。发布包不含用户原图、测试作品或凭据。

## 文件校验

大小：225619 字节。SHA256：

```text
d27cd0f47d287926993005ed7af71da6b46f5a4387cdb574e9b0082b2f5b6534
```
