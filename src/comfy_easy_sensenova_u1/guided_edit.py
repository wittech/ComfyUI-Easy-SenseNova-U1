from __future__ import annotations


GUIDED_EDIT_MODES = (
    "框选文字风格重塑",
    "局部文字替换",
    "标记引导风格改造",
)


def _required(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label}不能为空。")
    return normalized


def _preservation_clause(preserve: str) -> str:
    normalized = preserve.strip()
    if normalized:
        return normalized
    return "除明确指定的编辑区域外，保持原图的主体、构图、背景、光照、材质、图标和其他文字不变。"


def build_guided_edit_prompt(
    mode: str,
    edit_target: str,
    original_text: str,
    replacement_text: str,
    style_goal: str,
    preserve: str,
) -> str:
    """Build a strict SenseNova instruction for one of the guided edit modes."""

    if mode not in GUIDED_EDIT_MODES:
        raise ValueError(f"不支持的引导编辑模式：{mode}")

    target = _required(edit_target, "编辑目标")
    preserved = _preservation_clause(preserve)

    if mode == "框选文字风格重塑":
        source = _required(original_text, "原文字")
        style = _required(style_goal, "风格目标")
        return (
            f"仅修改{target}。\n"
            "文字内容必须逐字保持为：\n"
            f"{source}\n"
            "不得增删、翻译或改写文字；保持原有行数、排版层级、近似位置和占用范围。\n"
            f"将目标文字重塑为：{style}。\n"
            "删除输入图中用于定位的框线、箭头、标记和说明文字；它们仅用于引导编辑，不得出现在输出中。\n"
            f"{preserved}"
        )

    if mode == "局部文字替换":
        source = _required(original_text, "原文字")
        replacement = _required(replacement_text, "替换后文字")
        return (
            f"仅修改{target}内的文字。\n"
            "请将以下原文逐字替换为新文，不要遗漏、增补或改写：\n"
            "原文：\n"
            f"{source}\n"
            "新文：\n"
            f"{replacement}\n"
            "保持目标区域原有的字体风格、颜色、字号层级、行数、对齐、字距、行距和排版布局不变。\n"
            "如果输入中含有仅用于定位的框线、箭头、标记或说明文字，请将其删除并自然修复遮挡区域。\n"
            f"{preserved}"
        )

    style = _required(style_goal, "风格目标")
    return (
        "严格按照输入图中的框线、箭头和手写说明，逐项修改对应对象。\n"
        f"任务范围：{target}。\n"
        f"整体风格统一调整为：{style}。\n"
        "输入图中的定位框、虚线框、圆圈、箭头、标记和说明文字仅用于编辑引导；"
        "输出中必须完整擦除，并自然修复被它们遮挡的区域。\n"
        f"{preserved}"
    )
