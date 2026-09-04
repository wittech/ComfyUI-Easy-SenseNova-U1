from __future__ import annotations

import json
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PLUGIN_ROOT / "workflows" / "SenseNova 图像编辑 50步原版.json"
README_PATH = PLUGIN_ROOT / "README.md"


def node_by_type(workflow, node_type):
    matches = [node for node in workflow["nodes"] if node.get("type") == node_type]
    if len(matches) != 1:
        raise AssertionError(f"expected one {node_type}, got {len(matches)}")
    return matches[0]


def link_for_input(workflow, node, input_name):
    target = next(item for item in node["inputs"] if item["name"] == input_name)
    return next(item for item in workflow["links"] if item[0] == target["link"])


def source_node_for_input(workflow, node, input_name):
    link = link_for_input(workflow, node, input_name)
    return next(item for item in workflow["nodes"] if item["id"] == link[1])


class OriginalFiftyStepImageEditWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = (
            json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
            if WORKFLOW_PATH.exists()
            else {"nodes": [], "links": []}
        )

    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WORKFLOW_PATH.exists())

    def test_uses_native_edit_chain_without_any_lora(self) -> None:
        node_types = {node["type"] for node in self.workflow["nodes"]}
        serialized = json.dumps(self.workflow, ensure_ascii=False).lower()

        self.assertEqual(
            node_types,
            {
                "LoadImage",
                "PrimitiveStringMultiline",
                "ComfyEasySenseNovaLoader",
                "ComfyEasySenseNovaConditioning",
                "ComfyEasySenseNovaSamplingPatch",
                "RandomNoise",
                "ComfyEasySenseNovaDualGuider",
                "KSamplerSelect",
                "ComfyEasySenseNovaScheduler",
                "EmptyHiDreamO1LatentImage",
                "SamplerCustomAdvanced",
                "VAEDecode",
                "SaveImage",
            },
        )
        self.assertNotIn("lora", serialized)

    def test_uses_original_fifty_step_edit_parameters(self) -> None:
        patch = node_by_type(self.workflow, "ComfyEasySenseNovaSamplingPatch")
        guider = node_by_type(self.workflow, "ComfyEasySenseNovaDualGuider")
        sampler = node_by_type(self.workflow, "KSamplerSelect")
        scheduler = node_by_type(self.workflow, "ComfyEasySenseNovaScheduler")

        self.assertEqual(patch["widgets_values"], [3.0, "none", 0.0, 1.0])
        self.assertEqual(guider["widgets_values"], [4.0, 1.0])
        self.assertEqual(sampler["widgets_values"], ["euler"])
        self.assertEqual(scheduler["widgets_values"], [50, 3.0])

    def test_image_and_full_prompt_feed_conditioning_directly(self) -> None:
        conditioning = node_by_type(
            self.workflow, "ComfyEasySenseNovaConditioning"
        )
        image_source = source_node_for_input(
            self.workflow, conditioning, "Image-1"
        )
        prompt_source = source_node_for_input(
            self.workflow, conditioning, "prompt"
        )

        self.assertEqual(image_source["type"], "LoadImage")
        self.assertEqual(prompt_source["type"], "PrimitiveStringMultiline")
        prompt = prompt_source["widgets_values"][0]
        self.assertGreater(len(prompt), 200)
        self.assertGreaterEqual(prompt.count("【填写"), 3)
        self.assertIn("Image-1", prompt)
        self.assertIn("保持不变", prompt)

    def test_native_edit_chain_is_fully_connected(self) -> None:
        conditioning = node_by_type(
            self.workflow, "ComfyEasySenseNovaConditioning"
        )
        loader = node_by_type(self.workflow, "ComfyEasySenseNovaLoader")
        patch = node_by_type(self.workflow, "ComfyEasySenseNovaSamplingPatch")
        guider = node_by_type(self.workflow, "ComfyEasySenseNovaDualGuider")
        noise = node_by_type(self.workflow, "RandomNoise")
        sampler_select = node_by_type(self.workflow, "KSamplerSelect")
        scheduler = node_by_type(self.workflow, "ComfyEasySenseNovaScheduler")
        latent = node_by_type(self.workflow, "EmptyHiDreamO1LatentImage")
        sampler = node_by_type(self.workflow, "SamplerCustomAdvanced")
        decode = node_by_type(self.workflow, "VAEDecode")
        save = node_by_type(self.workflow, "SaveImage")

        expected_sources = [
            (conditioning, "model", loader),
            (patch, "model", loader),
            (guider, "model", patch),
            (guider, "positive", conditioning),
            (guider, "image_condition", conditioning),
            (guider, "negative", conditioning),
            (guider, "thinking_noise", noise),
            (sampler, "noise", noise),
            (sampler, "guider", guider),
            (sampler, "sampler", sampler_select),
            (sampler, "sigmas", scheduler),
            (sampler, "latent_image", latent),
            (decode, "samples", sampler),
            (decode, "vae", loader),
            (save, "images", decode),
        ]
        for target, input_name, source in expected_sources:
            with self.subTest(target=target["type"], input=input_name):
                self.assertEqual(
                    source_node_for_input(self.workflow, target, input_name)["id"],
                    source["id"],
                )

    def test_readme_lists_new_original_workflow(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("SenseNova 图像编辑 50步原版.json", readme)
        self.assertIn("Euler / 50 steps", readme)
        self.assertIn("不连接 LoRA", readme)


if __name__ == "__main__":
    unittest.main()
