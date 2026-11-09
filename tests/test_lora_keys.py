from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lora_keys", ROOT / "src/comfy_easy_sensenova_u1/lora_keys.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tensor:
    def __init__(self, shape, value=8.0):
        self.shape = shape
        self.value = value

    def __float__(self):
        return self.value


class LoRAKeysTest(unittest.TestCase):
    def setUp(self):
        self.base = "language_model.model.layers.0.self_attn.q_proj_mot_gen"
        self.state = {self.base + ".lora_down.weight": Tensor((128, 4096)),
                      self.base + ".lora_up.weight": Tensor((4096, 128)),
                      self.base + ".alpha": Tensor(())}
        self.shapes = {"diffusion_model." + self.base + ".weight": (4096, 4096)}

    def test_official_bf16_keys_are_normalized_without_changing_tensors(self):
        state, targets = module.prepare_lora(self.state, self.shapes)
        for key, value in self.state.items():
            self.assertIs(state["diffusion_model." + key], value)
        self.assertEqual(set(targets.values()), set(self.shapes))

    def test_converted_keys_are_not_prefixed_twice(self):
        state = {"diffusion_model." + k: v for k, v in self.state.items()}
        self.assertEqual(module.prepare_lora(state, self.shapes)[0], state)

    def test_missing_alpha_uses_comfy_rank_default(self):
        del self.state[self.base + ".alpha"]
        self.assertEqual(len(module.prepare_lora(self.state, self.shapes)[1]), 1)

    def test_unmatched_model_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "未匹配"):
            module.prepare_lora(self.state, {})

    def test_partial_match_is_rejected(self):
        self.state["other.lora_down.weight"] = Tensor((2, 3))
        self.state["other.lora_up.weight"] = Tensor((3, 2))
        with self.assertRaisesRegex(ValueError, "未匹配"):
            module.prepare_lora(self.state, self.shapes)

    def test_unpaired_and_wrong_shapes_are_rejected(self):
        self.state[self.base + ".lora_up.weight"] = Tensor((4096, 64))
        with self.assertRaisesRegex(ValueError, "形状"):
            module.prepare_lora(self.state, self.shapes)
        del self.state[self.base + ".lora_up.weight"]
        with self.assertRaisesRegex(ValueError, "配对"):
            module.prepare_lora(self.state, self.shapes)

    def test_empty_duplicate_and_unknown_keys_are_rejected(self):
        for state in ({}, {"unknown": Tensor(())},
                      dict(self.state, **{"diffusion_model." + k: v for k, v in self.state.items()})):
            with self.subTest(keys=list(state)), self.assertRaises(ValueError):
                module.prepare_lora(state, self.shapes)

    def test_invalid_alpha_is_rejected(self):
        for alpha in (Tensor((2,)), Tensor((), float("nan"))):
            self.state[self.base + ".alpha"] = alpha
            with self.assertRaisesRegex(ValueError, "alpha"):
                module.prepare_lora(self.state, self.shapes)


if __name__ == "__main__":
    unittest.main()
