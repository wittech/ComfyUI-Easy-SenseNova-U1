from __future__ import annotations

import ast
import importlib.util
import json
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1"
GUIDED_EDIT_PATH = PACKAGE_DIR / "guided_edit.py"
NODES_PATH = PACKAGE_DIR / "nodes.py"
WORKFLOW_PATH = PLUGIN_ROOT / "workflows" / "SenseNova 引导式局部编辑.json"
GUIDE_PATH = PLUGIN_ROOT / "docs" / "guided-edit-workflow_CN.md"


def load_guided_edit_module():
    if not GUIDED_EDIT_PATH.is_file():
        raise AssertionError(f"missing guided edit module: {GUIDED_EDIT_PATH}")
    spec = importlib.util.spec_from_file_location(
        "guided_edit_under_test", GUIDED_EDIT_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load guided edit module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def node_by_type(workflow, node_type):
    matches = [node for node in workflow["nodes"] if node.get("type") == node_type]
    if len(matches) != 1:
        raise AssertionError(f"expected one {node_type}, got {len(matches)}")
    return matches[0]


class GuidedEditPromptTest(unittest.TestCase):
    def test_three_modes_are_exposed_in_stable_order(self) -> None:
        module = load_guided_edit_module()

        self.assertEqual(
            module.GUIDED_EDIT_MODES,
            (
                "框选文字风格重塑",
                "局部文字替换",
                "标记引导风格改造",
            ),
        )

    def test_boxed_typography_prompt_preserves_exact_text_and_removes_guides(
        self,
    ) -> None:
        module = load_guided_edit_module()

        prompt = module.build_guided_edit_prompt(
            mode="框选文字风格重塑",
            edit_target="红色定位框内的大号白色文字",
            original_text="BLOCK\nHOUSEHOLD\nNOISE",
            replacement_text="",
            style_goal="复古海报字体，旧化印刷、磨损墨边和轻微褪色",
            preserve="保持耳机、图标、图示和周围文字不变。",
        )

        self.assertIn("仅修改红色定位框内的大号白色文字", prompt)
        self.assertIn("BLOCK\nHOUSEHOLD\nNOISE", prompt)
        self.assertIn("文字内容必须逐字保持", prompt)
        self.assertIn("保持原有行数", prompt)
        self.assertIn("复古海报字体", prompt)
        self.assertIn("删除", prompt)
        self.assertIn("定位框", prompt)
        self.assertIn("保持耳机、图标、图示和周围文字不变。", prompt)

    def test_text_replacement_prompt_contains_exact_before_and_after_text(self) -> None:
        module = load_guided_edit_module()

        prompt = module.build_guided_edit_prompt(
            mode="局部文字替换",
            edit_target="左下角深蓝色矩形信息栏",
            original_text="JUNE 15 - JULY 30, 2024",
            replacement_text="AUGUST 10 - SEPTEMBER 28, 2024",
            style_goal="",
            preserve="其他海报元素不变。",
        )

        self.assertIn("仅修改左下角深蓝色矩形信息栏", prompt)
        self.assertIn("原文：\nJUNE 15 - JULY 30, 2024", prompt)
        self.assertIn("新文：\nAUGUST 10 - SEPTEMBER 28, 2024", prompt)
        self.assertIn("字体风格、颜色、字号层级", prompt)
        self.assertIn("排版布局", prompt)
        self.assertIn("其他海报元素不变。", prompt)

    def test_marker_prompt_follows_annotations_and_erases_them(self) -> None:
        module = load_guided_edit_module()

        prompt = module.build_guided_edit_prompt(
            mode="标记引导风格改造",
            edit_target="逐项执行图上的物件替换说明",
            original_text="",
            replacement_text="",
            style_goal="more luxurious, high-end vintage aesthetic",
            preserve="保持原图构图、视角和光影关系。",
        )

        self.assertIn("严格按照输入图中的框线、箭头和手写说明", prompt)
        self.assertIn("逐项执行图上的物件替换说明", prompt)
        self.assertIn("more luxurious, high-end vintage aesthetic", prompt)
        self.assertIn("定位框、虚线框、圆圈、箭头、标记和说明文字", prompt)
        self.assertIn("完整擦除", prompt)
        self.assertIn("保持原图构图、视角和光影关系。", prompt)

    def test_mode_specific_required_fields_are_validated(self) -> None:
        module = load_guided_edit_module()

        with self.assertRaisesRegex(ValueError, "原文字"):
            module.build_guided_edit_prompt(
                "框选文字风格重塑", "红框内", "", "", "复古", ""
            )
        with self.assertRaisesRegex(ValueError, "替换后文字"):
            module.build_guided_edit_prompt(
                "局部文字替换", "信息栏", "旧文字", "", "", ""
            )
        with self.assertRaisesRegex(ValueError, "风格目标"):
            module.build_guided_edit_prompt(
                "标记引导风格改造", "所有标记", "", "", "", ""
            )
        with self.assertRaisesRegex(ValueError, "不支持的引导编辑模式"):
            module.build_guided_edit_prompt(
                "未知模式", "目标", "原文", "新文", "风格", "保留"
            )


class GuidedEditNodeContractTest(unittest.TestCase):
    def test_prompt_node_is_registered_with_one_mode_and_structured_fields(
        self,
    ) -> None:
        source = NODES_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        prompt_class = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.ClassDef)
                and node.name == "ComfyEasySenseNovaGuidedEditPrompt"
            ),
            None,
        )

        self.assertIsNotNone(prompt_class)
        self.assertIn(
            '"ComfyEasySenseNovaGuidedEditPrompt": ComfyEasySenseNovaGuidedEditPrompt',
            source,
        )
        self.assertIn(
            '"ComfyEasySenseNovaGuidedEditPrompt": "SenseNova Guided Edit Prompt"',
            source,
        )

        namespace = {
            "NATIVE_CATEGORY": "test",
            "GUIDED_EDIT_MODES": ("a", "b", "c"),
            "build_guided_edit_prompt": lambda **kwargs: "prompt",
            "ui": lambda display_name, tooltip, **kwargs: {
                "display_name": display_name,
                "tooltip": tooltip,
                **kwargs,
            },
        }
        exec(
            compile(
                ast.Module(body=[prompt_class], type_ignores=[]),
                str(NODES_PATH),
                "exec",
            ),
            namespace,
        )
        prompt_node = namespace["ComfyEasySenseNovaGuidedEditPrompt"]
        inputs = prompt_node.INPUT_TYPES()

        self.assertEqual(
            list(inputs["required"]),
            [
                "mode",
                "edit_target",
                "original_text",
                "replacement_text",
                "style_goal",
                "preserve",
            ],
        )
        self.assertEqual(prompt_node.RETURN_TYPES, ("STRING",))
        self.assertEqual(prompt_node.RETURN_NAMES, ("编辑提示词",))


