# 快速命令与自动状态

从已验证的持久安装目录运行；以下 `PY`、`WORK` 必须换成真实绝对路径。`CHAT`、`MSG` 是当前会话和真实用户消息引用，不能照抄占位值伪造展示或确认。

```sh
PY=/实际持久目录/kang-doubao-pindou/.venv/bin/python
WORK=/实际持久项目目录/我的拼豆
# 首次或恢复时检查；正常对话不重复检查。
"$PY" scripts/pindou.py doctor --repair
# 宿主已确认持久安装存在、只缺临时链接时：
"$PY" scripts/pindou.py doctor --repair --link /runtime/skills/kang-doubao-pindou
```

收到图片但没有明确处理要求时，先看图给建议并等待用户选择，不执行以下图像命令。

用户选定要求后 `init --project "$WORK" --input /真实原图.png --source '本次上传' --preserve '绿色眼睛'` 保存原图。要编辑时：

```sh
"$PY" scripts/pindou.py begin --project "$WORK" --current --kind edit \
  --request '去背景并加红色帽子，保持姿态和眼睛' --preserve '绿色眼睛'
```

返回 operation_id、source_file、source_sha256；宿主从返回值直接取用，不先 status 或猜版本号。`claim-call --current --mode host` 后，调用实际图片编辑工具一次。`edit --current --input /工具结果.png --origin host --based-on-sha 返回的source_sha256` 导入。没有工具不能记成 host 调用，可接受用户提供素材并如实记录 manual。

## 每次展示后再记录

命令生成图后立即发送完整图和轻量预览给用户，然后记录：

```sh
"$PY" scripts/pindou.py present --project "$WORK" --current \
  --artifact candidate --conversation "$CHAT" --message-ref "$DELIVERY_MSG"
"$PY" scripts/pindou.py route --project "$WORK" --current \
  --conversation "$CHAT" --message '确认原图' --message-ref "$MSG"
"$PY" scripts/pindou.py pixel --project "$WORK" --current --width 78 --height 78 --max-colors 18
```

像素命令直接返回预览路径、尺寸/实际色数/颗数、小区域统计与建议，无需追加 inspect。详细区域保存为 analysis.json；只在定位指定区域时读取。预览交付后 `present --artifact preview --current ...`。展示脚本返回的4项去杂色菜单后，可把 `analysis.options` 写为 JSON 文件，用 `offer --current --options /实际菜单.json ...` 绑定；数字选项在版本变化后失效。

所有简单请求用同一入口：

```sh
"$PY" scripts/pindou.py route --project "$WORK" --current \
  --conversation "$CHAT" --message '轻度去杂色' --message-ref "$MSG"
```

支持“平衡去杂色”“强力简化到12色”“颜色减到12色”“18色改12色”“保持现在”“还是上一版”“生成PNG”“导出PDF”“PDF字大一点”“下载清单”。修改后的新预览必须再次展示并确认，不能沿用上一版确认。

低级确定性命令（仅在用户已明确授权对应动作时）：

```sh
"$PY" scripts/pindou.py denoise --project "$WORK" --current --mode light
"$PY" scripts/pindou.py denoise --project "$WORK" --current --mode balanced --protect /真实保护区.json
"$PY" scripts/pindou.py denoise --project "$WORK" --current --mode strong --max-colors 12
"$PY" scripts/pindou.py pixel --project "$WORK" --current --max-colors 12
"$PY" scripts/pindou.py confirm --project "$WORK" --current --stage pixel --message '用户真实确认原话'
"$PY" scripts/pindou.py png --project "$WORK" --current
```

PNG交付后 `present --artifact pattern --current ...`；用户再说“导出PDF”，route在同一命令里确认PNG并生成PDF。仅解释或否定不导出。已明确确认PNG的手动流程可用 `export --current --format csv|pdf`。相同参数重复请求复用文件；PDF失败不影响CSV/PNG。

## 自动状态与错误

`--current` 和原有 `--base/--revision` 二选一。begin、claim-call、edit、cancel、pixel、denoise、confirm、png、export、present、offer、preview-result、record-delivery可使用当前状态；route本来就按当前会话展示上下文选版本，`--current`不绕过版本歧义和展示检查。rollback仍用真实历史ID，常见“上一版”由route自动解析。操作token用于一次宿主编辑的输入绑定和取消，保留原来的真实token协议。

普通动作不需外置status。每次写入仍检查epoch，执行期间版本改变则拒绝覆盖，不悄悄对另一张图执行用户确认。主要错误返回 `ok/code/message/error`。用户消息含未知复合要求时返回 `status=modification_required` 或 `needs_input`，由宿主只处理必要的一步，不尝试把所有自然语言硬解释成固定动作。

## 分段计时

本地命令自动记录 local_command，pixel_pipeline、artifact_pipeline细分状态、处理、渲染和校验；去杂色记录实际修改统计。宿主需依据实际工具/消息时间戳补充：

```sh
"$PY" scripts/pindou.py record-stage --project "$WORK" \
  --phase image_tool --scope doubao --started-at 真实开始时间戳 \
  --ended-at 真实结束时间戳 --evidence '实际工具调用引用'
```

phase可为ai_thinking、image_tool、preview_delivery、post_script_wait。不能用估计代替实际时间。`record-delivery --current`继续记录提交到可见交付的完整耗时。没有宿主时间戳就保留未知。
