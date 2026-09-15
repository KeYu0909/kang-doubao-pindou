# 来源、版本、许可与复用范围

核对日期：2026-09-15。以下结论基于实际下载并读取的源码、LICENSE和资源说明；未执行参考项目的安装脚本、线上部署或图片API。

| 项目 | 实际commit | 结论与范围 |
|---|---|---|
| [kuizuo/pin-dou](https://github.com/kuizuo/pin-dou/tree/e94193cbdebe9ea4d774ca62025ef46f0ef0d281) | e94193cbdebe9ea4d774ca62025ef46f0ef0d281 | 读取skills/image-to-pindou/SKILL.md、scripts/generate.mjs、self-test.mjs、package.json与色卡目录。仓库未发现明确代码LICENSE，package未授权；不复制源码、图片、色卡到分发包。 |
| [wuZHeBoy/bead-pattern](https://github.com/wuZHeBoy/bead-pattern/tree/146543577e4641c5723e794d00cce6be7f41dc63) | 146543577e4641c5723e794d00cce6be7f41dc63 | MIT明确。仅复用generate.py的srgb_to_lab、ciede2000、to_grid到scripts/pindou/colors.py，保留许可。其他流程独立实现。 |
| [maxcleme/beadcolors](https://github.com/maxcleme/beadcolors/tree/f97ff4283d03cef5cd7e1071a86f5892e0c0c61b) | f97ff4283d03cef5cd7e1071a86f5892e0c0c61b | MIT明确。直接从raw/mard.csv转换291条色号/RGB至assets/mard.json，不经许可不明的副本。保留上游许可。 |

pin-dou实际代码中，`--size`表示最长边；`writeOutputs`同时输出pattern.svg、pattern.png、bom.csv和项目备份；脚本还包含openai/gemini调用。这些现有行为不符合本项目逐阶段确认、精确宽高和无未经核实豆包API的约束，因此不能直接套用现有CLI。

bead-pattern的色卡说明引用另一个AGPL项目并主张事实数据可自由使用；本轮不依赖这一许可解释，不复制其色卡、映射文件、照片、示例成品或字体。只复用其明确MIT授权的三个算法函数。新阶段管理、背景连通处理、配色限制、网格验证、PNG/CSV/PDF渲染均在本项目实现，未复制pin-dou代码。

MARD品牌色号是所引用仓库的社区映射，已检查唯一性、RGB值和291条数量；不是厂商校准认证。来源中RGB为近似显示色，不伪造额外品牌或未经核实色号。自有用户色卡必须明确source/license并由用户核实，脚本只能检查格式和一致性。

## 依赖

| 依赖（固定版本） | 用途 | 许可 |
|---|---|---|
| PyYAML 6.0.2 | 技能frontmatter自动校验 | MIT |
| numpy 2.2.6 | 色彩空间、CIEDE2000和数组 | BSD-3-Clause；其wheel原生组件另有随包许可 |
| Pillow 11.3.0 | 图片读取、裁切、像素和PNG | MIT-CMU |
| reportlab 4.4.3 | 矢量PDF | BSD-3-Clause |
| charset-normalizer 3.4.3 | reportlab依赖 | MIT |
| pypdf 6.0.0 | PDF解析和逐页文字核对 | BSD-3-Clause |
| pypdfium2 4.30.0 | PDF实际渲染检查 | Apache-2.0或BSD-3-Clause；PDFium及第三方部件随包通知 |

requirements.txt固定直接和传递依赖；requirements.lock包含PyPI所有对应发行文件SHA256，以`--require-hashes`安装。不会运行时自动下载模型或依赖。详细来源见dependency-sources.json和licenses/中取得的许可原文。分发ZIP不包含运行依赖二进制或虚拟环境；用户从PyPI安装的发行包携带自身许可。中文指引使用下面单独声明的开源字体子集，色号继续用Pillow默认字体/ReportLab标准PDF字体。

## 结构参考

- [Agent Skills specification](https://agentskills.io/specification)：标准SKILL.md frontmatter、同名目录、references/scripts/assets。
- [Using scripts](https://agentskills.io/skill-creation/using-scripts)：独立可运行命令、固定依赖和明确错误。
- [Evaluating skills](https://agentskills.io/skill-creation/evaluating-skills)：区分结构/程序测试与真实任务效果评估。

技能正文、说明、脚本及自建几何测试数据按根LICENSE分发；所有第三方许可保留在licenses/。参考仓库研究副本只在本地.research中，不进入ZIP。


## 中文界面字体

中文指引使用[Noto CJK官方仓库](https://github.com/notofonts/noto-cjk)的NotoSansSC-VF.ttf，固定提交与源/子集SHA256见[font-source.json](font-source.json)。原字体按[SIL OFL 1.1](https://raw.githubusercontent.com/notofonts/noto-cjk/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/LICENSE)允许随软件分发与嵌入；许可原文为licenses/noto-cjk-OFL.txt，原版权信息保留于字体name表。

构建时用fontTools4.60.2截取界面所需字符及ASCII，固定字重400，并将衍生字体改名Kang Pindou UI。运行时不需要fontTools，不下载字体，不依赖本机私有字体。维护中文文案时需运行scripts/build_ui_font.py重新构建子集并检查缺字；完整源字体及构建依赖只保留在.research，不入ZIP。该字体本身遵循OFL，不改为项目MIT许可。

## 0.3.0 本轮四个指定参考项目

2026-09-15重新取得公开源码并只读研究，研究副本在runs/research-v3，打包白名单排除整个runs。以下新模块全部自行实现，没有引入这些仓库的代码、色卡、图片或字体。

| 参考源码 | 当前核查 | 采用的设计思路与分发范围 |
|---|---|---|
| [pin-dou / generate.mjs](https://github.com/kuizuo/pin-dou/blob/main/skills/image-to-pindou/scripts/generate.mjs) | 未找到明确仓库源码LICENSE；GitHub license为null。色卡引用其他上游，不能由引用推出整包许可。 | 研究quantize、cleanTinyRegions、边缘背景填充、网格渲染；不复制代码和色卡。 |
| [perler-beads-ai](https://github.com/liangdabiao/perler-beads-ai) | 根LICENSE为Apache-2.0；内嵌色卡/示例图没有在此次核查中取得独立来源授权链。 | 阅读floodFillUtils.ts、pixelation.ts、page.tsx的近色合并/排除重映射/边缘擦除。四邻接区域分析和颜色排除作为通用算法思路，未复用源码或资源。 |
| [mard-bead-generator](https://github.com/Archmays/mard-bead-generator) | 根LICENSE为MIT（2026 Archmays）；色卡同步有独立数据来源，未据此新增分发。 | 阅读regionCleanup.ts和App.tsx：平衡/忠实/最少色策略、保护边缘、取消保留旧结果。本项目仍为独立三档清理与既有revision/epoch结构。 |
| [perler-beads-skill](https://github.com/liangdabiao/perler-beads-skill) | GitHub license为null，未找到明确根LICENSE。色卡来源许可未独立证实。 | 阅读pattern.js的limitColors/CSV和generate.js的max-colors；不复制代码/内嵌colorData。 |

本轮只继续使用此前已核验的maxcleme/beadcolors MIT社区MARD映射、现有MIT色差函数和OFL字体；没有借“事实色号”推定未授权的整理数据可再分发。无需额外添加未复用项目的许可证文件。独立实现的小区域规则、强力保护冲突和JSON状态接口均纳入本项目MIT许可。
