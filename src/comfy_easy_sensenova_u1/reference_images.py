"""Ordered reference-image collections for native SenseNova conditioning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class SenseNovaReferenceImages:
    """Images collected across nodes without forcing a shared tensor shape."""

    images: tuple[Any, ...]


def extend_reference_images(
    references: SenseNovaReferenceImages | None,
    images: Iterable[Any],
) -> SenseNovaReferenceImages:
    """Append one node's image batch while preserving graph and batch order."""
    if references is not None and not isinstance(references, SenseNovaReferenceImages):
        raise TypeError("SenseNova 参考图列表类型无效。")
    additions = tuple(images)
    if not additions:
        raise ValueError("每个 SenseNova Reference Images 节点至少包含一张图像。")
    existing = references.images if references is not None else ()
    return SenseNovaReferenceImages(existing + additions)


def resolve_reference_images(
    legacy_images: Iterable[Any] | None,
    references: SenseNovaReferenceImages | None,
) -> list[Any]:
    """Choose the legacy IMAGE batch or the shape-preserving collection."""
    if references is not None and not isinstance(references, SenseNovaReferenceImages):
        raise TypeError("SenseNova 参考图列表类型无效。")
    if legacy_images is not None and references is not None:
        raise ValueError("不能同时连接参考图像批次和 SenseNova 参考图列表。")
    if references is not None:
        return list(references.images)
    return list(legacy_images) if legacy_images is not None else []


__all__ = [
    "SenseNovaReferenceImages",
    "extend_reference_images",
    "resolve_reference_images",
]
