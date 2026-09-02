from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "reference_images.py"
NODES_PATH = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "nodes.py"


def load_reference_images_module():
    if not MODULE_PATH.is_file():
        raise AssertionError(f"missing reference image module: {MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("sensenova_reference_images", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReferenceImageCollectionTest(unittest.TestCase):
    def test_append_preserves_node_and_batch_order(self) -> None:
        module = load_reference_images_module()

        first = module.extend_reference_images(None, ["image-1", "image-2"])
        second = module.extend_reference_images(first, ["image-3"])

        self.assertEqual(second.images, ("image-1", "image-2", "image-3"))

    def test_append_does_not_mutate_previous_collection(self) -> None:
        module = load_reference_images_module()
        first = module.extend_reference_images(None, ["image-1"])

        module.extend_reference_images(first, ["image-2"])

        self.assertEqual(first.images, ("image-1",))

    def test_append_rejects_empty_batch(self) -> None:
        module = load_reference_images_module()

        with self.assertRaisesRegex(ValueError, "至少包含一张"):
            module.extend_reference_images(None, [])

    def test_append_rejects_invalid_previous_collection(self) -> None:
        module = load_reference_images_module()

        with self.assertRaisesRegex(TypeError, "参考图列表类型无效"):
            module.extend_reference_images(["not-a-collection"], ["image"])

    def test_resolve_rejects_legacy_batch_and_collection_together(self) -> None:
        module = load_reference_images_module()
        references = module.extend_reference_images(None, ["reference"])

        with self.assertRaisesRegex(ValueError, "不能同时"):
            module.resolve_reference_images(["legacy"], references)

    def test_resolve_accepts_legacy_batch_or_collection(self) -> None:
        module = load_reference_images_module()
        references = module.extend_reference_images(None, ["reference-1", "reference-2"])

        self.assertEqual(module.resolve_reference_images(["legacy"], None), ["legacy"])
        self.assertEqual(
            module.resolve_reference_images(None, references),
            ["reference-1", "reference-2"],
        )
        self.assertEqual(module.resolve_reference_images(None, None), [])


class ReferenceImageNodeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = NODES_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.classes = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, ast.ClassDef)
        }

    def test_collector_exposes_custom_reference_image_socket(self) -> None:
        collector = self.classes.get("ComfyEasySenseNovaReferenceImages")

        self.assertIsNotNone(collector, "missing ComfyEasySenseNovaReferenceImages node")
        assignments = {
            target.id: node.value
            for node in collector.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        return_types = ast.literal_eval(assignments["RETURN_TYPES"])
        self.assertEqual(return_types, ("SENSENOVA_REFERENCE_IMAGES",))

    def test_collector_is_registered(self) -> None:
        self.assertIn(
            '"ComfyEasySenseNovaReferenceImages": ComfyEasySenseNovaReferenceImages',
            self.source,
        )

    def test_conditioning_accepts_reference_image_collection(self) -> None:
        conditioning = self.classes["ComfyEasySenseNovaConditioning"]
        encode = next(
            node
            for node in conditioning.body
            if isinstance(node, ast.FunctionDef) and node.name == "encode"
        )
        argument_names = [argument.arg for argument in encode.args.args]

        self.assertIn("reference_images", argument_names)


if __name__ == "__main__":
    unittest.main()
