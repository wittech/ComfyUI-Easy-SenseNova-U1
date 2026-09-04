from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "transformer_patch"
MODELING_UTILS_PATH = PATCH_DIR / "transformers_4571" / "modeling_utils.py"


def load_initialize_weights_function():
    source = MODELING_UTILS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    pretrained_model = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PreTrainedModel"
    )
    method = next(
        node
        for node in pretrained_model.body
        if isinstance(node, ast.FunctionDef) and node.name == "initialize_weights"
    )
    method.decorator_list = []
    method.name = "initialize_weights_under_test"
    ast.fix_missing_locations(method)
    return method


class PrivateTransformersBackendTest(unittest.TestCase):
    def test_weight_initialization_ignores_foreign_global_smart_apply(self) -> None:
        calls = []
        foreign_calls = []

        class FakeModule:
            def __init__(self, name, children=()):
                self.name = name
                self._children = list(children)

            def children(self):
                return iter(self._children)

            def smart_apply(self, fn, is_custom_code):
                foreign_calls.append((self, fn, is_custom_code))
                return self

        class FakePreTrainedModel(FakeModule):
            def _initialize_weights(self, module):
                calls.append((self.name, module.name))

        fake_torch = type(
            "FakeTorch",
            (),
            {"nn": type("FakeNN", (), {"Module": FakeModule})},
        )
        namespace = {
            "torch": fake_torch,
            "PreTrainedModel": FakePreTrainedModel,
        }
        method = load_initialize_weights_function()
        exec(
            compile(ast.Module(body=[method], type_ignores=[]), MODELING_UTILS_PATH, "exec"),
            namespace,
        )

        plain_leaf = FakeModule("plain-leaf")
        plain = FakeModule("plain", [plain_leaf])
        sub_leaf = FakeModule("sub-leaf")
        sub_model = FakePreTrainedModel("sub-model", [sub_leaf])
        root = FakePreTrainedModel("root", [plain, sub_model])

        try:
            namespace["initialize_weights_under_test"](root)
        except TypeError as exc:
            self.fail(f"private initialization reused an incompatible global callback: {exc}")

        self.assertEqual(foreign_calls, [])
        self.assertEqual(
            calls,
            [
                ("root", "plain-leaf"),
                ("root", "plain"),
                ("sub-model", "sub-leaf"),
                ("sub-model", "sub-model"),
                ("root", "root"),
            ],
        )

    def test_broken_tensorflow_install_is_ignored_without_mutating_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_site_packages = Path(directory)
            tensorflow = fake_site_packages / "tensorflow"
            tensorflow.mkdir()
            (tensorflow / "__init__.py").write_text(
                "raise RuntimeError('private Transformers imported TensorFlow')\n",
                encoding="utf-8",
            )
            dist_info = fake_site_packages / "tensorflow-2.20.0.dist-info"
            dist_info.mkdir()
            (dist_info / "METADATA").write_text(
                "Metadata-Version: 2.1\nName: tensorflow\nVersion: 2.20.0\n",
                encoding="utf-8",
            )

            script = textwrap.dedent(
                f"""
                import importlib.util
                import logging
                import os
                import sys
                import types

                sys.path.insert(0, {str(fake_site_packages)!r})
                package = types.ModuleType("transformers_4571")
                package.__path__ = [{str(PATCH_DIR / 'transformers_4571')!r}]
                utils = types.ModuleType("transformers_4571.utils")
                utils.__path__ = [{str(PATCH_DIR / 'transformers_4571' / 'utils')!r}]
                private_logging = types.ModuleType("transformers_4571.utils.logging")
                private_logging.get_logger = logging.getLogger
                sys.modules.update({{
                    "transformers_4571": package,
                    "transformers_4571.utils": utils,
                    "transformers_4571.utils.logging": private_logging,
                }})

                module_name = "transformers_4571.utils.import_utils"
                spec = importlib.util.spec_from_file_location(
                    module_name,
                    {str(PATCH_DIR / 'transformers_4571' / 'utils' / 'import_utils.py')!r},
                )
                import_utils = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = import_utils
                spec.loader.exec_module(import_utils)

                assert not import_utils.is_tf_available()
                assert "tensorflow" not in sys.modules
                assert os.environ["USE_TF"] == "1"
                assert os.environ["FORCE_TF_AVAILABLE"] == "1"
                """
            )
            env = os.environ.copy()
            env["USE_TF"] = "1"
            env["FORCE_TF_AVAILABLE"] = "1"
            result = subprocess.run(
                [sys.executable, "-c", script],
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
