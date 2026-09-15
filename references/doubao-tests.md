# 豆包v0.2第一轮实测：逐条发送，逐阶段停下

## 开始前

1. 解压完整技能ZIP。检查你的豆包客户端是否有自定义技能入口并接受标准SKILL.md目录；若有，按该入口实际指引导入，记录入口和真实结果。没有入口不要把普通上传ZIP称作“技能已安装”。
2. 检查能否执行Python3.10+、读写目录、展示本地PNG、返回真实下载附件、调用原生编辑工具。先运行doctor。首次依赖安装单独计时。
3. 若没有脚本执行能力：在本机安装，豆包负责对话和原生编辑，手动保存图片后导入脚本、回传预览。全程标记manual-fallback。
4. 使用你有权处理的猫照片或自制图片，记录真实可读输入；避免将个人照片放进公共技能ZIP。开始录屏或其他可核查计时。
5. 每个阶段提交记录t0；合格图片真正可看/下载记录t1，计入排队、工具等待、下载、校验和展示。用户思考时间不计。

## 可复制对话与通过条件

| 顺序 | 发送内容 | 核对条件 |
|---|---|---|
| 1 | “使用kang-doubao-pindou（永康玩AI · 拼豆助手）。先去掉这张猫图的背景，保留趴着的姿势、绿色眼睛和原来的毛色，只给编辑候选。” | 实际原图、一张候选、保留特征；没有pixel/pattern/CSV/PDF |
| 2 | “这次去背景并加一顶红色生日帽，姿态、眼睛、毛色不改，先给我看。” | 本轮最多一次宿主编辑调用，要求合并 |
| 3 | “帽子小一点，其他不改。” | 用上一张真实候选修改，旧版还在，新revision |
| 4 | “确认这张编辑图，进入78×78、最多18色的真实像素预览。” | 绑定edit确认，78行78列，<=18合法色号，透明空格和白豆区分 |
| 5 | “改成12色，其他参数沿用。” | 新pixel版本，<=12色、原尺寸/色板保留，不重复AI |
| 6 | “返回上一版18色。” | 使用rollback，恢复原文件哈希，不生成相似图 |
| 7 | “确认这版像素效果，只生成PNG。” | 绑定pixel确认；正式PNG有坐标、色号、图例；未导出CSV/PDF |
| 8 | PNG已实际展示后：“导出pdf” | 同轮绑定当前PNG确认并只导出PDF，不要求额外口令 |
| 9 | “这个PNG没问题，确认这一版，只下载CSV。” | 绑定PNG文件及版本；只生成CSV，准确颗数、备损分列 |
| 10 | “现在单独给我PDF。” | 从同网格导出，不读图识别；分页坐标连续；不额外重生成CSV |
| 11 | “PDF字号大一点，图案不改。” | 仅切换large布局产生另一份PDF，保留图案和PNG确认 |
| 12 | “再给我同一份PDF。” | 文件哈希及修改时间不变，复用现成文件 |
| 13 | “假设当前预览读取失败，请展示一次小图备用；备用也失败就告诉我未完成视觉检查。” | 初次失败一次备用；第二次失败明确incomplete，不声称已看过 |
| 14 | “我只想分析流程，不要生成图片。” | 不调用图片工具，不新建出图或导出操作 |
| 15 | “取消这次编辑，我选择已有的上一版。” | 取消token并选择版本；迟到结果不能覆盖当前选择 |
| 16 | “这是上一会话的完整工作目录，请核对状态和文件后继续。” | 读取真实state及历史文件；缺失时明确请求恢复，不能假记忆 |

每一步必须记录期望和实际。猫的眼睛、姿态、毛色、帽子是否保留，需要真实人类视觉判断，本地几何测试不验证这些。

## 新交互的分支复测

在真实展示的当前PNG上分别验证：“这张可以，下载用量清单”只CSV；“可以”只确认；“先不要导出PDF”不操作；“PDF和PNG有什么区别”只解释；“以后再导出”不操作；“只分析，不生成图片”不调图片工具。每个分支独立记录前后状态，不能拿已导出文件当本次新导出。

“眼睛改绿色后再导出”先修改与重新展示，不继承旧PNG确认。只有未确认像素图时请求PDF不跳步；像素已确认时先生成并实际展示PNG，等待选择。模拟未展示PNG/另一会话时没有回执则不自动确认。展示两个版本目标不明确时只问一个版本问题；“就用上一版导出PDF”核对真正旧文件和哈希。

用当前展示的2—3项菜单验证“1”“第二个”“按推荐来”和自然语言选项；换版本后旧数字必须失效。编辑/像素阶段展示确认并继续选项后，“可以”可继续该一步；PNG阶段不可猜测导出格式。更名后打开旧完整作品目录，核对原确认/历史文件仍可恢复导出。

PDF实物检查：第1页整体，第2页边界/页码/范围，施工从第3页；按左上原点读全局坐标，核对接缝与末行末列，标准/大字版切换不改图案。逐页检查而非只看第一页，不把页数等同拼板数。

## 记录模板（复制一份填写）

```json
{
  "client": "unknown",
  "client_version": "unknown",
  "entrypoint": "unknown",
  "account_entitlements": "unknown (do not record credentials)",
  "execution_environment": "unknown",
  "skill_version": "0.2.0",
  "zip_sha256": "fill actual",
  "input_description": "fill actual; no private image in public report",
  "input_sha256": "fill actual",
  "mode": "automatic-host / manual-fallback / unavailable",
  "stage": "edit / pixel / png / csv / pdf / revision",
  "user_request": "fill actual",
  "revision_before": "fill actual",
  "revision_after": "fill actual",
  "native_tool_name": "unknown",
  "native_tool_record": "actual tool record or unknown",
  "generative_call_count": "unknown",
  "retry_count": "unknown",
  "t_submission": "unknown",
  "t_tool_start": "unknown",
  "t_tool_end": "unknown",
  "t_file_readable": "unknown",
  "t_download_visible": "unknown",
  "e2e_seconds": "unknown",
  "install_seconds_separate": "unknown",
  "native_interrupt_supported": "unknown",
  "native_timestamps_supported": "unknown",
  "real_error": null,
  "delivered_file_and_sha256": "fill actual",
  "visual_quality": "not checked",
  "result": "pending",
  "notes": ""
}
```

判定：<=60秒且交付合格图=达标；>60秒合格图=有效但速度未达标；只给进度、报错、旧图或不合格图=不算成功出图。宿主无法计时/中断则填unknown或unsupported，禁止补造时间；不能承诺不受控工具超时后还能准时向用户发消息。

## 本轮已知结果

真实豆包测试：**未执行**。无真实猫图评测、无创意编辑效果评测、无原生工具中断实测、无豆包60秒达标结论。代码自动测试和合成图片本地性能见reports/。
