"""Validate official SenseNova and converted Comfy LoRA keys without torch."""

from __future__ import annotations

import math


PREFIX = "diffusion_model."
SUFFIXES = (".lora_down.weight", ".lora_up.weight", ".alpha")


def prepare_lora(state: dict, model_shapes: dict) -> tuple[dict, dict]:
    """Return generic Comfy keys and an exact target map; reject partial loads.

    Shapes are supplied by named_parameters(), so validation neither copies nor
    materializes the base model's weights. Tensor objects are passed unchanged.
    """
    normalized = {}
    groups = {}
    for name, tensor in state.items():
        suffix = next((s for s in SUFFIXES if name.endswith(s)), None)
        if suffix is None:
            raise ValueError(f"不支持的 SenseNova LoRA 张量: {name}")
        target = name if name.startswith(PREFIX) else PREFIX + name
        if target in normalized:
            raise ValueError(f"重复的 LoRA 键名: {target}")
        normalized[target] = tensor
        groups.setdefault(target[:-len(suffix)], {})[suffix] = tensor
    if not groups:
        raise ValueError("LoRA 中没有可加载的张量。")

    key_map = {}
    for base, tensors in groups.items():
        if ".lora_down.weight" not in tensors or ".lora_up.weight" not in tensors:
            raise ValueError(f"LoRA 缺少配对的 down/up 张量: {base}")
        target = base + ".weight"
        if target not in model_shapes:
            raise ValueError(f"LoRA 未匹配模型权重: {target}；请确认使用正式版 U1.5 底模。")
        down = tuple(tensors[".lora_down.weight"].shape)
        up = tuple(tensors[".lora_up.weight"].shape)
        shape = tuple(model_shapes[target])
        if (len(down) != 2 or len(up) != 2 or down[0] < 1
                or up[1] != down[0] or shape != (up[0], down[1])):
            raise ValueError(f"LoRA 形状不匹配: {base}: down={down}, up={up}, model={shape}")
        alpha = tensors.get(".alpha")
        if alpha is not None:
            if tuple(alpha.shape) not in ((), (1,)) or not math.isfinite(float(alpha)):
                raise ValueError(f"LoRA alpha 必须为有限标量: {base}")
        key_map[base] = target
    return normalized, key_map
