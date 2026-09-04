from __future__ import annotations

import ast
import base64
import importlib.util
import io
import json
import unittest
from pathlib import Path

from PIL import Image


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1"
ANNOTATION_PATH = PACKAGE_DIR / "annotation_canvas.py"
NODES_PATH = PACKAGE_DIR / "nodes.py"
PACKAGE_INIT_PATH = PACKAGE_DIR / "__init__.py"
ROOT_INIT_PATH = PLUGIN_ROOT / "__init__.py"
FRONTEND_PATH = PLUGIN_ROOT / "web" / "annotation_canvas.js"


def load_annotation_module():
    spec = importlib.util.spec_from_file_location("annotation_canvas", ANNOTATION_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("annotation canvas module cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def png_data_url(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def payload(source: str, overlay: Image.Image) -> str:
    return json.dumps(
        {
            "version": 1,
            "source": source,
            "width": overlay.width,
            "height": overlay.height,
            "shapes": [],
            "overlay": png_data_url(overlay),
        }
    )


class AnnotationCompositeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_annotation_module()

    def test_empty_annotation_returns_rgb_copy(self) -> None:
        source = Image.new("RGBA", (3, 2), (10, 20, 30, 80))

        result = self.module.compose_annotation(source, "", "poster.png")

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.size, (3, 2))
        self.assertEqual(result.getpixel((1, 1)), (10, 20, 30))

    def test_transparent_png_overlay_is_alpha_composited(self) -> None:
        source = Image.new("RGB", (2, 2), (0, 0, 255))
        overlay = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        overlay.putpixel((1, 0), (255, 0, 0, 128))

        result = self.module.compose_annotation(
            source, payload("poster.png", overlay), "poster.png"
        )

        red, green, blue = result.getpixel((1, 0))
        self.assertGreaterEqual(red, 127)
        self.assertEqual(green, 0)
        self.assertGreaterEqual(blue, 126)

    def test_rejects_overlay_for_a_different_source_image(self) -> None:
        overlay = Image.new("RGBA", (2, 2), (0, 0, 0, 0))

        with self.assertRaisesRegex(ValueError, "另一张图片"):
            self.module.compose_annotation(
                Image.new("RGB", (2, 2)),
                payload("old.png", overlay),
                "new.png",
            )

    def test_rejects_wrong_overlay_dimensions_and_malformed_base64(self) -> None:
        source = Image.new("RGB", (2, 2))

        with self.assertRaisesRegex(ValueError, "尺寸"):
            self.module.compose_annotation(
                source,
                payload("poster.png", Image.new("RGBA", (3, 2))),
                "poster.png",
            )

        malformed = json.dumps(
            {
                "version": 1,
                "source": "poster.png",
                "width": 2,
                "height": 2,
                "shapes": [],
                "overlay": "data:image/png;base64,not-valid-@@@",
            }
        )
        with self.assertRaisesRegex(ValueError, "PNG"):
            self.module.compose_annotation(source, malformed, "poster.png")


class AnnotationNodeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.nodes_source = NODES_PATH.read_text(encoding="utf-8")
        cls.nodes_tree = ast.parse(cls.nodes_source)
        cls.classes = {
            node.name: node
            for node in cls.nodes_tree.body
            if isinstance(node, ast.ClassDef)
        }

    def test_native_annotation_node_is_registered_with_one_image_output(self) -> None:
        self.assertIn("ComfyEasySenseNovaAnnotationCanvas", self.classes)
        self.assertIn(
            '"ComfyEasySenseNovaAnnotationCanvas": ComfyEasySenseNovaAnnotationCanvas',
            self.nodes_source,
        )
        self.assertIn(
            '"ComfyEasySenseNovaAnnotationCanvas": "SenseNova Annotation Canvas"',
            self.nodes_source,
        )
        self.assertIn('RETURN_TYPES = ("IMAGE",)', self.nodes_source)
        self.assertIn('FUNCTION = "annotate"', self.nodes_source)

    def test_node_owns_image_upload_and_serialized_annotation_inputs(self) -> None:
        annotation_class = self.classes["ComfyEasySenseNovaAnnotationCanvas"]
        class_source = ast.get_source_segment(
            self.nodes_source, annotation_class
        ) or ""

        self.assertIn("image_upload=True", class_source)
        self.assertIn('"annotation_data"', class_source)
        self.assertIn('"STRING"', class_source)
        self.assertIn("get_annotated_filepath", class_source)
        self.assertIn("compose_annotation", class_source)
        self.assertIn("IS_CHANGED", class_source)
        self.assertIn("VALIDATE_INPUTS", class_source)

    def test_frontend_directory_is_exported(self) -> None:
        root_init = ROOT_INIT_PATH.read_text(encoding="utf-8")
        package_init = PACKAGE_INIT_PATH.read_text(encoding="utf-8")

        self.assertIn('WEB_DIRECTORY = "./web"', root_init)
        self.assertIn("ComfyEasySenseNovaAnnotationCanvas", self.nodes_source)
        self.assertIn("NODE_CLASS_MAPPINGS", package_init)


class AnnotationFrontendContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = FRONTEND_PATH.read_text(encoding="utf-8")

    def test_frontend_registers_a_dom_canvas_for_the_native_node(self) -> None:
        self.assertIn("app.registerExtension", self.source)
        self.assertIn("ComfyEasySenseNovaAnnotationCanvas", self.source)
        self.assertIn("addDOMWidget", self.source)
        self.assertIn("annotation_data", self.source)
        self.assertIn('querySelector("canvas")', self.source)
        self.assertIn("/view?", self.source)

    def test_tools_cover_official_box_marker_arrow_and_text_examples(self) -> None:
        for tool in ["select", "rectangle", "ellipse", "arrow", "brush", "text"]:
            self.assertIn(f'data-tool="{tool}"', self.source)

        for action in ["undo", "redo", "delete", "clear"]:
            self.assertIn(f'data-action="{action}"', self.source)

        for control in [
            'data-control="color"',
            'data-control="width"',
            'data-control="opacity"',
            'data-control="dashed"',
            'data-control="text"',
            'data-control="font-size"',
            'data-control="font-family"',
            'data-control="zoom"',
        ]:
            self.assertIn(control, self.source)

    def test_annotations_are_editable_and_persist_as_png_overlay(self) -> None:
        self.assertIn("setPointerCapture", self.source)
        self.assertIn("hitTest", self.source)
        self.assertIn("selectedId", self.source)
        self.assertIn("keydown", self.source)
        self.assertIn('toDataURL("image/png")', self.source)
        self.assertIn("JSON.stringify", self.source)
        self.assertIn("shapes", self.source)
        self.assertIn("source", self.source)


if __name__ == "__main__":
    unittest.main()
