# SenseNova-U1.5 引导式局部编辑融合工作流

本工作流对应 SenseNova-U1.5 官方最佳实践中的三个案例：

- 框选引导的文字风格重塑
- 局部文字替换
- 标记引导的高端复古风格改造

参考：[SenseNova-U1.5 最佳实践（中文）](https://github.com/OpenSenseNova/SenseNova-U1/blob/main/docs/u1.5_best_practices_CN.md)

## 为什么可以融合

三个案例使用同一条图像编辑链路，区别只在编辑指令：

| 案例 | 定位方式 | 核心约束 | 输出清理 |
|---|---|---|---|
| 框选文字风格重塑 | 输入图中的红色定位框 | 文字逐字不变，保留行数、位置和版式，只改字形风格 | 删除定位框 |
| 局部文字替换 | 对区域的空间与语义描述 | 明确写出原文和新文，只替换目标文字，继承原字体与排版 | 有引导标记时删除 |
| 标记引导风格改造 | 输入图中的框线、圆圈、箭头和手写说明 | 逐项执行物件修改，并统一整体风格 | 删除全部标记和说明文字 |

这里没有额外的 bbox、mask 或第二个图像参数。**框线、箭头和手写文字是输入图像的一部分**，和原图一起由 `Load Image` 直接连接到 `SenseNova Conditioning.Image-1`。提示词节点负责告诉模型如何解释并擦除这些引导元素。

融合后的数据流为：

```text
Load Image ──────────────────────────────→ SenseNova Conditioning.Image-1
SenseNova Guided Edit Prompt ───────────→ SenseNova Conditioning.prompt
SenseNova Loader.MODEL ─────────────────→ SenseNova Conditioning.model

Conditioning 三路条件 → SenseNova Dual Guider → SamplerCustomAdvanced
SenseNova Loader.VAE ─────────────────────────→ VAE Decode → Save Image
```

工作流文件：[`workflows/SenseNova 引导式局部编辑.json`](../workflows/SenseNova%20引导式局部编辑.json)

## 使用步骤

1. 将工作流 JSON 拖进 ComfyUI。
2. 在 `Load Image` 上传原图。框选或标记类任务需上传已经画好框线、箭头和说明的图片。
3. 在 `SenseNova Guided Edit Prompt` 选择模式并填写相应字段。
4. 在 `EmptyHiDreamO1LatentImage` 设置输出宽高。保持接近输入图宽高比，并使用 32 的倍数。
5. 在 `SenseNova Loader` 重新选择本机 checkpoint，然后运行。

工作流默认使用官方图像编辑参数：Euler、50 steps、timestep shift 3、text CFG 4、image CFG 1、cfg norm `none`。为优先保证精确文字和局部保持，没有连接 8-step LoRA。

## 框选引导的文字风格重塑

输入图准备：用醒目的细框完整圈住目标文字，但尽量不要压住字形；框外内容不要做其他涂画。

节点字段建议：

- `mode`：`框选文字风格重塑`
- `edit_target`：`红色定位框内的大号白色文字`
- `original_text`：

  ```text
  BLOCK
  HOUSEHOLD
  NOISE
  ```

- `replacement_text`：留空
- `style_goal`：`复古海报式字体；加入旧化印刷、轻微噪点、磨损墨边、轻微褪色，以及融入字形的撕纸纹理；匹配原海报的黑白单色设计。`
- `preserve`：`保持其他耳机、图标、图示和周围文字不变。`

官方案例是约 2:3 的竖图，可先用 `1376 × 2048`。这里最重要的是把文字逐行写入 `original_text`；节点会自动补上“逐字保持、保持行数与版式、移除定位框”的约束。

## 局部文字替换

官方案例没有画定位框，而是通过“左下角深蓝色矩形信息栏”定位。边界清晰时优先使用这种空间加语义描述，可以少一次清理标记的压力。

节点字段建议：

- `mode`：`局部文字替换`
- `edit_target`：`左下角深蓝色矩形信息栏`
- `original_text`：

  ```text
  JUNE 15 -
  JULY 30, 2024
  URBAN GALLERY
  123 CREATIVE WAY
  ARTSVILLE, USA
  ```

- `replacement_text`：

  ```text
  AUGUST 10 -
  SEPTEMBER 28, 2024
  METRO MUSEUM
  456 DESIGN ROAD
  CREATIVITY CITY, UK
  ```

- `style_goal`：留空，本模式不使用
- `preserve`：`保持原有白色与粉色字体样式、对齐方式和版式；其他海报元素及文字不变。`

可先用接近原图比例的 `1600 × 2016`。原文和新文的换行应表达想要的对应行结构，模型更容易同时完成准确替换和排版保持。

## 标记引导的高端复古风格改造

输入图准备：使用不同颜色的框线、圆圈和箭头连接对象与简短说明。标记应清晰但不要大面积遮挡物件，否则模型需要猜测被遮挡内容。

节点字段建议：

- `mode`：`标记引导风格改造`
- `edit_target`：`逐项执行图中四处标记：陶瓷罐改为彩绘珐琅瓷罐，研磨器改为精致铜制研磨器，茶壶改为金盖水晶瓶，并在托盘角落放置几块方糖。`
- `original_text`：留空，本模式不使用
- `replacement_text`：留空，本模式不使用
- `style_goal`：`more luxurious, high-end vintage aesthetic；材质精致、华丽但克制，并保持统一的高端复古色调。`
- `preserve`：`保持原图构图、视角、桌面场景、托盘位置和光影关系；只修改标记指向的物件及必要的整体质感。`

官方案例是 16:9 横图，可先用 `2048 × 1152`。节点会自动强调逐项读取标记，以及在输出中完整擦除定位框、虚线框、圆圈、箭头和说明文字。

## 调整建议

- 文字有错字时，先固定 seed 重试，并把 `original_text` / `replacement_text` 按目标行数精确换行；不要同时增加无关风格要求。
- 框线残留时，在 `preserve` 末尾再次写明具体颜色和位置，例如“最终图不得保留红色矩形框”。
- 未标记区域变化过大时，把 `preserve` 写得更具体；`image CFG` 仍建议先保持官方默认 1。
- 横竖图切换只改 latent 的宽高，不需要更换工作流或 Conditioning 输入。
