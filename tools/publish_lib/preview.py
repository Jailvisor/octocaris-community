"""Animated previews for the catalog plus static thumbnails for the README.

Previews stay GIF so the app's preview cache and WebView2 path keep working.
The optimizer keeps every other frame at 64 colors, which halves the repository
size without touching the source package.
"""

import hashlib
import io
import json
from pathlib import Path

MAX_PREVIEW_BYTES = 8 * 1024 * 1024
PREVIEW_COLORS = 64
FRAME_STEP = 2
THUMB_WIDTH = 150

try:  # Pillow is optional: without it previews are copied unchanged.
    from PIL import Image, ImageChops, ImageSequence
except Exception:  # pragma: no cover - exercised only without Pillow
    Image = None


def choose_preview(folder: Path, manifest: dict | None) -> Path | None:
    candidates = []
    project = folder / "project.json"
    if project.is_file():
        try:
            data = json.loads(project.read_text(encoding="utf-8-sig"))
            if data.get("preview"):
                candidates.append(folder / str(data["preview"]))
        except (OSError, ValueError):
            pass
    if manifest:
        for key in ("preview", "image"):
            if manifest.get(key):
                candidates.append(folder / str(manifest[key]))
    candidates.extend([folder / "preview.gif", folder / "preview.png", folder / "preview.jpg"])
    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size <= MAX_PREVIEW_BYTES:
            return candidate
    return None


def optimize_gif(data: bytes) -> bytes | None:
    if Image is None:
        return None
    try:
        source = Image.open(io.BytesIO(data))
        if getattr(source, "n_frames", 1) < 2:
            return None
        duration = int(source.info.get("duration") or 40)
        frames = []
        previous = None
        for index, frame in enumerate(ImageSequence.Iterator(source)):
            if index % FRAME_STEP:
                continue
            rgb = frame.convert("RGB")
            if previous is not None and ImageChops.difference(rgb, previous).getbbox() is None:
                continue
            previous = rgb
            frames.append(rgb.convert("P", palette=Image.Palette.ADAPTIVE, colors=PREVIEW_COLORS))
        if len(frames) < 2:
            return None
        buffer = io.BytesIO()
        frames[0].save(
            buffer, format="GIF", save_all=True, append_images=frames[1:],
            duration=duration * FRAME_STEP, loop=0, optimize=True, disposal=2,
        )
        return buffer.getvalue()
    except Exception:
        return None


def build_thumb(data: bytes) -> bytes | None:
    if Image is None:
        return None
    try:
        source = Image.open(io.BytesIO(data))
        frames = getattr(source, "n_frames", 1)
        if frames > 1:
            source.seek(frames // 2)
        image = source.convert("RGB")
        image.thumbnail((THUMB_WIDTH, THUMB_WIDTH), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=80, method=4)
        return buffer.getvalue()
    except Exception:
        return None


def _write_if_changed(path: Path, data: bytes) -> None:
    if path.is_file() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(data)
    temporary.replace(path)


def install_preview(source: Path, previews_dir: Path, thumbs_dir: Path, item_id: str) -> dict:
    original = source.read_bytes()
    data = original
    if source.suffix.lower() == ".gif":
        optimized = optimize_gif(original)
        if optimized and len(optimized) < len(original):
            data = optimized

    suffix = source.suffix.lower() or ".gif"
    destination = previews_dir / f"{item_id}{suffix}"
    _write_if_changed(destination, data)

    thumb_bytes = build_thumb(original)
    thumb_path = None
    if thumb_bytes:
        thumb = thumbs_dir / f"{item_id}.webp"
        _write_if_changed(thumb, thumb_bytes)
        thumb_path = thumb.relative_to(previews_dir.parent).as_posix()

    width = height = None
    if Image is not None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
        except Exception:
            width = height = None

    return {
        "file": destination.name,
        "bytes": len(data),
        "sha8": hashlib.sha256(data).hexdigest()[:8],
        "width": width,
        "height": height,
        "thumb": thumb_path,
        "thumb_bytes": len(thumb_bytes) if thumb_bytes else 0,
    }
