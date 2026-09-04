from __future__ import annotations

import ast
import math
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "runtime.py"


def load_target_size_function():
    tree = ast.parse(RUNTIME_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "target_size_from_dimensions"
    )
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"math": math, "GRID_SIZE": 32}
    exec(compile(module, RUNTIME_PATH, "exec"), namespace)
    return namespace["target_size_from_dimensions"]


class EditResolutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.target_size_from_dimensions = staticmethod(load_target_size_function())

    def test_normalizes_landscape_like_official_smart_resize(self) -> None:
        self.assertEqual(
            self.target_size_from_dimensions(1920, 1080, 4.194304),
            (2752, 1536),
        )

    def test_normalizes_portrait_like_official_smart_resize(self) -> None:
        self.assertEqual(
            self.target_size_from_dimensions(1080, 1920, 4.194304),
            (1536, 2752),
        )

    def test_square_remains_2048_square(self) -> None:
        self.assertEqual(
            self.target_size_from_dimensions(1024, 1024, 4.194304),
            (2048, 2048),
        )

    def test_rejects_invalid_source_dimensions(self) -> None:
        with self.assertRaisesRegex(ValueError, "输入图像尺寸"):
            self.target_size_from_dimensions(0, 1080, 4.194304)

    def test_rejects_extreme_aspect_ratios_like_official_smart_resize(self) -> None:
        with self.assertRaisesRegex(ValueError, "宽高比"):
            self.target_size_from_dimensions(10000, 40, 4.194304)


if __name__ == "__main__":
    unittest.main()
