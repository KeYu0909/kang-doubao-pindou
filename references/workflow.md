# 命令、数据与错误处理

## 数据约定

- `state.json`: schema_version=1，project_id，skill_version，current_revision，stage，epoch，revisions，operations，preview_reads。
- 编辑版本：revision_id、parent_revision、输入来源/哈希/模拟标记、编辑要求、保留特征、裁切/背景参数、候选与原始文件、每阶段确认记录。
- 像素版本：edit_revision、完整网格、色板快照、处理参数、grid_sha256、文件表、确认记录。网格 `cells[y][x]` 中 `null` 为不放豆，字符串为真实色号。
- 每个文件：相对路径、SHA256、revision_id、grid_sha256、格式参数、ready状态和创建时间。失败不注册ready文件；错误另记events.jsonl。
- 确认包含阶段、版本、网格哈希、PNG文件哈希（PNG阶段）、时间及必要短确认摘要；不存在全局confirmed布尔变量。
- v0.2新增可选interaction（会话展示/菜单）、preferences（PDF布局）、pending_modification；兼容原schema1。详见[交互协议](interaction.md)和[迁移说明](migration.md)。
- 阶段：EDIT_PENDING_CONFIRMATION → EDIT_CONFIRMED → PIXEL_PENDING_CONFIRMATION → PIXEL_CONFIRMED → PNG_PENDING_CONFIRMATION → PNG_CONFIRMED。每次修改创建新版本；历史确认只属于历史版本。

状态写入采用文件锁与原子替换；耗时渲染在暂存目录进行，提交前检查epoch和当前选择。即使先切走再切回同一ID，旧操作也因epoch变化失效。宿主操作token还需pending且未消费，取消后不能迟到导入覆盖。

这是工作流约束，拥有工作目录写权限的宿主仍可手工修改文件或伪造确认；不将其描述为认证安全边界。

## 普通编辑

```bash
.venv/bin/python scripts/pindou.py begin --project "$WORK" --kind edit \
  --base 当前版本ID --request '只裁掉明确指定边框，其他保留'
# 取返回的 operation_id；left top width height 均为原图像素
.venv/bin/python scripts/pindou.py edit --project "$WORK" --operation 操作ID \
  --crop 0 0 1000 1000
```

EXIF方向先规范化，裁切坐标针对规范化后的图片。越界明确拒绝：1440×1920输入，`0 640 1440 1440`超出底边，不补黑、不假成功。有效裁切如`0 480 1440 1440`会记录裁切参数。没有用户的明确裁切要求不要自行裁掉主体。

明确纯色背景可 `--remove-edge '#FFFFFF' --tolerance 12`，只对与图片边缘连通的近似颜色洪水填充，不把封闭的白色主体内部抹掉。不适用于复杂照片的语义抠图；白色主体接触白背景仍可能被去掉，需用户审阅。透明图无需调用图片工具。

## 像素参数

`pixel --width N --height N --max-colors N --palette /实际色卡.json --reserve 真实色号`

初次缺参使用78×78、MARD、18；修改时缺省沿用当前像素版本的尺寸/色板/颜色上限/采样/保留色号。脚本JSON显示实际采用参数，宿主须向用户展示，不能默默改参数赶时限。

等比contain补透明边，记录原尺寸、缩放尺寸、四侧补边。默认BOX面积采样；已有像素图可指定`--sampling nearest`。CIEDE2000匹配后按实际用量优先选色，按上限重新映射；指定`--reserve`优先保留该真实色号。色数降低仍可能改变眼睛等小特征，不承诺语义识别；本版不自动清除小色块。`--reserve`保留色板可用项，不保证每项一定会占用格子。

自有色卡结构参见assets/mard.json，需name/source/license/colors；code为1..5个ASCII字母数字下划线或连字符（至少一个字母，避免与坐标混淆），hex为#RRGGBB。品牌必须有实际依据，本脚本格式校验不等于确认自定义品牌真实性。

## 查看失败

宿主实际尝试展示后再记录，禁止用脚本的文件解码代替视觉检查：

```bash
.venv/bin/python scripts/pindou.py preview-result --project "$WORK" \
  --revision 当前版本ID --outcome fail
```

第一次fail返回小图fallback路径，只尝试一次；第二次fail标为incomplete并stop，不再自动重试。success仅代表宿主报告查看成功，不创建用户确认。需要调整/修复后可新建版本重新审阅。

## 时间与取消

全局参数放子命令前，例如 `pindou.py --budget-seconds 60 --submitted-at 真实UNIX秒 pixel ...`。整个本地命令包含导入模块、渲染和校验，共用剩余预算；独立子步骤没有各自新增60秒。`begin`产生的宿主操作记录有启动时间；宿主图片调用所花时间需要在后续命令传入真实阶段提交时间，或在record-delivery中完整计入。

`cancel --operation ID`仅关闭后续导入授权，不假装中止豆包原生工具；豆包是否实际支持中断未知。自有进程超时通过POSIX进程组SIGKILL终止并回收。中断的暂存数据不会成为当前版本。极端断电/进程在文件夹移动与状态提交之间被杀，可能留下未登记目录：保留文件、检查state和校验结果，必要时选新工作目录恢复，勿手动补确认或覆盖已有成品。

实际交付后记录：

```bash
.venv/bin/python scripts/pindou.py record-delivery --project "$WORK" \
  --revision 当前版本ID --artifact pattern --scope doubao \
  --user-submitted-at 真实提交时间戳 --delivered-at 真实可下载时间戳 \
  --quality qualified --evidence '实际工具记录或录屏时间依据'
```

命令字段不能用示例数字当真实证据。手动传文件用manual-fallback，不能统计为自动豆包链路。时间未知则在实测模板写unknown，不猜测。合格与否由真实审阅决定，文件生成成功不自动视为内容合格。

## 常见错误

- EDIT_NOT_CONFIRMED / PIXEL_NOT_CONFIRMED / PNG_NOT_CONFIRMED：先核实真实展示与用户意图；当前已展示PNG的明确导出请求可经route同轮确认导出，无需口令。只有像素图时不能跨过PNG展示。
- STALE_BASE / STALE_RESULT / OPERATION_STALE_OR_CLOSED：用户已改变选择，保留当前版本；新操作重新读取status。
- DEPENDENCY_ERROR：安装锁文件一次后doctor，不在循环中临时安装。
- INVALID_IMAGE / MISSING_FILE / CORRUPT_FILE：要求恢复真实文件；不得重建相似图冒充历史图。
- TIMEOUT：本轮无成功交付结论；先status/validate核实，不自动重试生图。
- PDF单独失败：保留PNG和CSV，可仅重试明确请求的PDF，不重绘图案。
