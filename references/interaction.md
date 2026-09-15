# 上下文交互协议 v0.2

## 宿主职责

先实际展示结果并提供文件，再present，不能在生成后自动写展示回执。conversation必须是当前真实会话标识；message-ref使用宿主实际消息ID/记录引用，不存在ID时写可追溯简短引用，不能虚构工具成功记录。present验证版本及文件哈希，仅代表宿主对实际交付的声明，不能自动证明用户看过或形成身份认证。

```bash
.venv/bin/python scripts/pindou.py present --project "$WORK" --revision 当前ID \
  --conversation 当前会话ID --artifact pattern --message-ref 实际PNG交付引用
.venv/bin/python scripts/pindou.py route --project "$WORK" --conversation 当前会话ID \
  --message '导出pdf' --message-ref 实际用户操作引用
```

artifact为candidate/preview/pattern。展示多个版本且指向不清，present加 `--ambiguous`，不默认选择最后一个。明确历史目标可route加 `--revision 真实ID`；“就用上一版导出PDF”沿真实parent_revision找上一个有正式PNG的版本，仍要求该版本本会话实际展示。不更改当前选择，也不把最新图网格套到历史确认。

## 推荐与选项

先向用户展示与JSON内容一致的文本选项，再offer。例：当前像素预览后展示“1. 继续生成PNG（推荐，保留这版效果） 2. 调整细节”。JSON存到宿主实际文件：

```json
[
  {"label":"继续生成PNG","action":"png","recommended":true,"aliases":["继续图纸"]},
  {"label":"调整细节","action":"adjust"}
]
```

```bash
.venv/bin/python scripts/pindou.py offer --project "$WORK" --revision 当前ID \
  --conversation 当前会话ID --options /实际选项.json
.venv/bin/python scripts/pindou.py route --project "$WORK" --conversation 当前会话ID \
  --message '按推荐来' --message-ref 实际用户引用
```

最多3项/1个推荐；action为confirm/pixel/png/export_pdf/export_csv/adjust/rollback。pixel的args可指定width/height/max_colors/palette/reserve/sampling；export_pdf的args.layout为standard/large。推荐不会扩大范围。菜单绑定revision/stage/epoch且使用后失效，新的present也清空菜单。旧“1”、过期推荐不得重放。

## 路由结果

| 返回status | 宿主下一步 |
|---|---|
| file_ready | 交付真实文件；若是候选/预览/PNG，交付后再present |
| confirmed | 简短确认当前版本，不自行导出 |
| png_needs_presentation | 只有已确认像素时可先生成PNG；立即真实展示，等新的用户选择 |
| needs_presentation | 提供指定版本的真实文件/预览，记录present，不补造用户意图 |
| needs_input | 最多问返回的一个聚焦问题 |
| modification_required | 按用户要求进入修改/重新配色，展示新版本；不得直接导出 |
| no_action / explanation | 不生成；结合用户具体问题回答，不机械照搬默认说明 |
| restored | 展示已恢复的真实历史文件，重新建立当前语境 |

确定性规则保守处理否定、未来、疑问与修改，再识别简单意图；没有独立大模型调用。复杂自然语言未必被规则覆盖，宿主可根据本轮已有意图执行同样的阶段操作，但不能绕过展示、版本、修改拦截。修改请求只记录pending并交给宿主处理，不假装脚本已把眼睛改绿。若取消修改须真实cancel/rollback或完成新版本，不手改确认。

确认记录绑定project_id/revision_id/grid_sha256/artifact_sha256、source(explicit/contextual_export)、message_ref、conversation、confirmed_at和最多180字符的真实确认摘要。只保留必要短语；不额外保存整段聊天。旧确认字段按迁移规则兼容。

route返回intent/state_check/confirmation/export_or_render及导出细分timings；底层artifact_pipeline另记录pagination/drawing/validation/file_delivery。重复阶段名以export_区分。JSON中的file_delivery仅表示本地文件注册返回，实际用户下载交付要另用record-delivery记录。不能据此解释旧截图的36秒来源。
