# SenseNova Reference Images Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Add a chainable ComfyUI node that collects independently sized reference images and feeds them to SenseNova Conditioning without forcing them into one uniformly sized `IMAGE` batch.

**Architecture:** Store converted PIL images in an immutable `SenseNovaReferenceImages` value object exposed through a custom `SENSENOVA_REFERENCE_IMAGES` socket. Each collector node appends every frame from its required `IMAGE` input to an optional prior collection. Conditioning keeps its existing `IMAGE` input for backward compatibility, accepts the new collection as an alternative, and rejects connecting both inputs at once.

**Tech Stack:** Python 3.10+, ComfyUI custom-node APIs, Pillow images produced by the existing `comfy_to_pil_batch`, `unittest`.

---

### Task 1: Reference-image collection value object

**Files:**
- Create: `src/comfy_easy_sensenova_u1/reference_images.py`
- Create: `tests/test_reference_images.py`

**Step 1: Write the failing tests**

Add tests that specify these behaviors:

```python
def test_append_preserves_node_and_batch_order():
    first = extend_reference_images(None, ["image-1", "image-2"])
    second = extend_reference_images(first, ["image-3"])
    self.assertEqual(second.images, ("image-1", "image-2", "image-3"))

def test_append_does_not_mutate_previous_collection():
    first = extend_reference_images(None, ["image-1"])
    extend_reference_images(first, ["image-2"])
    self.assertEqual(first.images, ("image-1",))

def test_resolve_rejects_legacy_batch_and_collection_together():
    references = extend_reference_images(None, ["reference"])
    with self.assertRaisesRegex(ValueError, "不能同时"):
        resolve_reference_images(["legacy"], references)
```

Also cover empty additions, invalid prior values, legacy-only resolution, and collection-only resolution.

**Step 2: Run the tests to verify RED**

Run: `python -m unittest tests.test_reference_images -v`

Expected: import failure because `comfy_easy_sensenova_u1.reference_images` does not exist.

**Step 3: Implement the minimal value object and helpers**

Create an immutable dataclass and two helpers:

```python
@dataclass(frozen=True)
class SenseNovaReferenceImages:
    images: tuple[Any, ...]


def extend_reference_images(
    references: SenseNovaReferenceImages | None,
    images: Iterable[Any],
) -> SenseNovaReferenceImages:
    ...


def resolve_reference_images(
    legacy_images: Iterable[Any] | None,
    references: SenseNovaReferenceImages | None,
) -> list[Any]:
    ...
```

The module must not import Torch, ComfyUI, or the package-level `__init__`, so its tests remain runnable in the lightweight development environment.

**Step 4: Run the tests to verify GREEN**

Run: `python -m unittest tests.test_reference_images -v`

Expected: all reference-image tests pass.

**Step 5: Commit**

```bash
git add src/comfy_easy_sensenova_u1/reference_images.py tests/test_reference_images.py
git commit -m "feat: add SenseNova reference image collection"
```

### Task 2: Chainable collector node and Conditioning integration

**Files:**
- Modify: `src/comfy_easy_sensenova_u1/nodes.py:20-50,551-577,698-730`
- Modify: `src/comfy_easy_sensenova_u1/comfy_native.py:20-30,98-122`
- Test: `tests/test_reference_images.py`

**Step 1: Add a failing source-contract test**

Parse `nodes.py` with `ast` and assert that:

- `ComfyEasySenseNovaReferenceImages` exists.
- It returns `SENSENOVA_REFERENCE_IMAGES`.
- It is present in `NODE_CLASS_MAPPINGS`.
- `ComfyEasySenseNovaConditioning.encode` accepts `reference_images`.

This test checks the import-time node contract without mocking Torch or ComfyUI.

**Step 2: Run the test to verify RED**

Run: `python -m unittest tests.test_reference_images -v`

Expected: failure because the collector class and registration do not exist.

**Step 3: Add the collector node**

Implement `ComfyEasySenseNovaReferenceImages` with:

```python
"required": {"image": ("IMAGE", ...)}
"optional": {"reference_images": ("SENSENOVA_REFERENCE_IMAGES", ...)}
RETURN_TYPES = ("SENSENOVA_REFERENCE_IMAGES",)
RETURN_NAMES = ("参考图列表",)
```

Convert every frame in the input batch through `comfy_to_pil_batch`, append it immutably with `extend_reference_images`, and register/display the node in the native category.

**Step 4: Integrate the custom collection with Conditioning**

Add optional `reference_images` to Conditioning while keeping optional `image`. Pass it into `conditioning_from_prompt`, which resolves the inputs through `resolve_reference_images`. If both inputs are connected, raise a clear `ValueError` instead of silently choosing one.

**Step 5: Run focused tests and syntax checks**

Run:

```bash
python -m unittest tests.test_reference_images -v
python -m compileall -q src tests
```

Expected: tests pass and compilation exits successfully.

**Step 6: Commit**

```bash
git add src/comfy_easy_sensenova_u1/nodes.py src/comfy_easy_sensenova_u1/comfy_native.py tests/test_reference_images.py
git commit -m "feat: add chainable reference images node"
```

### Task 3: User-facing documentation and final verification

**Files:**
- Modify: `README.md:28-65`

**Step 1: Document the connection pattern**

Add the collector to the native-node table and document this chain:

```text
Load Image 1 -> Reference Images 1 ─┐
                                   ├-> Reference Images 2 -> Conditioning.reference_images
Load Image 2 ----------------------┘
```

Explain that node order defines `Image-1`, `Image-2`, and so on; an `IMAGE` batch connected to one collector contributes all of its frames in batch order. Mention that the legacy `Conditioning.image` socket remains supported but cannot be used together with `reference_images`.

**Step 2: Run final verification**

Run:

```bash
python -m unittest tests.test_reference_images -v
python -m compileall -q src tests
git diff --check
git status --short
```

Expected: focused tests pass, compilation and diff checks exit successfully, and only intended files are changed.

Also run `python -m unittest discover -s tests -v` and report the known baseline import errors for missing `torch` and `safetensors` separately from the focused feature results.

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-09-01-reference-images.md
git commit -m "docs: explain multi-reference image workflow"
```
