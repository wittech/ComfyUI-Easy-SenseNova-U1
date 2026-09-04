from __future__ import annotations

import base64
import binascii
import io
import json
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError


ANNOTATION_VERSION = 1
MAX_ANNOTATION_BYTES = 32 * 1024 * 1024
MAX_OVERLAY_BYTES = 24 * 1024 * 1024


def _read_payload(annotation_data: str) -> dict[str, Any] | None:
    if not annotation_data or not annotation_data.strip():
        return None
    if len(annotation_data.encode("utf-8")) > MAX_ANNOTATION_BYTES:
        raise ValueError("标注数据过大，请减少自由画笔笔画后重试。")
    try:
        payload = json.loads(annotation_data)
    except json.JSONDecodeError as exc:
        raise ValueError("标注数据不是有效的 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("标注数据必须是一个 JSON 对象。")
    if payload.get("version") != ANNOTATION_VERSION:
        raise ValueError("标注数据版本不受支持，请在画布中重新保存标注。")
    return payload


def _decode_overlay(payload: dict[str, Any]) -> Image.Image:
    value = payload.get("overlay")
    prefix = "data:image/png;base64,"
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError("标注覆盖层必须是透明 PNG 数据。")
    encoded = value[len(prefix) :]
    if len(encoded) > (MAX_OVERLAY_BYTES * 4 // 3) + 8:
        raise ValueError("标注 PNG 过大，请减少自由画笔笔画后重试。")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("标注 PNG 数据损坏，无法解码。") from exc
    if len(raw) > MAX_OVERLAY_BYTES:
        raise ValueError("标注 PNG 过大，请减少自由画笔笔画后重试。")
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            if opened.format != "PNG":
                raise ValueError("标注覆盖层不是 PNG 图像。")
            overlay = opened.convert("RGBA")
            overlay.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("标注 PNG 数据损坏，无法读取。") from exc
    return overlay


def compose_annotation(
    source_image: Image.Image,
    annotation_data: str,
    source_name: str,
) -> Image.Image:
    """Return an RGB copy of source_image with the saved transparent overlay."""

    base = ImageOps.exif_transpose(source_image).convert("RGBA")
    payload = _read_payload(annotation_data)
    if payload is None:
        return base.convert("RGB")

    payload_source = payload.get("source")
    if payload_source != source_name:
        raise ValueError(
            "当前标注数据属于另一张图片；请在 Annotation Canvas 中重新选择图片或清空标注。"
        )

    expected_size = (base.width, base.height)
    declared_size = (payload.get("width"), payload.get("height"))
    if declared_size != expected_size:
        raise ValueError(
            f"标注画布尺寸 {declared_size} 与输入图片尺寸 {expected_size} 不一致。"
        )

    overlay = _decode_overlay(payload)
    if overlay.size != expected_size:
        raise ValueError(
            f"标注 PNG 尺寸 {overlay.size} 与输入图片尺寸 {expected_size} 不一致。"
        )
    return Image.alpha_composite(base, overlay).convert("RGB")
