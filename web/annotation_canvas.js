const { app } = window.comfyAPI.app;

const NODE_CLASS = "ComfyEasySenseNovaAnnotationCanvas";
const TOOL_TYPES = new Set(["select", "rectangle", "ellipse", "arrow", "brush", "text"]);
const DRAW_TYPES = new Set(["rectangle", "ellipse", "arrow", "brush", "text"]);
const MAX_HISTORY = 50;

function installStyles() {
  if (document.getElementById("sensenova-annotation-canvas-styles")) return;
  const style = document.createElement("style");
  style.id = "sensenova-annotation-canvas-styles";
  style.textContent = `
    .sn-annotation-root {
      --sn-panel: var(--comfy-menu-bg, #24262b);
      --sn-border: var(--border-color, #555);
      --sn-text: var(--input-text, #e8eaed);
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      gap: 8px;
      width: 100%;
      min-width: 420px;
      color: var(--sn-text);
      font: 12px/1.35 Inter, ui-sans-serif, system-ui, sans-serif;
      user-select: none;
    }
    .sn-annotation-root *, .sn-annotation-root *::before, .sn-annotation-root *::after {
      box-sizing: border-box;
    }
    .sn-annotation-toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 5px;
      padding: 7px;
      border: 1px solid var(--sn-border);
      border-radius: 7px;
      background: var(--sn-panel);
    }
    .sn-annotation-toolbar button,
    .sn-annotation-toolbar select,
    .sn-annotation-toolbar input,
    .sn-annotation-toolbar textarea {
      min-height: 28px;
      border: 1px solid var(--sn-border);
      border-radius: 5px;
      background: var(--comfy-input-bg, #111318);
      color: var(--sn-text);
      font: inherit;
    }
    .sn-annotation-toolbar button {
      padding: 4px 8px;
      cursor: pointer;
    }
    .sn-annotation-toolbar button:hover { border-color: #8ab4f8; }
    .sn-annotation-toolbar button.active {
      border-color: #8ab4f8;
      background: color-mix(in srgb, #8ab4f8 22%, var(--comfy-input-bg, #111318));
      color: #d7e7ff;
    }
    .sn-annotation-toolbar button:disabled { opacity: .38; cursor: default; }
    .sn-annotation-divider { width: 1px; height: 22px; margin: 0 2px; background: var(--sn-border); }
    .sn-annotation-field { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
    .sn-annotation-field input[type="range"] { width: 76px; min-height: 20px; accent-color: #8ab4f8; }
    .sn-annotation-field input[type="color"] { width: 32px; padding: 2px; cursor: pointer; }
    .sn-annotation-field input[type="checkbox"] { min-height: auto; accent-color: #8ab4f8; }
    .sn-annotation-text { flex: 1 1 210px; min-width: 150px; padding: 5px 7px; resize: vertical; user-select: text; }
    .sn-annotation-swatch { width: 22px; min-width: 22px; padding: 0 !important; background: var(--swatch) !important; }
    .sn-annotation-canvas-shell {
      position: relative;
      width: 100%;
      min-height: 340px;
      max-height: 720px;
      overflow: auto;
      border: 1px solid var(--sn-border);
      border-radius: 7px;
      background-color: #15171a;
      background-image:
        linear-gradient(45deg, #202328 25%, transparent 25%),
        linear-gradient(-45deg, #202328 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #202328 75%),
        linear-gradient(-45deg, transparent 75%, #202328 75%);
      background-size: 20px 20px;
      background-position: 0 0, 0 10px, 10px -10px, -10px 0;
    }
    .sn-annotation-canvas-shell canvas {
      display: block;
      width: 100%;
      height: auto;
      touch-action: none;
      cursor: crosshair;
    }
    .sn-annotation-empty {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      padding: 24px;
      color: #aeb4bd;
      text-align: center;
      pointer-events: none;
    }
    .sn-annotation-status {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      min-height: 18px;
      color: #aeb4bd;
    }
    .sn-annotation-status [data-role="message"].error { color: #ff8a80; }
    .sn-annotation-kbd { opacity: .75; text-align: right; }
  `;
  document.head.appendChild(style);
}

function deepCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

