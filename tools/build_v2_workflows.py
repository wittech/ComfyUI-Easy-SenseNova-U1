"""Build V2 examples; optionally migrate the two existing PPT workflows.

Run from any directory. Originals are read only; output files get new names.
"""
from __future__ import annotations

import argparse
import copy
import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LORA = "SenseNova-U1.5-8B-MoT-LoRA-8step-V2.safetensors"


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def by_type(data, kind):
    return next(n for n in data["nodes"] if n["type"] == kind)


def rebuild(data, edges):
    nodes = {n["id"]: n for n in data["nodes"]}
    for node in nodes.values():
        for port in node.get("inputs", []):
            port["link"] = None
        for port in node.get("outputs", []):
            port["links"] = []
    data["links"] = []
    for number, (_, origin, out_slot, target, in_slot, kind) in enumerate(edges, 1):
        nodes[origin]["outputs"][out_slot]["links"].append(number)
        port = nodes[target]["inputs"][in_slot]
        if port["link"] is not None:
            raise ValueError(f"Duplicate input link: {target}/{in_slot}")
        port["link"] = number
        data["links"].append([number, origin, out_slot, target, in_slot, kind])
    data["last_link_id"] = len(edges)
    data["last_node_id"] = max(nodes)


def edit_example(megapixels):
    data = json.loads((ROOT / "workflows/SenseNova 图像编辑 50步原版.json").read_text())
    data["id"] = str(uuid.uuid4())
    loader = by_type(data, "ComfyEasySenseNovaLoader")
    loader["widgets_values"][3] = False
    lora = {"id": 15, "type": "ComfyEasySenseNovaLoraLoader", "pos": [1640, 1050],
            "size": [420, 140], "flags": {}, "order": 3, "mode": 0,
            "inputs": [{"name": "model", "type": "MODEL", "link": None}],
            "outputs": [{"name": "MODEL", "type": "MODEL", "links": []},
                        {"name": "LoRA 加载信息", "type": "STRING", "links": []}],
            "properties": {"Node name for S&R": "ComfyEasySenseNovaLoraLoader"},
            "widgets_values": [LORA, 1.0]}
    data["nodes"].append(lora)
    patch = by_type(data, "ComfyEasySenseNovaSamplingPatch")
    edges = copy.deepcopy(data["links"])
    for edge in edges:
        if edge[3] == patch["id"] and edge[4] == 0:
            edge[1:3] = [15, 0]
    edges.append([0, loader["id"], 0, 15, 0, "MODEL"])
    by_type(data, "ComfyEasySenseNovaScheduler")["widgets_values"] = [8, 3.0]
    by_type(data, "ComfyEasySenseNovaDualGuider")["widgets_values"] = [1.0, 1.0]
    by_type(data, "ComfyEasySenseNovaEditResolution")["widgets_values"] = [megapixels]
    by_type(data, "RandomNoise")["widgets_values"] = [744571600207914, "fixed"]
    by_type(data, "SaveImage")["widgets_values"] = ["SenseNova/V2_8step"]
    data["groups"][1]["title"] = "2. U1.5 正式版 + V2 LoRA / 8步 / CFG 1 / full"
    data["extra"]["sensenova_v2"] = {"base": "sensenova/SenseNova-U1.5-8B-MoT",
        "lora": LORA, "megapixels": megapixels, "think_mode": False}
    rebuild(data, edges)
    return data


