from __future__ import annotations

import ast
import inspect
import json
import unittest
from pathlib import Path
from types import SimpleNamespace


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
NODES_PATH = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "nodes.py"
COMFY_NATIVE_PATH = (
    PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "comfy_native.py"
)
WORKFLOWS_DIR = PLUGIN_ROOT / "workflows"


def nested_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_objects(child)


def load_conditioning_node():
    source = NODES_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    conditioning = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "ComfyEasySenseNovaConditioning"
    )

    class DummySenseNovaComfyModel:
        pass

    calls = []

    def capture_conditioning(*args, **kwargs):
        calls.append((args, kwargs))
        return ("positive", "image", "negative", "state")

    namespace = {
        "NATIVE_CATEGORY": "test",
        "SenseNovaComfyModel": DummySenseNovaComfyModel,
        "comfy_to_pil_batch": list,
        "conditioning_from_prompt": capture_conditioning,
        "ui": lambda display_name, tooltip, **kwargs: {
            "display_name": display_name,
            "tooltip": tooltip,
            **kwargs,
        },
    }
    exec(
        compile(ast.Module(body=[conditioning], type_ignores=[]), str(NODES_PATH), "exec"),
        namespace,
    )
    return (
        namespace["ComfyEasySenseNovaConditioning"],
        DummySenseNovaComfyModel,
        calls,
    )


class ConditioningReferenceImageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = NODES_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.classes = {
            node.name: node
            for node in cls.tree.body
            if isinstance(node, ast.ClassDef)
        }

    def conditioning_input_keys(self) -> tuple[list[str], list[str]]:
        conditioning = self.classes["ComfyEasySenseNovaConditioning"]
        input_types = next(
            node
            for node in conditioning.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "INPUT_TYPES"
        )
        returned = next(
            node.value for node in input_types.body if isinstance(node, ast.Return)
        )
        sections = {
            key.value: value
            for key, value in zip(returned.keys, returned.values)
            if isinstance(key, ast.Constant)
        }

        def dictionary_keys(node: ast.Dict) -> list[str]:
            return [
                key.value
                for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]

        return dictionary_keys(sections["required"]), dictionary_keys(
            sections["optional"]
        )

    def assert_handler_accepts_direct_images(self, conditioning) -> None:
        parameters = inspect.signature(conditioning.encode).parameters.values()
        self.assertTrue(
            any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters),
            "Conditioning.encode must accept Image-1 through Image-10 directly",
        )

    def test_conditioning_exposes_ten_optional_direct_image_inputs(self) -> None:
        required, optional = self.conditioning_input_keys()

        self.assertEqual(required, ["model", "prompt", "think_mode", "max_think_tokens"])
        self.assertEqual(optional, [f"Image-{index}" for index in range(1, 11)])
        self.assertNotIn("image", optional)
        self.assertNotIn("reference_images", optional)

    def test_conditioning_passes_all_ten_images_in_order(self) -> None:
        conditioning, model_type, calls = load_conditioning_node()
        self.assert_handler_accepts_direct_images(conditioning)
        inputs = {
            f"Image-{index}": [f"image-{index}"]
            for index in range(1, 11)
        }

        result = conditioning().encode(
            SimpleNamespace(model=model_type()),
            "prompt",
            True,
            1024,
            **inputs,
        )

        self.assertEqual(result, ("positive", "image", "negative", "state"))
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args[0], "prompt")
        self.assertEqual(args[1], [f"image-{index}" for index in range(1, 11)])
        self.assertEqual(args[2:], (True, 1024))
        self.assertEqual(kwargs, {})

    def test_conditioning_rejects_multiple_images_in_one_socket(self) -> None:
        conditioning, model_type, _ = load_conditioning_node()
        self.assert_handler_accepts_direct_images(conditioning)

        with self.assertRaisesRegex(ValueError, "每个.*一张"):
            conditioning().encode(
                SimpleNamespace(model=model_type()),
                "prompt",
                True,
                1024,
                **{"Image-1": ["image-1", "image-2"]},
            )

    def test_conditioning_without_images_keeps_text_to_image_mode(self) -> None:
        conditioning, model_type, calls = load_conditioning_node()
        self.assert_handler_accepts_direct_images(conditioning)

        conditioning().encode(
            SimpleNamespace(model=model_type()),
            "prompt",
            False,
            512,
        )

        args, kwargs = calls[0]
        self.assertEqual(args, ("prompt", [], False, 512))
        self.assertEqual(kwargs, {})

    def test_standalone_reference_image_collector_is_removed(self) -> None:
        self.assertNotIn("ComfyEasySenseNovaReferenceImages", self.classes)
        self.assertNotIn(
            '"ComfyEasySenseNovaReferenceImages":',
            self.source,
        )

    def test_native_conditioning_no_longer_uses_custom_reference_collection(self) -> None:
        source = COMFY_NATIVE_PATH.read_text(encoding="utf-8")

        self.assertNotIn("SenseNovaReferenceImages", source)
        self.assertNotIn("resolve_reference_images", source)

    def test_bundled_workflows_do_not_use_removed_conditioning_inputs(self) -> None:
        invalid = []
        for path in WORKFLOWS_DIR.glob("*.json"):
            workflow = json.loads(path.read_text(encoding="utf-8"))
            for node in nested_objects(workflow):
                if node.get("type") != "ComfyEasySenseNovaConditioning":
                    continue
                names = {item.get("name") for item in node.get("inputs", [])}
                removed = names.intersection({"image", "reference_images"})
                if removed:
                    invalid.append((path.name, node.get("id"), sorted(removed)))

        self.assertEqual(invalid, [])


if __name__ == "__main__":
    unittest.main()
