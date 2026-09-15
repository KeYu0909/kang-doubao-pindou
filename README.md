# 永康玩AI · 拼豆助手 0.2.0

正式技能名 `kang-doubao-pindou`。交互及PNG/PDF指引、CSV表头已中文化；命令和色号保留原标识。本版在原工程继续修改，保留旧项目与成品。已实现本地工作流；豆包原生导入、脚本调用和图片附件交付仍待实测。无网站、服务端、收费图片API或凭据。

## 从 GitHub 导入

仓库：https://github.com/KeYu0909/kang-doubao-pindou

在技能发布页面选择“从 GitHub 导入”，填写上面的仓库地址，分支选择 `main`，技能目录选择仓库根目录（`.` 或留空）。根目录包含 `SKILL.md`，其余脚本、色卡、字体和说明与之一起导入。实际导入与脚本执行需在宿主端验收。

完整发布包：[下载 v0.2.0 ZIP](https://github.com/KeYu0909/kang-doubao-pindou/releases/download/v0.2.0/kang-doubao-pindou.zip)。历史 v0.2.0 标签的自动源码包只有旧分发页；同步请使用 `main`。

## 安装

解压 `dist/kang-doubao-pindou.zip`，得到完整 `kang-doubao-pindou/`。需要 Python 3.10+、macOS/Linux（Windows用WSL），首次联网安装固定依赖，运行时不临时装包。

```bash
cd /你的路径/kang-doubao-pindou
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python scripts/pindou.py doctor
```

开发验收Python3.12.14；系统Python3.9不能运行。目录移动后请重建虚拟环境，不复用含旧绝对路径的pip启动脚本。升级见[迁移说明](references/migration.md)。豆包入口是否接受该ZIP必须实际核实，上传ZIP不代表已安装；若无法执行脚本，在本机运行并手动回传文件，记录manual-fallback。

## 从图片开始

以下 `WORK` 是用户作品目录，`EDIT_REV`、`PIXEL_REV`、消息引用都必须换成实际值；不要照抄占位确认。

```bash
WORK=/你的路径/拼豆作品
.venv/bin/python scripts/pindou.py init --project "$WORK" \
  --input /真实原图.png --source '本次用户上传' --request '保留主体，去掉背景'
```

init只是保存原始图和候选，不代表去背景已完成。按[编辑导入协议](references/doubao-adapter.md)或[普通编辑命令](references/workflow.md)完成实际要求。展示候选后记录：

```bash
.venv/bin/python scripts/pindou.py present --project "$WORK" --revision EDIT_REV \
  --artifact candidate --conversation 当前会话ID --message-ref 实际候选交付消息ID
# 以下低级命令仅在已经收到该版本真实明确确认时运行
.venv/bin/python scripts/pindou.py confirm --project "$WORK" --revision EDIT_REV \
  --stage edit --message '替换为用户真实确认原话'
.venv/bin/python scripts/pindou.py pixel --project "$WORK" --base EDIT_REV \
  --width 78 --height 78 --max-colors 18
.venv/bin/python scripts/pindou.py inspect --project "$WORK"
```

像素结果来自真实网格。默认MARD社区色卡是近似RGB映射，采购前核对实物色卡；空格null不是白豆。宽高1..192；参数确定后沿用。只减色用 `pixel --base PIXEL_REV --max-colors 12`，产生新版本并重用已保存输入，不再生图。

像素预览真实展示、获得确认后，`confirm --stage pixel`，再 `png --project "$WORK" --revision PIXEL_REV`。正式PNG与网格一致。提供返回的完整PNG与轻量预览，随后记录展示回执：

```bash
.venv/bin/python scripts/pindou.py present --project "$WORK" --revision PIXEL_REV \
  --artifact pattern --conversation 当前会话ID --message-ref 实际PNG交付消息ID
# 用户这时说“导出pdf”，同一个命令完成版本确认和PDF导出
.venv/bin/python scripts/pindou.py route --project "$WORK" --conversation 当前会话ID \
  --message '导出pdf' --message-ref 实际用户消息ID
```

无需固定口令。不能在用户尚未看到PNG时伪造present。自然确认、推荐/数字选项、修改和历史版本用法见[交互协议](references/interaction.md)。脚本不保存整段聊天，只保留必要消息引用和短确认语义。

PDF默认A4标准清晰版：整体预览、分页指南、施工页。`route --message '给我大字施工版'` 可换布局并保存偏好。相同布局直接复用。已有明确PNG确认的手动工作流可直接：

```bash
.venv/bin/python scripts/pindou.py export --project "$WORK" --revision PIXEL_REV --format pdf --layout standard
.venv/bin/python scripts/pindou.py export --project "$WORK" --revision PIXEL_REV --format pdf --layout large
# 仅在另有用量清单请求时执行
.venv/bin/python scripts/pindou.py export --project "$WORK" --revision PIXEL_REV --format csv
```

CSV默认无备损，`--spare-percent 10` 增加独立备损列。PDF不额外输出CSV或采购页。排版区域不等于拼板，未配置豆距不是1:1模板。`--cell-pt 14..24`保留低级兼容入口，但不能覆盖字体最小可读要求，建议使用两种布局。参数、长色号限制见[PDF说明](references/pdf-layout.md)。

## 恢复、测试、打包

```bash
.venv/bin/python scripts/pindou.py status --project "$WORK"
.venv/bin/python scripts/pindou.py validate --project "$WORK"
.venv/bin/python scripts/pindou.py rollback --project "$WORK" --revision 真实历史ID
.venv/bin/python scripts/run_tests.py
.venv/bin/python scripts/pdf_benchmark.py --out runs/pdf-review-new
.venv/bin/python scripts/benchmark.py --synthetic-confirmations --out runs/bench-new
.venv/bin/python scripts/package_skill.py
.venv/bin/python scripts/verify_package.py --zip dist/kang-doubao-pindou.zip
```

基准使用程序生成几何图与明确标识的模拟确认，不要对真实用户作品运行自动确认。状态和成品位于作品目录，日志为events.jsonl。普通错误退出2、超时124；缺失/损坏历史文件需恢复真实文件，不重建相似图。

包按白名单收录代码、许可、色卡和报告，排除用户图、runs、旧基线、缓存、虚拟环境、密钥和字体。每个文件附SHA256清单。干净目录验收会新建环境、装锁定依赖、跑测试及模拟CLI；所有本地耗时不代表豆包端到端时间。真实测试从[豆包测试指南](references/doubao-tests.md)开始。

中文字体子集及许可见[来源说明](references/sources.md)。公开ZIP包含合法开源字体，不含私人字体；更新文案时需重新构建字形子集。