def migrate(source, output, megapixels, base_only=False):
    """Replace the old SenseNova subgraph with an explicit native chain.

    Preserve surrounding OCR/LLM/prompt nodes and their links, including the
    existing thinking-text output. Use the original image for model conditioning;
    the image sent to the external LLM keeps its existing resize settings.
    """
    data = json.loads(source.read_text())
    sub_ids = {s["id"] for s in data.get("definitions", {}).get("subgraphs", [])}
    outer = next(n for n in data["nodes"] if n["type"] in sub_ids)
    controls = outer["widgets_values"]
    template = edit_example(megapixels)
    if base_only:
        template = json.loads((ROOT / "workflows/SenseNova 图像编辑 50步原版.json").read_text())
        by_type(template, "ComfyEasySenseNovaEditResolution")["widgets_values"] = [megapixels]
        by_type(template, "RandomNoise")["widgets_values"] = [744571600207914, "fixed"]
    by_type(template, "ComfyEasySenseNovaLoader")["widgets_values"] = [controls[0], controls[1], "full", False]
    by_type(template, "PrimitiveStringMultiline")["widgets_values"] = [controls[3]]
    by_type(template, "SaveImage")["widgets_values"] = ["SenseNova/V2_compare" if not base_only else "SenseNova/base50_compare"]

    outer_links = {port["name"]: next((e for e in data["links"] if e[0] == port.get("link")), None)
                   for port in outer["inputs"]}
    main_image = outer_links.get("Image-1") or outer_links.get("image")
    if main_image is None:
        raise ValueError("The source workflow has no connected main image")
    # A resize shared with a prompt LLM must not cap the image the generator sees.
    source_node = next(n for n in data["nodes"] if n["id"] == main_image[1])
    image_origin = main_image[1:3]
    if source_node["type"] == "ImageScaleToTotalPixels":
        original = next(e for e in data["links"] if e[3] == source_node["id"] and e[4] == 0)
        image_origin = original[1:3]

    offset = max(n["id"] for n in data["nodes"]) + 1
    mapping = {n["id"]: n["id"] + offset for n in template["nodes"]}
    cond = by_type(template, "ComfyEasySenseNovaConditioning")
    resolution = by_type(template, "ComfyEasySenseNovaEditResolution")
    decode = by_type(template, "VAEDecode")
    save = by_type(template, "SaveImage")
    prompt = by_type(template, "PrimitiveStringMultiline")
    image = by_type(template, "LoadImage")
    removed = {image["id"], save["id"]}
    if outer_links.get("prompt"):
        removed.add(prompt["id"])
    edges = [[0, mapping[e[1]], e[2], mapping[e[3]], e[4], e[5]]
             for e in template["links"] if e[1] not in removed and e[3] not in removed]
    edges += [[0, *image_origin, mapping[cond["id"]], 1, "IMAGE"],
              [0, *image_origin, mapping[resolution["id"]], 0, "IMAGE"]]
    if outer_links.get("prompt"):
        edges.append([0, *outer_links["prompt"][1:3], mapping[cond["id"]], 2, "STRING"])
    if outer_links.get("Image-2"):
        cond["inputs"].append({"name": "Image-2", "type": "IMAGE", "link": None})
        edges.append([0, *outer_links["Image-2"][1:3], mapping[cond["id"]], len(cond["inputs"])-1, "IMAGE"])

    think_id = offset + max(mapping) + 1
    has_think = any(e[1] == outer["id"] and e[2] == 1 for e in data["links"])
    if has_think:
        sampler = by_type(template, "SamplerCustomAdvanced")
        think = {"id": think_id, "type": "ComfyEasySenseNovaThinkText", "pos": [2650, 700],
                 "size": [280, 100], "flags": {}, "order": 20, "mode": 0,
                 "inputs": [{"name": "state", "type": "SENSENOVA_CONDITION_STATE", "link": None},
                            {"name": "samples", "type": "LATENT", "link": None}],
                 "outputs": [{"name": "STRING", "type": "STRING", "links": []},
                             {"name": "LATENT", "type": "LATENT", "links": []}],
                 "properties": {"Node name for S&R": "ComfyEasySenseNovaThinkText"}, "widgets_values": []}
        edges += [[0, mapping[cond["id"]], 3, think_id, 0, "SENSENOVA_CONDITION_STATE"],
                  [0, mapping[sampler["id"]], 0, think_id, 1, "LATENT"]]

    for edge in data["links"]:
        if edge[3] == outer["id"]:
            continue
        edge = copy.deepcopy(edge)
        if edge[1] == outer["id"]:
            edge[1:3] = [mapping[decode["id"]], 0] if edge[2] == 0 else [think_id, 0]
        edges.append(edge)
    data["nodes"] = [n for n in data["nodes"] if n["id"] != outer["id"]]
    new_nodes = []
    for node in template["nodes"]:
        if node["id"] in removed:
            continue
        node["id"] = mapping[node["id"]]
        node["pos"] = [outer["pos"][0] + node["pos"][0] - 1100,
                       outer["pos"][1] + node["pos"][1] - 600]
        new_nodes.append(node)
    data["nodes"].extend(new_nodes)
    if has_think:
        data["nodes"].append(think)
    data["definitions"]["subgraphs"] = [s for s in data["definitions"].get("subgraphs", []) if s["id"] != outer["type"]]
    data["id"] = str(uuid.uuid4())
    data["extra"]["sensenova_v2"] = {"source": source.name, "megapixels": megapixels,
        "base_only": base_only, "input_resize_bypassed_for_generator": True}
    rebuild(data, edges)
    dump(output, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    for name, pixels in [("4MP", 4.194304), ("4K", 9.437184)]:
        data = edit_example(pixels)
        dump(ROOT / "workflows" / f"SenseNova V2 8步图像编辑 {name}.json", data)
    data = edit_example(4.194304)
    # T2I uses the same positive-only guider when both CFG values are one.
    image = by_type(data, "LoadImage")["id"]
    resolution = by_type(data, "ComfyEasySenseNovaEditResolution")["id"]
    data["nodes"] = [n for n in data["nodes"] if n["id"] not in (image, resolution)]
    edges = [e for e in data["links"] if e[1] not in (image, resolution) and e[3] not in (image, resolution)]
    by_type(data, "EmptyHiDreamO1LatentImage")["widgets_values"] = [2048, 2048, 1]
    by_type(data, "PrimitiveStringMultiline")["widgets_values"] = ["日出时的高山湖泊，写实摄影，自然光照，真实材质与清晰细节。"]
    rebuild(data, edges)
    dump(ROOT / "workflows/SenseNova V2 8步图像生成.json", data)
    if args.workspace:
        sources = [args.workspace / "PPT美化/Sensenova图像美化测试 .json",
                   args.workspace / "PPT重绘/参考工作流/Sensenova+U1.5+图像编辑.json"]
        for source in sources:
            for name, pixels in [("4MP", 4.194304), ("4K", 9.437184)]:
                migrate(source, source.with_name(source.stem.strip() + f"_V2_8步_{name}.json"), pixels)
            migrate(source, source.with_name(source.stem.strip() + "_原版50步_4MP对照.json"), 4.194304, base_only=True)


if __name__ == "__main__":
    main()
