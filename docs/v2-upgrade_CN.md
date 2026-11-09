# SenseNova-U1.5 8step V2 适配

核查日期：2026-11-09。官方源码核查版本：
`45fbbc56b0ccfa4685099339f33b46f9b0a0bbbc`（2026-11-07）。
插件修改前版本：`05aa3ec59a7422c2a6aa19dcdf10f53f64455c35`。

## 结论与原因

旧的 8 步工作流中，Euler、8 步、shift 3、CFG norm none、文本/图像
CFG 1 已经符合 V2 的官方参数，不应靠盲目增加步数或 CFG 修复。
工作流引用的是旧 `8step_comfy.safetensors`，必须实际选择 V2 权重。

官方 V2 改善色彩平衡、自然对比度并减少过度锐化，不是专门的去模糊模型。
它要求正式版 `sensenova/SenseNova-U1.5-8B-MoT`，不兼容 Preview。
与旧 LoRA 进行对照时，必须固定输入、提示词、输出尺寸、种子和 Think Mode。

核实官方 V2 safetensors 文件头：882 个 BF16 张量，294 组
down/up/alpha，目标位于 42 层中的生成分支。原文件键名以
`language_model.` 开头，而 ComfyUI 通用映射需要 `diffusion_model.` 前缀。
旧插件的转换脚本能够补前缀；通用加载节点直接选择官方原文件存在零匹配风险。
新节点自动补前缀并检查完整匹配，原有通用节点仍可继续使用转换后的文件。

逐函数比较官方最新版本与插件内置后端：`_t2i_predict_v`、`extract_feature`、
`patchify`、`unpatchify`、`_build_it2i_inputs`、`_t2i_prefix_forward`、
`_it2i_prefix_forward`、`_build_t2i_image_indexes` 的 AST 完全相同。
V2 不要求改写这些核心数值函数。上游近期的 CFG 批处理、显存管理和
Transformers 5 支持涉及多文件依赖，因此本次保留插件私有 Transformers 4.57.1，
对加载和工作流做针对性适配。原版 50 步后端与既有节点接口继续保留。

## 两份实际 PPT 工作流

| 工作流 | 原来实际生效的设置 | 本次处理 |
| --- | --- | --- |
| `PPT重绘/参考工作流/Sensenova+U1.5+图像编辑.json` | 旧 LoRA，1920×1088，Think 开启；提示词却要求 4K | 新增 V2 4MP / 4K 副本；关闭 Think 做对照；保留完整提示词与 OCR 文本 |
| `PPT美化/Sensenova图像美化测试 .json` | 外层覆盖为 4096×2304，Think 关闭；输入先缩到 2MP 再送 SenseNova 和文本模型 | SenseNova 直接接原图，文本模型保留原缩图链；新增 V2 4MP / 4K 副本并保留提示词自动生成链 |

不能只看子图节点中的 1920×1088 默认值：PPT 美化流程的外层 widget
实际覆盖了这个值。新流程展开 SenseNova 采样链，去掉失效或被覆盖的宽高控件，
以 Edit Resolution 的连线为准，避免参数来源不明确。

SenseNova 自身仍会把参考图限制在每张最多约 2048² 像素（还受多图预算影响）。
本次去掉的是外部额外的 2MP 上限，没有把模型改成无限分辨率输入。
低清原图经放大不能恢复不存在的信息；密集小字需要原始清晰素材、准确全文或分区处理。

每份旧 PPT 流程分别新增三个文件，旧文件不覆盖：

- `_V2_8步_4MP.json`：先用此版本确认加载和效果，16:9 输入约 2752×1536。
- `_V2_8步_4K.json`：16:9 输入为 4096×2304，需更多显存。
- `_原版50步_4MP对照.json`：不加载 LoRA，Euler / 50 步 / text CFG 4 / image CFG 1。

这些副本保留原图上传、提示词、文本模型、预览及保存链。新样例默认固定相同种子，
避免每次随机种子掩盖参数影响。原版 50 步是质量对照，不能保证所有图片都优于 V2。

## 使用

1. 更新本插件并重启 ComfyUI。
2. 确认 Loader 选的是正式版 U1.5 checkpoint，使用 `full`。当前插件的
   `balanced/low` 层卸载路径不支持 LoRA 补丁；新节点会提前报出这一限制。
3. 下载官方权重到运行 ComfyUI 的机器，例如在 ComfyUI 根目录执行：

   ```bash
   hf download sensenova/SenseNova-U1.5-8B-MoT-LoRAs \
     SenseNova-U1.5-8B-MoT-LoRA-8step-V2.safetensors \
     --local-dir models/loras
   ```

4. 导入新工作流，在新 **SenseNova LoRA Loader** 下拉框选择 V2 文件。
   放在子目录时需选择实际相对路径。原来的旧版文件不会自动变成 V2。
5. 先跑 4MP 版。日志应显示 `matched_layers: 294`、`tensor_count: 882`、
   `strength: 1.0`。否则先排查文件或底模，不通过 CFG 调参掩盖加载问题。
6. 固定同一张原图和完整提示词，对比 V2 与 50 步基线；再按显存情况跑 4K。
   PPT 美化链的外部文本模型也可能有随机性，比较时请把它生成的提示词固定下来。

V2 继续使用 8 步，不将 V2 LoRA 和原版 CFG 4 / 50 步混用。
未启用 LoRA 时则应使用原版 50 步配置。

## 验证范围

本次覆盖键名归一化、重复/缺失/形状错误拒绝、编辑 CFG 分支选择、工作流
双向连线与无环检查、原有分辨率和工作流回归。CFG=1 时只请求正向去噪分支，
原先每步无条件计算三路；条件预处理缓存仍沿用原插件实现。

当前机器没有可用的 ComfyUI 推理环境及模型权重，未完成真实出图或 GPU 显存验证。
结构检查通过不等于已证实“模糊完全消除”。仍需在实际推理机器用相同输入对照。

## 官方依据

- [V2 官方模型说明与参数](https://huggingface.co/sensenova/SenseNova-U1.5-8B-MoT-LoRAs)
- [SenseNova-U1 官方仓库](https://github.com/OpenSenseNova/SenseNova-U1)
- [本次核查版本的编辑示例](https://github.com/OpenSenseNova/SenseNova-U1/blob/45fbbc56b0ccfa4685099339f33b46f9b0a0bbbc/examples/editing/inference.py)
- [ComfyUI 通用 LoRA 键名映射](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/lora.py)
