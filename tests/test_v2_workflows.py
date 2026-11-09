import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def validate_graph(data):
    nodes = {n["id"]: n for n in data["nodes"]}
    assert len(nodes) == len(data["nodes"])
    seen = set()
    for link, origin, out_slot, target, in_slot, kind in data["links"]:
        assert link not in seen
        seen.add(link)
        assert nodes[origin]["outputs"][out_slot]["type"] == kind
        assert nodes[target]["inputs"][in_slot]["type"] in (kind, "*")
        assert link in nodes[origin]["outputs"][out_slot]["links"]
        assert nodes[target]["inputs"][in_slot]["link"] == link
    for n in nodes.values():
        for slot, port in enumerate(n.get("inputs", [])):
            if port.get("link") is not None:
                assert any(e[0] == port["link"] and e[3:5] == [n["id"], slot] for e in data["links"])
        for slot, port in enumerate(n.get("outputs", [])):
            for link in port.get("links") or []:
                assert any(e[0] == link and e[1:3] == [n["id"], slot] for e in data["links"])
    # Detect cycles and disconnected required sampling inputs.
    pending = set(nodes)
    done = set()
    while pending:
        ready = {n for n in pending if all(e[1] in done for e in data["links"] if e[3] == n)}
        assert ready, "cycle"
        done |= ready
        pending -= ready
    sampler = next(n for n in nodes.values() if n["type"] == "SamplerCustomAdvanced")
    assert all(p.get("link") is not None for p in sampler["inputs"])


class V2WorkflowTest(unittest.TestCase):
    def test_examples_have_valid_graphs_and_official_v2_parameters(self):
        paths = list((ROOT / "workflows").glob("SenseNova V2*.json"))
        self.assertEqual(len(paths), 3)
        for path in paths:
            with self.subTest(path=path.name):
                data = json.loads(path.read_text())
                validate_graph(data)
                kinds = {n["type"]: n for n in data["nodes"]}
                self.assertEqual(kinds["ComfyEasySenseNovaScheduler"]["widgets_values"], [8, 3])
                self.assertEqual(kinds["ComfyEasySenseNovaDualGuider"]["widgets_values"], [1, 1])
                self.assertEqual(kinds["ComfyEasySenseNovaSamplingPatch"]["widgets_values"], [3, "none", 0, 1])
                self.assertEqual(kinds["KSamplerSelect"]["widgets_values"], ["euler"])
                self.assertFalse(kinds["ComfyEasySenseNovaConditioning"]["widgets_values"][1])
                self.assertEqual(kinds["ComfyEasySenseNovaLoraLoader"]["widgets_values"], ["SenseNova-U1.5-8B-MoT-LoRA-8step-V2.safetensors", 1])
                self.assertEqual(kinds["ComfyEasySenseNovaLoader"]["widgets_values"][2:], ["full", False])


if __name__ == "__main__":
    unittest.main()
