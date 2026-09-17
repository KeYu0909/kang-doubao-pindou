# 永康玩AI · 拼豆助手 0.3.2

正式技能名 `kang-doubao-pindou`。交互及PNG/PDF指引、CSV表头已中文化；命令和色号保留原标识。本版在原工程继续修改，保留旧项目与成品。已实现本地工作流；豆包原生导入、脚本调用和图片附件交付仍待实测。无网站、服务端、收费图片API或凭据。


## 0.3.2：一键安装到豆包用户技能目录

新增包根目录 `install.py`：校验完整发布文件，复制到真实用户技能目录，在目标创建 `.venv` 并安装锁定依赖，最后运行 `doctor --repair`。已有健康环境直接复用；更新时备份被替换的代码，保留未收录的作品和其他用户文件。源码目录不使用软链接，源目录的 `.venv`、缓存、作品不会复制。

本版按本次提供的豆包宿主路径约定使用 `~/.doubao/agent_mode/workspace/.user_skills/`。不同豆包版本的实际路径须由宿主核实；这里不宣称它是所有版本唯一的扫描路径。

## 0.3.1：安装位置与新窗口入口

开始前检查真实源码及虚拟环境路径，临时安装明确提示迁移；`doctor` 不再把依赖就绪描述为持久安装成功。新增 `scripts/install_record.py`，在项目中保存安装位置，并在新窗口按记录检查，保留所有旧作品。文件保存、宿主技能注册、同项目新窗口访问分别验收；尚未实测豆包跨窗口行为。具体操作见[持久化安装](references/persistent-install.md)。

## 0.3.0：快速工作流

AI理解与建议 → 固定脚本执行 → 用户阶段确认。已有项目直接读取；无需重建或重新做旧作品。

- 图片刚上传先给建议，用户选择后再处理；每轮最多一次宿主图片编辑，有结果立即展示。
- `pixel --current` 自动选当前确认素材并返回预览和本地杂色分析；无需先运行status或填写版本号。
- `denoise --current --mode light|balanced` 本地清理；强力档必须指定 `--mode strong --max-colors 12`。支持色号/格子/区域保护。
- `route --current`识别明确的减色、去杂色、上一版、生成PNG与自然导出；仅减色从当前网格重算，保留之前清理效果。
- `doctor --repair`复用可用环境，只修复必要依赖。豆包技能发现使用本版真实目录安装，不使用`--link`代替。
- PNG单独展示并确认后，CSV/PDF各自按需生成、复用；两种PDF沿用同一网格。

见[快速命令与计时](references/fast-path.md)、[三档去杂色](references/cleanup.md)、[本轮验收与限制](reports/v3-acceptance.md)。旧版低级命令仍兼容；下方完整流程展示其用法，新对话优先使用`--current`。

## 从 GitHub 同步

仓库：https://github.com/KeYu0909/kang-doubao-pindou ，分支 `main`，技能目录为仓库根目录（留空或填 `.`）。根目录的SKILL.md与脚本、字体、色卡一起导入。原生导入与执行仍需在实际宿主核实。

## 开始前先检查持久化安装

0.2.1起将持久化安装提示提前到制图之前：先检查已有安装并复用；需要安装时，源码、依赖和作品都应落到宿主实际支持的持久存储中。不要先安装进 `/runtime`，等目录清空后再补救。操作与恢复步骤见[持久化安装说明](references/persistent-install.md)。

`/home/user/pindou-skill/`、`/opt/` 等位置可以作为解包来源或普通执行目录，不能作为本次约定的豆包发现入口；也不写入系统 `.skills/`。主目录可写或软链接存在，不代表能跨重置保存。无法核实保存范围时，应提前说明限制并安排宿主项目文件备份。

## 豆包安装

ZIP 内仅有一层 `kang-doubao-pindou/`。解压后在其中运行：

```bash
python3 install.py
```

默认将整个发布文件树**复制**到以下位置，最终必须能直接看到：

```text
~/.doubao/agent_mode/workspace/.user_skills/kang-doubao-pindou/SKILL.md
```

安装器从当前账号的主目录定位，不会创建缺失的扫描目录来假装安装成功。若报告目录不存在，先确认宿主确实使用该路径，再创建：

```bash
mkdir -p "$HOME/.doubao/agent_mode/workspace/.user_skills"
python3 install.py
```

若宿主明确提供了其他版本的真实 `.user_skills` 路径，可用 `python3 install.py --skills-dir /实际宿主工作区/.user_skills`。不能指定 `/runtime`、临时目录或系统 `.skills`；不会自动尝试多个猜测路径。

源码入口是实际目录，不能软链回解包位置。源 `.venv` 不复制、不搬动；在最终目录新建，目标已有可用环境则复用。已有 `.venv` 软链接或损坏环境会明确报错并保留，不能把指向临时环境的链接当成稳定依赖。首次安装可能需要联网；失败返回非零退出码，不报告成功。

更新重复运行同一条命令即可。被替换的发布文件备份在宿主工作区的 `pindou-install-backups/`，位于 `.user_skills` 外，避免被当成另一份技能扫描；不会删除原作品、未收录文件或旧环境。实际安装路径保存为目标 `INSTALLATION.json`，不等同于项目的 `pindou-install.json`。

成功后**重启对话并检查生效**。本地复制和依赖检查不证明豆包已扫描；新窗口应实际选择或调用技能，验证版本与保存范围，操作见[持久化与恢复](references/persistent-install.md)。

## 本机或其他宿主安装

本机或其他宿主可以自行选择稳定执行目录；这不代替豆包的扫描入口。需要 Python 3.10+、macOS/Linux（Windows用WSL），首次联网安装固定依赖，运行时不临时装包。

```bash
# 替换成宿主已确认支持持久保存的实际路径
cd /已确认的持久目录/kang-doubao-pindou
# 已有 .venv 时先执行 doctor --repair；通过就跳过下面两条安装命令。
# 以下命令用于首次安装，不在每次制图时重复执行。
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
.venv/bin/python scripts/pindou.py doctor
```

开发验收Python3.12.14；系统Python3.9不能运行。目录移动后请重建虚拟环境，不复用含旧绝对路径的pip启动脚本。升级见[迁移说明](references/migration.md)。豆包入口是否接受该ZIP必须实际核实，上传ZIP不代表已安装；若无法执行脚本，在本机运行并手动回传文件，记录manual-fallback。

## 从图片开始

以下 `WORK` 是用户作品目录，`EDIT_REV`、`PIXEL_REV`、消息引用都必须换成实际值；不要照抄占位确认。

```bash
WORK=/已确认的持久项目目录/拼豆作品
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
