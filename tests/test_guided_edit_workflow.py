from __future__ import annotations

import json
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1"
GUIDED_EDIT_PATH = PACKAGE_DIR / "guided_edit.py"
NODES_PATH = PACKAGE_DIR / "nodes.py"
WORKFLOW_PATH = PLUGIN_ROOT / "workflows" / "SenseNova 引导式局部编辑.json"
GUIDE_PATH = PLUGIN_ROOT / "docs" / "guided-edit-workflow_CN.md"
README_PATH = PLUGIN_ROOT / "README.md"


def node_by_type(workflow, node_type):
    matches = [node for node in workflow["nodes"] if node.get("type") == node_type]
    if len(matches) != 1:
        raise AssertionError(f"expected one {node_type}, got {len(matches)}")
    return matches[0]


def source_node_for_input(workflow, node, input_name):
    target_input = next(item for item in node["inputs"] if item["name"] == input_name)
    link = next(item for item in workflow["links"] if item[0] == target_input["link"])
    return next(item for item in workflow["nodes"] if item["id"] == link[1])


class RemovedPromptBuilderTest(unittest.TestCase):
    def test_structured_prompt_builder_and_custom_node_are_removed(self) -> None:
        source = NODES_PATH.read_text(encoding="utf-8")

        self.assertFalse(GUIDED_EDIT_PATH.exists())
        self.assertNotIn("guided_edit", source)
        self.assertNotIn("ComfyEasySenseNovaGuidedEditPrompt", source)
        self.assertNotIn("SenseNova Guided Edit Prompt", source)


class GuidedEditWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))

    def test_painter_sits_between_load_image_and_conditioning_image_one(self) -> None:
        load_image = node_by_type(self.workflow, "LoadImage")
        painter = node_by_type(self.workflow, "PainterNode")
        conditioning = node_by_type(self.workflow, "ComfyEasySenseNovaConditioning")

        self.assertEqual(
            source_node_for_input(self.workflow, painter, "images")["id"],
            load_image["id"],
        )
        self.assertEqual(
            source_node_for_input(self.workflow, conditioning, "Image-1")["id"],
            painter["id"],
        )
        conditioning_inputs = {item["name"] for item in conditioning["inputs"]}
        self.assertNotIn("image", conditioning_inputs)
        self.assertNotIn("reference_images", conditioning_inputs)

    def test_painter_node_has_verified_schema_and_manager_metadata(self) -> None:
        painter = node_by_type(self.workflow, "PainterNode")

        self.assertEqual(
            [item["name"] for item in painter["inputs"]],
            ["image", "images", "update_node"],
        )
        self.assertEqual(
            [item["type"] for item in painter["outputs"]],
            ["IMAGE", "MASK"],
        )
        self.assertEqual(
            painter["properties"]["cnr_id"], "comfyui_custom_nodes_alekpet"
        )
        self.assertEqual(painter["properties"]["ver"], "1.1.9")
        self.assertEqual(painter["widgets_values"][0], f"Paint_{painter['id']}.png")

        settings = painter["widgets_values"][3]["settings"]
        self.assertTrue(settings["pipingSettings"]["pipingChangeSize"])
        self.assertTrue(settings["pipingSettings"]["pipingUpdateImage"])
        self.assertEqual(settings["pipingSettings"]["action"]["name"], "background")

    def test_three_complete_prompt_templates_are_visible_as_core_nodes(self) -> None:
        templates = [
            node
            for node in self.workflow["nodes"]
            if node.get("type") == "PrimitiveStringMultiline"
        ]
        by_title = {node["title"]: node for node in templates}

        self.assertEqual(
            set(by_title),
            {
                "提示词模板 1｜框选文字风格重塑（已连接）",
                "提示词模板 2｜局部文字替换（备用）",
                "提示词模板 3｜标记引导高端复古改造（备用）",
            },
        )
        for node in templates:
            prompt = node["widgets_values"][0]
            self.assertGreater(len(prompt), 250)
            self.assertGreaterEqual(prompt.count("【填写"), 3)
            self.assertIn("仅用于编辑引导", prompt)
            self.assertNotIn("BLOCK\nHOUSEHOLD\nNOISE", prompt)

        boxed = by_title["提示词模板 1｜框选文字风格重塑（已连接）"]["widgets_values"][
            0
        ]
        replacement = by_title["提示词模板 2｜局部文字替换（备用）"]["widgets_values"][
            0
        ]
        marker = by_title["提示词模板 3｜标记引导高端复古改造（备用）"][
            "widgets_values"
        ][0]

        self.assertIn("文字内容必须逐字保持为", boxed)
        self.assertIn("【填写必须保持不变的完整文字，并按原版换行】", boxed)
        self.assertIn("原文：\n【填写需要替换的完整原文", replacement)
        self.assertIn("新文：\n【填写替换后的完整新文", replacement)
        self.assertIn("严格按照输入图中的框线、圆圈、箭头和手写说明", marker)
        self.assertIn("【填写每一处标记对应的具体修改要求】", marker)

    def test_one_full_template_is_connected_directly_to_conditioning_prompt(
        self,
    ) -> None:
        conditioning = node_by_type(self.workflow, "ComfyEasySenseNovaConditioning")
        prompt_source = source_node_for_input(self.workflow, conditioning, "prompt")

        self.assertEqual(prompt_source["type"], "PrimitiveStringMultiline")
        self.assertIn("（已连接）", prompt_source["title"])
        self.assertFalse(
            any(
                node.get("type") == "ComfyEasySenseNovaGuidedEditPrompt"
                for node in self.workflow["nodes"]
            )
        )

    def test_official_edit_defaults_are_preserved_without_eight_step_lora(self) -> None:
        node_types = {node.get("type") for node in self.workflow["nodes"]}
        patch = node_by_type(self.workflow, "ComfyEasySenseNovaSamplingPatch")
        guider = node_by_type(self.workflow, "ComfyEasySenseNovaDualGuider")
        scheduler = node_by_type(self.workflow, "ComfyEasySenseNovaScheduler")

        self.assertNotIn("LoraLoaderModelOnly", node_types)
        self.assertEqual(patch["widgets_values"], [3.0, "none", 0.0, 1.0])
        self.assertEqual(guider["widgets_values"], [4.0, 1.0])
        self.assertEqual(scheduler["widgets_values"], [50, 3.0])


class GuidedEditDocumentationTest(unittest.TestCase):
    def test_guide_explains_painter_workflow_and_complete_templates(self) -> None:
        guide = GUIDE_PATH.read_text(encoding="utf-8")

        self.assertIn("AlekPet PainterNode", guide)
        self.assertIn("https://github.com/AlekPet/ComfyUI_Custom_Nodes_AlekPet", guide)
        self.assertIn("Load Image → Painter Node → Conditioning.Image-1", guide)
        self.assertIn("第一次", guide)
        self.assertIn("三段完整提示词", guide)
        self.assertNotIn("edit_target", guide)
        self.assertNotIn("SenseNova Guided Edit Prompt", guide)

    def test_readme_lists_painter_dependency_not_removed_custom_node(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("AlekPet Painter Node", readme)
        self.assertIn("PrimitiveStringMultiline", readme)
        self.assertNotIn("SenseNova Guided Edit Prompt", readme)


if __name__ == "__main__":
    unittest.main()
