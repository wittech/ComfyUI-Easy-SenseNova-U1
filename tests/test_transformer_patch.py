from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = PLUGIN_ROOT / "src" / "comfy_easy_sensenova_u1" / "transformer_patch"


class PrivateTransformersBackendTest(unittest.TestCase):
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