class GuidedEditWorkflowTest(unittest.TestCase):
    def test_fused_workflow_connects_one_image_and_generated_prompt_to_conditioning(
        self,
    ) -> None:
        self.assertTrue(WORKFLOW_PATH.is_file(), f"missing workflow: {WORKFLOW_PATH}")
        workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
        prompt_node = node_by_type(workflow, "ComfyEasySenseNovaGuidedEditPrompt")
        load_image = node_by_type(workflow, "LoadImage")
        conditioning = node_by_type(workflow, "ComfyEasySenseNovaConditioning")

        link_by_id = {link[0]: link for link in workflow["links"]}
        conditioning_inputs = {item["name"]: item for item in conditioning["inputs"]}
        prompt_link = link_by_id[conditioning_inputs["prompt"]["link"]]
        image_link = link_by_id[conditioning_inputs["Image-1"]["link"]]

        self.assertEqual(prompt_link[1], prompt_node["id"])
        self.assertEqual(image_link[1], load_image["id"])
        self.assertNotIn("image", conditioning_inputs)
        self.assertNotIn("reference_images", conditioning_inputs)

    def test_fused_workflow_uses_official_edit_defaults_without_eight_step_lora(
        self,
    ) -> None:
        workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
        node_types = {node.get("type") for node in workflow["nodes"]}
        patch = node_by_type(workflow, "ComfyEasySenseNovaSamplingPatch")
        guider = node_by_type(workflow, "ComfyEasySenseNovaDualGuider")
        scheduler = node_by_type(workflow, "ComfyEasySenseNovaScheduler")

        self.assertNotIn("LoraLoaderModelOnly", node_types)
        self.assertEqual(patch["widgets_values"], [3.0, "none", 0.0, 1.0])
        self.assertEqual(guider["widgets_values"], [4.0, 1.0])
        self.assertEqual(scheduler["widgets_values"], [50, 3.0])
        self.assertTrue(
            {
                "ComfyEasySenseNovaLoader",
                "RandomNoise",
                "KSamplerSelect",
                "EmptyHiDreamO1LatentImage",
                "SamplerCustomAdvanced",
                "VAEDecode",
                "SaveImage",
            }.issubset(node_types)
        )

    def test_guide_documents_all_three_official_use_cases(self) -> None:
        self.assertTrue(GUIDE_PATH.is_file(), f"missing guide: {GUIDE_PATH}")
        guide = GUIDE_PATH.read_text(encoding="utf-8")

        for heading in (
            "框选引导的文字风格重塑",
            "局部文字替换",
            "标记引导的高端复古风格改造",
        ):
            self.assertIn(heading, guide)
        self.assertIn("Image-1", guide)
        self.assertIn("50", guide)
        self.assertIn("框线、箭头和手写文字是输入图像的一部分", guide)


if __name__ == "__main__":
    unittest.main()
