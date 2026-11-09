"""Exercise the real guider method with scalar predictions, without a GPU."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


class Sigma:
    def __init__(self, value):
        self.value = value

    def flatten(self):
        return [self.value]


class DualGuiderBranchesTest(unittest.TestCase):
    def run_guider(self, text, image, options=None):
        calls = []

        def calc(inner, branches, x, timestep, model_options):
            calls.append(branches)
            return [{"positive": 11.0, "middle": 5.0, "negative": 2.0}[b] if b else None for b in branches]

        path = Path(__file__).resolve().parents[1] / "src/comfy_easy_sensenova_u1/comfy_native.py"
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SenseNovaDualGuider")
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "predict_noise")
        module = ast.Module(body=[method], type_ignores=[])
        namespace = {"comfy": SimpleNamespace(samplers=SimpleNamespace(calc_cond_batch=calc))}
        exec(compile(module, str(path), "exec"), namespace)
        self_obj = SimpleNamespace(inner_model=None, text_cfg=text, image_cfg=image,
                                   conds={k: k for k in ("positive", "middle", "negative")})
        return namespace["predict_noise"](self_obj, 0.0, Sigma(0.5), options or {}), calls[0]

    def test_distilled_cfg_one_only_evaluates_positive(self):
        value, calls = self.run_guider(1.0, 1.0)
        self.assertEqual(value, 11.0)
        self.assertEqual([c for c in calls if c], ["positive"])

    def test_base_edit_only_evaluates_image_and_positive(self):
        value, calls = self.run_guider(4.0, 1.0)
        self.assertEqual(value, 5 + 4 * (11 - 5))
        self.assertEqual([c for c in calls if c], ["middle", "positive"])

    def test_equal_cfg_only_evaluates_negative_and_positive(self):
        value, calls = self.run_guider(3.0, 3.0)
        self.assertEqual(value, 2 + 3 * (11 - 2))
        self.assertEqual([c for c in calls if c], ["negative", "positive"])

    def test_general_cfg_preserves_upstream_three_branch_formula(self):
        value, calls = self.run_guider(4.0, 2.0)
        self.assertEqual(value, 2 + 4 * (11 - 5) + 2 * (5 - 2))
        self.assertEqual(len([c for c in calls if c]), 3)

    def test_outside_cfg_interval_only_evaluates_positive(self):
        value, calls = self.run_guider(4.0, 2.0, {"sensenova_guidance": {"interval_start": 0.8, "interval_end": 1.0}})
        self.assertEqual(value, 11.0)
        self.assertEqual([c for c in calls if c], ["positive"])


if __name__ == "__main__":
    unittest.main()