function makeId() {
  return globalThis.crypto?.randomUUID?.()
    ?? `annotation-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function rgba(hex, opacity) {
  const value = /^#[0-9a-f]{6}$/i.test(hex) ? hex.slice(1) : "ff3b30";
  return `rgba(${parseInt(value.slice(0, 2), 16)}, ${parseInt(value.slice(2, 4), 16)}, ${parseInt(value.slice(4, 6), 16)}, ${clamp(opacity, 0.05, 1)})`;
}

function parseAnnotatedFilename(value) {
  const original = String(value ?? "").trim();
  const match = original.match(/\s+\[(input|output|temp)\]$/i);
  const type = match?.[1]?.toLowerCase() ?? "input";
  const clean = (match ? original.slice(0, match.index) : original).replaceAll("\\", "/");
  const separator = clean.lastIndexOf("/");
  return {
    original,
    type,
    filename: separator >= 0 ? clean.slice(separator + 1) : clean,
    subfolder: separator >= 0 ? clean.slice(0, separator) : "",
  };
}

function imageViewUrl(value) {
  const file = parseAnnotatedFilename(value);
  const query = new URLSearchParams({
    filename: file.filename,
    type: file.type,
    subfolder: file.subfolder,
    t: String(Date.now()),
  });
  const path = `/view?${query.toString()}`;
  return window.comfyAPI.api?.api?.apiURL?.(path) ?? path;
}

function shapeBounds(shape, context) {
  if (shape.type === "brush") {
    const points = shape.points ?? [];
    if (!points.length) return { x1: 0, y1: 0, x2: 0, y2: 0 };
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    return { x1: Math.min(...xs), y1: Math.min(...ys), x2: Math.max(...xs), y2: Math.max(...ys) };
  }
  if (shape.type === "text") {
    context.save();
    context.font = `${shape.fontSize}px ${shape.fontFamily}`;
    const lines = String(shape.text ?? "").split("\n");
    const width = Math.max(1, ...lines.map((line) => context.measureText(line || " ").width));
    const height = Math.max(1, lines.length * shape.fontSize * 1.25);
    context.restore();
    return { x1: shape.x1, y1: shape.y1, x2: shape.x1 + width, y2: shape.y1 + height };
  }
  return {
    x1: Math.min(shape.x1, shape.x2),
    y1: Math.min(shape.y1, shape.y2),
    x2: Math.max(shape.x1, shape.x2),
    y2: Math.max(shape.y1, shape.y2),
  };
}

function applyStroke(context, shape) {
  context.strokeStyle = rgba(shape.color, shape.opacity);
  context.fillStyle = rgba(shape.color, shape.opacity);
  context.lineWidth = Math.max(1, shape.width);
  context.lineCap = "round";
  context.lineJoin = "round";
  context.setLineDash(shape.dashed ? [shape.width * 3, shape.width * 2] : []);
}

function drawShape(context, shape) {
  context.save();
  applyStroke(context, shape);
  if (shape.type === "rectangle") {
    context.strokeRect(shape.x1, shape.y1, shape.x2 - shape.x1, shape.y2 - shape.y1);
  } else if (shape.type === "ellipse") {
    const centerX = (shape.x1 + shape.x2) / 2;
    const centerY = (shape.y1 + shape.y2) / 2;
    context.beginPath();
    context.ellipse(
      centerX,
      centerY,
      Math.abs(shape.x2 - shape.x1) / 2,
      Math.abs(shape.y2 - shape.y1) / 2,
      0,
      0,
      Math.PI * 2,
    );
    context.stroke();
  } else if (shape.type === "arrow") {
    const angle = Math.atan2(shape.y2 - shape.y1, shape.x2 - shape.x1);
    const head = Math.max(12, shape.width * 4);
    context.beginPath();
    context.moveTo(shape.x1, shape.y1);
    context.lineTo(shape.x2, shape.y2);
    context.stroke();
    context.setLineDash([]);
    context.beginPath();
    context.moveTo(shape.x2, shape.y2);
    context.lineTo(shape.x2 - head * Math.cos(angle - Math.PI / 6), shape.y2 - head * Math.sin(angle - Math.PI / 6));
    context.lineTo(shape.x2 - head * Math.cos(angle + Math.PI / 6), shape.y2 - head * Math.sin(angle + Math.PI / 6));
    context.closePath();
    context.fill();
  } else if (shape.type === "brush") {
    const points = shape.points ?? [];
    if (points.length) {
      context.beginPath();
      context.moveTo(points[0].x, points[0].y);
      for (const point of points.slice(1)) context.lineTo(point.x, point.y);
      if (points.length === 1) context.lineTo(points[0].x + 0.01, points[0].y + 0.01);
      context.stroke();
    }
  } else if (shape.type === "text") {
    context.setLineDash([]);
    context.font = `${shape.fontSize}px ${shape.fontFamily}`;
    context.textBaseline = "top";
    String(shape.text ?? "").split("\n").forEach((line, index) => {
      context.fillText(line, shape.x1, shape.y1 + index * shape.fontSize * 1.25);
    });
  }
  context.restore();
}

function sanitizeShapes(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 2000).flatMap((raw) => {
    if (!raw || !DRAW_TYPES.has(raw.type)) return [];
    const base = {
      id: String(raw.id || makeId()),
      type: raw.type,
      color: /^#[0-9a-f]{6}$/i.test(raw.color) ? raw.color : "#ff3b30",
      width: clamp(finiteNumber(raw.width, 8), 1, 200),
      opacity: clamp(finiteNumber(raw.opacity, 1), 0.05, 1),
      dashed: Boolean(raw.dashed),
    };
    if (raw.type === "brush") {
      const points = Array.isArray(raw.points)
        ? raw.points.slice(0, 20000).map((point) => ({ x: finiteNumber(point.x), y: finiteNumber(point.y) }))
        : [];
      return [{ ...base, points }];
    }
    if (raw.type === "text") {
      return [{
        ...base,
        x1: finiteNumber(raw.x1),
        y1: finiteNumber(raw.y1),
        text: String(raw.text ?? "").slice(0, 2000),
        fontSize: clamp(finiteNumber(raw.fontSize, 48), 8, 500),
        fontFamily: String(raw.fontFamily || "ui-sans-serif, system-ui, sans-serif").slice(0, 200),
      }];
    }
    return [{
      ...base,
      x1: finiteNumber(raw.x1),
      y1: finiteNumber(raw.y1),
      x2: finiteNumber(raw.x2),
      y2: finiteNumber(raw.y2),
    }];
  });
}

class AnnotationEditor {
  constructor(node, root, imageWidget, dataWidget) {
    this.node = node;
    this.root = root;
    this.imageWidget = imageWidget;
    this.dataWidget = dataWidget;
    this.canvas = root.querySelector("canvas");
    this.context = this.canvas.getContext("2d");
    this.shell = root.querySelector(".sn-annotation-canvas-shell");
    this.empty = root.querySelector(".sn-annotation-empty");
    this.message = root.querySelector('[data-role="message"]');
    this.count = root.querySelector('[data-role="count"]');
    this.sourceImage = new Image();
    this.sourceName = "";
    this.shapes = [];
    this.selectedId = null;
    this.tool = "rectangle";
    this.interaction = null;
    this.undoStack = [];
    this.redoStack = [];
    this.loadSequence = 0;
    this.bindControls();
    this.bindCanvas();
    this.selectTool("rectangle");
    this.updateButtons();
  }

  control(name) {
    return this.root.querySelector(`[data-control="${name}"]`);
  }

  bindControls() {
    this.root.querySelectorAll("[data-tool]").forEach((button) => {
      button.addEventListener("click", () => this.selectTool(button.dataset.tool));
    });
    this.root.querySelectorAll("[data-action]").forEach((button) => {
      button.addEventListener("click", () => this.runAction(button.dataset.action));
    });
    this.root.querySelectorAll("[data-color]").forEach((button) => {
      button.addEventListener("click", () => {
        this.control("color").value = button.dataset.color;
        this.applyControlsToSelection();
      });
    });
    ["color", "width", "opacity", "dashed", "text", "font-size", "font-family"].forEach((name) => {
      this.control(name).addEventListener("change", () => this.applyControlsToSelection());
    });
    this.control("width").addEventListener("input", () => this.updateStyleLabels());
    this.control("opacity").addEventListener("input", () => this.updateStyleLabels());
    this.control("zoom").addEventListener("input", () => this.applyZoom());
    this.updateStyleLabels();
    this.applyZoom();
  }

  bindCanvas() {
    this.canvas.addEventListener("pointerdown", (event) => this.pointerDown(event));
    this.canvas.addEventListener("pointermove", (event) => this.pointerMove(event));
    this.canvas.addEventListener("pointerup", (event) => this.pointerUp(event));
    this.canvas.addEventListener("pointercancel", (event) => this.pointerUp(event));
    this.canvas.addEventListener("dblclick", (event) => {
      const shape = this.hitTest(this.point(event));
      if (shape?.type !== "text") return;
      this.selectedId = shape.id;
      this.selectTool("select");
      this.syncControls(shape);
      this.control("text").focus();
      this.control("text").select();
      this.render();
    });
    this.root.tabIndex = 0;
    this.root.addEventListener("keydown", (event) => {
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
      if (!typing && (event.key === "Delete" || event.key === "Backspace")) {
        event.preventDefault();
        this.runAction("delete");
      }
      if (!typing && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        this.runAction(event.shiftKey ? "redo" : "undo");
      }
      if (!typing && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
        event.preventDefault();
        this.runAction("redo");
      }
      if (!typing && event.key.toLowerCase() === "v") this.selectTool("select");
      if (!typing && event.key.toLowerCase() === "r") this.selectTool("rectangle");
      if (!typing && event.key.toLowerCase() === "e") this.selectTool("ellipse");
      if (!typing && event.key.toLowerCase() === "a") this.selectTool("arrow");
      if (!typing && event.key.toLowerCase() === "b") this.selectTool("brush");
      if (!typing && event.key.toLowerCase() === "t") this.selectTool("text");
    });
  }

  selectTool(tool) {
    if (!TOOL_TYPES.has(tool)) return;
    this.tool = tool;
    this.root.querySelectorAll("[data-tool]").forEach((button) => {
      button.classList.toggle("active", button.dataset.tool === tool);
    });
    this.canvas.style.cursor = tool === "select" ? "default" : tool === "text" ? "text" : "crosshair";
  }

  styleFromControls(type) {
    return {
      type,
      color: this.control("color").value,
      width: finiteNumber(this.control("width").value, 8),
      opacity: finiteNumber(this.control("opacity").value, 100) / 100,
      dashed: this.control("dashed").checked,
    };
  }

  syncControls(shape) {
    this.control("color").value = shape.color;
    this.control("width").value = shape.width;
    this.control("opacity").value = Math.round(shape.opacity * 100);
    this.control("dashed").checked = shape.dashed;
    this.updateStyleLabels();
    if (shape.type === "text") {
      this.control("text").value = shape.text;
      this.control("font-size").value = shape.fontSize;
      const matching = [...this.control("font-family").options].find((option) => option.value === shape.fontFamily);
      if (matching) this.control("font-family").value = shape.fontFamily;
    }
  }

  applyControlsToSelection() {
    const shape = this.shapes.find((item) => item.id === this.selectedId);
    if (!shape) return;
    this.pushHistory();
    Object.assign(shape, this.styleFromControls(shape.type));
    if (shape.type === "text") {
      shape.text = this.control("text").value;
      shape.fontSize = finiteNumber(this.control("font-size").value, 48);
      shape.fontFamily = this.control("font-family").value;
    }
    this.persist();
    this.render();
  }

  applyZoom() {
    const zoom = finiteNumber(this.control("zoom").value, 100);
    this.canvas.style.width = `${zoom}%`;
    this.root.querySelector('[data-role="zoom-value"]').textContent = `${zoom}%`;
  }

  updateStyleLabels() {
    this.root.querySelector('[data-role="width-value"]').textContent = `${this.control("width").value}px`;
    this.root.querySelector('[data-role="opacity-value"]').textContent = `${this.control("opacity").value}%`;
  }

  point(event) {
    const bounds = this.canvas.getBoundingClientRect();
    return {
      x: clamp((event.clientX - bounds.left) * this.canvas.width / bounds.width, 0, this.canvas.width),
      y: clamp((event.clientY - bounds.top) * this.canvas.height / bounds.height, 0, this.canvas.height),
    };
  }

  visualTolerance() {
    const bounds = this.canvas.getBoundingClientRect();
    return bounds.width ? 9 * this.canvas.width / bounds.width : 9;
  }

  hitTest(point) {
    const tolerance = this.visualTolerance();
    return [...this.shapes].reverse().find((shape) => {
      const box = shapeBounds(shape, this.context);
      return point.x >= box.x1 - tolerance && point.x <= box.x2 + tolerance
        && point.y >= box.y1 - tolerance && point.y <= box.y2 + tolerance;
    }) ?? null;
  }

  isResizeHandle(point, shape) {
    if (!shape) return false;
    const box = shapeBounds(shape, this.context);
    const tolerance = this.visualTolerance() * 1.35;
    return Math.hypot(point.x - box.x2, point.y - box.y2) <= tolerance;
  }

  pointerDown(event) {
    if (event.button !== 0) return;
    if (!this.sourceImage.complete || !this.sourceImage.naturalWidth) return;
    event.preventDefault();
    this.root.focus({ preventScroll: true });
    this.canvas.setPointerCapture(event.pointerId);
    const point = this.point(event);
    if (this.tool === "select") {
      const selected = this.shapes.find((shape) => shape.id === this.selectedId);
      const resize = this.isResizeHandle(point, selected);
      const hit = resize ? selected : this.hitTest(point);
      this.selectedId = hit?.id ?? null;
      if (hit) {
        this.syncControls(hit);
        this.interaction = {
          mode: resize ? "resize" : "move",
          start: point,
          original: deepCopy(hit),
          changed: false,
        };
      } else if (this.canvas.hasPointerCapture(event.pointerId)) {
        this.canvas.releasePointerCapture(event.pointerId);
      }
      this.render();
      this.updateButtons();
      return;
    }

    if (this.tool === "text" && !this.control("text").value.trim()) {
      if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
      this.setMessage("请先在工具栏填写标注文字，再点击图片放置。", true);
      return;
    }
    this.pushHistory();
    const id = makeId();
    const shape = { id, ...this.styleFromControls(this.tool) };
    if (this.tool === "brush") {
      shape.points = [point];
    } else if (this.tool === "text") {
      Object.assign(shape, {
        x1: point.x,
        y1: point.y,
        text: this.control("text").value,
        fontSize: finiteNumber(this.control("font-size").value, 48),
        fontFamily: this.control("font-family").value,
      });
    } else {
      Object.assign(shape, { x1: point.x, y1: point.y, x2: point.x, y2: point.y });
    }
    this.shapes.push(shape);
    this.selectedId = id;
    this.interaction = this.tool === "text" ? null : { mode: "draw", start: point, original: deepCopy(shape) };
    if (this.tool === "text") {
      if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
      this.persist();
    }
    this.render();
    this.updateButtons();
  }

  pointerMove(event) {
    if (!this.interaction || !this.selectedId) return;
    event.preventDefault();
    const point = this.point(event);
    const shape = this.shapes.find((item) => item.id === this.selectedId);
    if (!shape) return;
    if (["move", "resize"].includes(this.interaction.mode) && !this.interaction.changed) {
      this.pushHistory();
      this.interaction.changed = true;
    }
    if (this.interaction.mode === "draw") {
      if (shape.type === "brush") {
        const previous = shape.points.at(-1);
        if (!previous || Math.hypot(point.x - previous.x, point.y - previous.y) >= 1) shape.points.push(point);
      } else {
        let end = point;
        if (event.shiftKey && ["rectangle", "ellipse"].includes(shape.type)) {
          const dx = point.x - shape.x1;
          const dy = point.y - shape.y1;
          const length = Math.max(Math.abs(dx), Math.abs(dy));
          end = {
            x: shape.x1 + Math.sign(dx || 1) * length,
            y: shape.y1 + Math.sign(dy || 1) * length,
          };
        } else if (event.shiftKey && shape.type === "arrow") {
          const dx = point.x - shape.x1;
          const dy = point.y - shape.y1;
          const length = Math.hypot(dx, dy);
          const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * (Math.PI / 4);
          end = { x: shape.x1 + Math.cos(angle) * length, y: shape.y1 + Math.sin(angle) * length };
        }
        shape.x2 = clamp(end.x, 0, this.canvas.width);
        shape.y2 = clamp(end.y, 0, this.canvas.height);
      }
    } else if (this.interaction.mode === "move") {
      this.moveShape(shape, this.interaction.original, point.x - this.interaction.start.x, point.y - this.interaction.start.y);
    } else if (this.interaction.mode === "resize") {
      this.resizeShape(shape, this.interaction.original, point);
    }
    this.render();
  }

  pointerUp(event) {
    if (!this.interaction) return;
    event.preventDefault();
    if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
    const shape = this.shapes.find((item) => item.id === this.selectedId);
    if (shape && ["rectangle", "ellipse", "arrow"].includes(shape.type)) {
      if (Math.hypot(shape.x2 - shape.x1, shape.y2 - shape.y1) < 2) {
        this.shapes = this.shapes.filter((item) => item.id !== shape.id);
        this.selectedId = null;
        if (this.interaction.mode === "draw") this.undoStack.pop();
      }
    }
    this.interaction = null;
    this.persist();
    this.render();
    this.updateButtons();
  }

  moveShape(shape, original, dx, dy) {
    if (shape.type === "brush") {
      shape.points = original.points.map((point) => ({ x: point.x + dx, y: point.y + dy }));
      return;
    }
    shape.x1 = original.x1 + dx;
    shape.y1 = original.y1 + dy;
    if (shape.type !== "text") {
      shape.x2 = original.x2 + dx;
      shape.y2 = original.y2 + dy;
    }
  }

  resizeShape(shape, original, point) {
    const box = shapeBounds(original, this.context);
    const scaleX = Math.max(0.05, (point.x - box.x1) / Math.max(1, box.x2 - box.x1));
    const scaleY = Math.max(0.05, (point.y - box.y1) / Math.max(1, box.y2 - box.y1));
    const transform = (source) => ({
      x: box.x1 + (source.x - box.x1) * scaleX,
      y: box.y1 + (source.y - box.y1) * scaleY,
    });
    if (shape.type === "brush") {
      shape.points = original.points.map(transform);
    } else if (shape.type === "text") {
      const anchor = transform({ x: original.x1, y: original.y1 });
      shape.x1 = anchor.x;
      shape.y1 = anchor.y;
      shape.fontSize = clamp(original.fontSize * Math.max(scaleX, scaleY), 8, 500);
      this.control("font-size").value = Math.round(shape.fontSize);
    } else {
      const start = transform({ x: original.x1, y: original.y1 });
      const end = transform({ x: original.x2, y: original.y2 });
      Object.assign(shape, { x1: start.x, y1: start.y, x2: end.x, y2: end.y });
    }
  }

  pushHistory() {
    this.undoStack.push(deepCopy(this.shapes));
    if (this.undoStack.length > MAX_HISTORY) this.undoStack.shift();
    this.redoStack = [];
  }

  runAction(action) {
    if (action === "undo" && this.undoStack.length) {
      this.redoStack.push(deepCopy(this.shapes));
      this.shapes = this.undoStack.pop();
      this.selectedId = null;
    } else if (action === "redo" && this.redoStack.length) {
      this.undoStack.push(deepCopy(this.shapes));
      this.shapes = this.redoStack.pop();
      this.selectedId = null;
    } else if (action === "delete" && this.selectedId) {
      this.pushHistory();
      this.shapes = this.shapes.filter((shape) => shape.id !== this.selectedId);
      this.selectedId = null;
    } else if (action === "clear" && this.shapes.length) {
      this.pushHistory();
      this.shapes = [];
      this.selectedId = null;
    } else {
      this.updateButtons();
      return;
    }
    this.persist();
    this.render();
    this.updateButtons();
  }

  restorePayload() {
    if (!this.dataWidget.value) return null;
    try {
      const payload = JSON.parse(this.dataWidget.value);
      if (payload?.version !== 1) return null;
      return payload;
    } catch (error) {
      console.warn("[SenseNova Annotation Canvas] 无法恢复标注数据:", error);
      return null;
    }
  }

  async loadImage(value, forceReset = false) {
    const source = String(value ?? "").trim();
    const sequence = ++this.loadSequence;
    this.sourceName = source;
    this.sourceImage = new Image();
    this.empty.hidden = false;
    this.empty.textContent = source ? "正在加载图片…" : "请使用节点上方的上传按钮选择图片";
    if (!source) {
      this.shapes = [];
      this.canvas.width = 1;
      this.canvas.height = 1;
      this.render();
      return;
    }
    const image = new Image();
    image.decoding = "async";
    image.onload = () => {
      if (sequence !== this.loadSequence) return;
      this.sourceImage = image;
      this.canvas.width = image.naturalWidth;
      this.canvas.height = image.naturalHeight;
      const saved = this.restorePayload();
      const compatible = !forceReset
        && saved?.source === source
        && saved?.width === image.naturalWidth
        && saved?.height === image.naturalHeight;
      this.shapes = compatible ? sanitizeShapes(saved.shapes) : [];
      this.selectedId = null;
      this.undoStack = [];
      this.redoStack = [];
      this.empty.hidden = true;
      if (!compatible && this.dataWidget.value) this.persist();
      this.render();
      this.updateButtons();
      this.setMessage(`已加载 ${image.naturalWidth} × ${image.naturalHeight}`);
    };
    image.onerror = () => {
      if (sequence !== this.loadSequence) return;
      this.empty.hidden = false;
      this.empty.textContent = "图片加载失败，请重新选择或上传";
      this.setMessage("无法从 ComfyUI input 目录读取这张图片。", true);
    };
    image.src = imageViewUrl(source);
  }

  render() {
    const context = this.context;
    context.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (this.sourceImage.complete && this.sourceImage.naturalWidth) {
      context.drawImage(this.sourceImage, 0, 0, this.canvas.width, this.canvas.height);
    }
    this.shapes.forEach((shape) => drawShape(context, shape));
    const selected = this.shapes.find((shape) => shape.id === this.selectedId);
    if (selected) this.drawSelection(selected);
    this.count.textContent = `${this.shapes.length} 个标注`;
    this.node.setDirtyCanvas?.(true, true);
  }

  drawSelection(shape) {
    const context = this.context;
    const box = shapeBounds(shape, context);
    const scale = this.canvas.width / Math.max(1, this.canvas.getBoundingClientRect().width);
    const padding = 5 * scale;
    const handle = 6 * scale;
    context.save();
    context.strokeStyle = "#8ab4f8";
    context.fillStyle = "#ffffff";
    context.lineWidth = 1.5 * scale;
    context.setLineDash([5 * scale, 4 * scale]);
    context.strokeRect(box.x1 - padding, box.y1 - padding, box.x2 - box.x1 + padding * 2, box.y2 - box.y1 + padding * 2);
    context.setLineDash([]);
    context.fillRect(box.x2 - handle, box.y2 - handle, handle * 2, handle * 2);
    context.strokeRect(box.x2 - handle, box.y2 - handle, handle * 2, handle * 2);
    context.restore();
  }

  persist() {
    if (!this.sourceImage.naturalWidth) return;
    if (!this.shapes.length) {
      this.dataWidget.value = "";
    } else {
      const overlay = document.createElement("canvas");
      overlay.width = this.canvas.width;
      overlay.height = this.canvas.height;
      const overlayContext = overlay.getContext("2d");
      this.shapes.forEach((shape) => drawShape(overlayContext, shape));
      this.dataWidget.value = JSON.stringify({
        version: 1,
        source: this.sourceName,
        width: this.canvas.width,
        height: this.canvas.height,
        shapes: this.shapes,
        overlay: overlay.toDataURL("image/png"),
      });
    }
    this.dataWidget.callback?.(this.dataWidget.value);
    this.node.setDirtyCanvas?.(true, true);
  }

  writeSerializedValue(serialized) {
    if (!Array.isArray(serialized?.widgets_values)) return;
    let serializedIndex = 0;
    for (const widget of this.node.widgets ?? []) {
      if (widget.options?.serialize === false) continue;
      if (widget === this.dataWidget) {
        serialized.widgets_values[serializedIndex] = this.dataWidget.value;
        return;
      }
      serializedIndex += 1;
    }
  }

  setMessage(text, error = false) {
    this.message.textContent = text;
    this.message.classList.toggle("error", error);
  }

  updateButtons() {
    this.root.querySelector('[data-action="undo"]').disabled = !this.undoStack.length;
    this.root.querySelector('[data-action="redo"]').disabled = !this.redoStack.length;
    this.root.querySelector('[data-action="delete"]').disabled = !this.selectedId;
    this.root.querySelector('[data-action="clear"]').disabled = !this.shapes.length;
  }
}

function createEditorElement() {
  const root = document.createElement("div");
  root.className = "sn-annotation-root";
  root.innerHTML = `
    <div class="sn-annotation-toolbar" aria-label="标注工具">
      <button type="button" data-tool="select" title="选择、移动或缩放标注 (V)">选择</button>
      <button type="button" data-tool="rectangle" title="矩形定位框 (R)">矩形</button>
      <button type="button" data-tool="ellipse" title="椭圆或圆圈 (E)">椭圆</button>
      <button type="button" data-tool="arrow" title="箭头 (A)">箭头</button>
      <button type="button" data-tool="brush" title="自由画笔 (B)">画笔</button>
      <button type="button" data-tool="text" title="文字标注 (T)">文字</button>
      <span class="sn-annotation-divider"></span>
      <button type="button" data-action="undo" title="撤销 (Ctrl/Cmd+Z)">撤销</button>
      <button type="button" data-action="redo" title="重做 (Ctrl/Cmd+Shift+Z)">重做</button>
      <button type="button" data-action="delete" title="删除选中标注 (Delete)">删除</button>
      <button type="button" data-action="clear" title="清空全部标注">清空</button>
    </div>
    <div class="sn-annotation-toolbar" aria-label="标注样式">
      <label class="sn-annotation-field">颜色 <input data-control="color" type="color" value="#ff3b30"></label>
      <button type="button" class="sn-annotation-swatch" data-color="#ff3b30" style="--swatch:#ff3b30" title="红色" aria-label="使用红色"></button>
      <button type="button" class="sn-annotation-swatch" data-color="#ffcc00" style="--swatch:#ffcc00" title="黄色" aria-label="使用黄色"></button>
      <button type="button" class="sn-annotation-swatch" data-color="#00c7ff" style="--swatch:#00c7ff" title="青色" aria-label="使用青色"></button>
      <button type="button" class="sn-annotation-swatch" data-color="#34c759" style="--swatch:#34c759" title="绿色" aria-label="使用绿色"></button>
      <label class="sn-annotation-field">线宽 <input data-control="width" type="range" min="1" max="60" value="8"><span data-role="width-value">8px</span></label>
      <label class="sn-annotation-field">透明度 <input data-control="opacity" type="range" min="5" max="100" value="100"><span data-role="opacity-value">100%</span></label>
      <label class="sn-annotation-field"><input data-control="dashed" type="checkbox"> 虚线</label>
      <span class="sn-annotation-divider"></span>
      <label class="sn-annotation-field">缩放 <input data-control="zoom" type="range" min="25" max="200" step="5" value="100"><span data-role="zoom-value">100%</span></label>
    </div>
    <div class="sn-annotation-toolbar" aria-label="文字设置">
      <textarea class="sn-annotation-text" data-control="text" rows="1" maxlength="2000" placeholder="输入说明文字；支持换行，然后选择“文字”并点击图片"></textarea>
      <label class="sn-annotation-field">字号 <input data-control="font-size" type="number" min="8" max="500" value="48" style="width:64px"></label>
      <select data-control="font-family" title="文字风格">
        <option value="ui-sans-serif, system-ui, sans-serif">无衬线</option>
        <option value="'Kaiti SC', STKaiti, KaiTi, cursive">手写/楷体</option>
        <option value="ui-serif, Georgia, 'Songti SC', SimSun, serif">衬线/宋体</option>
      </select>
    </div>
    <div class="sn-annotation-canvas-shell">
      <canvas width="1" height="1" aria-label="SenseNova 图片标注画布"></canvas>
      <div class="sn-annotation-empty">请使用节点上方的上传按钮选择图片</div>
    </div>
    <div class="sn-annotation-status">
      <span data-role="message">上传图片后即可直接标注</span>
      <span><span data-role="count">0 个标注</span> · <span class="sn-annotation-kbd">选择工具可移动/缩放</span></span>
    </div>
  `;
  return root;
}

function chain(node, method, callback) {
  const original = node[method];
  node[method] = function (...args) {
    const result = original?.apply(this, args);
    callback.apply(this, args);
    return result;
  };
}

app.registerExtension({
  name: "eastmoe.ComfyEasySenseNovaU1.AnnotationCanvas",
  async nodeCreated(node) {
    if ((node.comfyClass ?? node.type) !== NODE_CLASS) return;
    installStyles();
    const imageWidget = node.widgets?.find((widget) => widget.name === "image");
    const dataWidget = node.widgets?.find((widget) => widget.name === "annotation_data");
    if (!imageWidget || !dataWidget) {
      console.error("[SenseNova Annotation Canvas] 找不到 image 或 annotation_data 控件。");
      return;
    }

    dataWidget.type = "hidden";
    dataWidget.computeSize = () => [0, -4];
    const root = createEditorElement();
    const editor = new AnnotationEditor(node, root, imageWidget, dataWidget);
    node.senseNovaAnnotationEditor = editor;
    node.addDOMWidget("sensenova_annotation_editor", "annotation-canvas", root, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => 600,
      getHeight: () => 820,
    });

    const originalImageCallback = imageWidget.callback;
    imageWidget.callback = function (...args) {
      const result = originalImageCallback?.apply(this, args);
      const nextSource = String(imageWidget.value ?? "").trim();
      editor.loadImage(nextSource, nextSource !== editor.sourceName);
      return result;
    };
    chain(node, "onConfigure", () => editor.loadImage(imageWidget.value));
    chain(node, "onSerialize", (serialized) => {
      editor.persist();
      editor.writeSerializedValue(serialized);
    });
    chain(node, "onRemoved", () => { editor.loadSequence += 1; });
    if (node.size?.[0] < 700 || node.size?.[1] < 900) node.setSize?.([760, 980]);
    editor.loadImage(imageWidget.value);
  },
});
