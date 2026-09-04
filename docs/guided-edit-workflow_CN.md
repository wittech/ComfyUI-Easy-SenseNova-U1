# SenseNova-U1.5 引导式局部编辑融合工作流

本工作流对应 SenseNova-U1.5 官方最佳实践中的三个案例：

- 框选引导的文字风格重塑
- 局部文字替换
- 标记引导的高端复古风格改造

参考：[SenseNova-U1.5 最佳实践（中文）](https://github.com/OpenSenseNova/SenseNova-U1/blob/main/docs/u1.5_best_practices_CN.md)

工作流文件：[`workflows/SenseNova 引导式局部编辑.json`](../workflows/SenseNova%20引导式局部编辑.json)

## 工作流结构

三类任务共用同一套 SenseNova 图像编辑链，只替换整段 Prompt：

```text
Load Image → Painter Node → Conditioning.Image-1
完整 Prompt 模板 ─────────→ Conditioning.prompt

Conditioning 三路条件 → SenseNova Dual Guider → SamplerCustomAdvanced
SenseNova Loader.VAE ─────────────────────────→ VAE Decode → Save Image
```

Painter 输出的是已经把框线、文字和涂画栅格化进去的完整图片。SenseNova 看到的是一张带视觉标记的 `Image-1`，没有额外 bbox、mask 或第二个图像参数。

## 绘图节点

工作流使用成熟的 [AlekPet PainterNode](https://github.com/AlekPet/ComfyUI_Custom_Nodes_AlekPet)，当前工作流按节点包 `1.1.9` 的接口配置。该项目约有 1.5k GitHub stars、400 多次提交，Painter Node 支持上游图片 piping，并提供：

- 矩形、圆形、三角形和直线
- 自由画笔、MyPaint 画笔和橡皮擦
- 文字标注
- 颜色、透明度和线宽调整
- 对已画对象进行移动、缩放和旋转

安装方法任选一种：

1. 在 ComfyUI Manager 搜索 `ComfyUI_Custom_Nodes_AlekPet` 并安装。
2. 在 `ComfyUI/custom_nodes` 下执行：

   ```bash
   git clone https://github.com/AlekPet/ComfyUI_Custom_Nodes_AlekPet.git
   ```

安装后重启 ComfyUI。

## 怎么在节点内画框和标注

1. 在 `Load Image` 上传图片。
2. 第一次运行工作流。Painter Node 会把上游图片设为画布背景，并自动采用图片尺寸；第一次生成结果可以忽略。
3. 直接在 Painter Node 内使用 `☐` 画框、`◯` 画圆、`|` 画线、`T` 添加文字，或用画笔自由标注。
4. 编辑下方已经连接的完整 Prompt，把所有 `【填写……】` 占位内容替换掉。
5. 再次运行，Painter Node 输出的标注图会直接进入 `Conditioning.Image-1`。

Painter Node 也支持把本地图片直接拖到画布中。如果采用拖入方式，可以先完成框选和标注再运行。

建议让标记醒目但尽量少遮挡原图：框线使用高对比颜色，线宽足够清楚；文字说明放在对象旁边，用直线或箭头指向目标。Painter Node 没有独立箭头按钮时，可以用直线加小三角形，或直接用自由笔画箭头。

## 三段完整提示词

工作流右侧放置了三个 `PrimitiveStringMultiline` 节点，每个节点都显示一整段完整提示词，不再拆成多个字段：

1. `提示词模板 1｜框选文字风格重塑（已连接）`
2. `提示词模板 2｜局部文字替换（备用）`
3. `提示词模板 3｜标记引导高端复古改造（备用）`

第一段默认连接到 `SenseNova Conditioning.prompt`。使用其他类型时，断开第一段的连线，把第二段或第三段节点的 `STRING` 输出接到 `Conditioning.prompt`。

每段 Prompt 都已经包含完整约束：定位方式、需要填写的内容、保持范围、排版或场景一致性，以及最终删除框线、箭头、涂画和说明文字。用户只需要替换 `【填写……】` 中的内容，其余句子可以直接保留。

### 模板 1：框选文字风格重塑

需要填写：框线颜色、目标文字区域、必须保持的完整文字、目标文字风格、不得变化的其他元素。必须按原版换行填写文字，这会帮助模型保持行数和版式。

### 模板 2：局部文字替换

需要填写：目标区域描述、完整原文、完整新文、不得变化的其他元素。原文和新文都要按照希望得到的行结构换行。官方案例本身没有框线，只通过“左下角深蓝色矩形信息栏”定位；如果区域容易描述，可以不画框。

### 模板 3：标记引导高端复古改造

需要填写：每一处标记对应的修改要求、整体风格目标、不得变化的场景和对象。多处修改建议按“标记颜色／位置：原对象改成什么”逐行填写，以便模型逐项对应。

## 采样设置

工作流保留官方图像编辑默认值：

- Euler
- 50 steps
- timestep shift 3
- text CFG 4
- image CFG 1
- cfg norm `none`

为优先保证精确文字和局部保持，没有连接 8-step LoRA。

默认 latent 为适合竖版文字案例的 `1376 × 2048`。切换到横版场景改造时，可以改为 `2048 × 1152`；其他图片应尽量保持输入宽高比，并让宽高为 32 的倍数。

## 常见问题

- Painter 没显示上传图：先确认 `Load Image` 已连接到 Painter 的 `images`，然后运行一次完成 piping。
- 每次运行背景被刷新：这是 Painter 的上游图片更新机制；已画对象会保留在背景上方。确定不再更新原图时，也可以断开 `Load Image → Painter.images`。
- 标记残留：在完整 Prompt 中把具体颜色和位置写清楚，并再次强调最终图不得保留这些标记。
- 未标记区域变化过大：在 Prompt 最后一处占位中明确列出必须保持不变的对象、构图、背景、光照和其他文字。
