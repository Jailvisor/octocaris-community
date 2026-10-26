"""Validate the flat catalog before it is pushed."""

import json
import re
import subprocess
from pathlib import Path

from .config import ASSET_BASE
from .ids import VERSION_RE, validate_id
from .text import name_problems

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_INDEX_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_FILES = 1_000


def validate(root: Path, check_assets: bool = False, strict: bool = False,
             tracked: bool = False) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []

    index_path = root / "index.json"
    if not index_path.is_file():
        return ["index.json is missing"]
    if index_path.stat().st_size > MAX_INDEX_BYTES:
        errors.append(f"index.json is larger than {MAX_INDEX_BYTES} bytes")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"index.json is not valid JSON: {error}"]

    if index.get("schemaVersion") != 1:
        errors.append(f"unsupported schemaVersion {index.get('schemaVersion')!r}")
    items = index.get("items") or []
    if index.get("itemCount") != len(items):
        errors.append("index itemCount does not match items length")

    seen: set[str] = set()
    for item in items:
        item_id = item.get("folder", "")
        where = f"item {item_id!r}"
        if not validate_id(item_id):
            errors.append(f"{where}: folder must be a numeric Workshop id")
        if item_id in seen:
            errors.append(f"{where}: duplicate folder")
        seen.add(item_id)
        for problem in name_problems(str(item.get("name", ""))):
            warnings.append(f"{where}: name {problem}")
        if not VERSION_RE.fullmatch(str(item.get("version", ""))):
            errors.append(f"{where}: invalid version")
        download = item.get("download") or {}
        if not str(download.get("url", "")).startswith(ASSET_BASE + "/"):
            errors.append(f"{where}: download url outside {ASSET_BASE}")
        expected_asset = f"octocaris-{item_id}-v{item.get('version')}.zip"
        if download.get("url", "").rsplit("/", 1)[-1] != expected_asset:
            errors.append(f"{where}: asset name should be {expected_asset}")
        if not SHA_RE.fullmatch(str(download.get("sha256", ""))):
            errors.append(f"{where}: invalid sha256")
        size = download.get("bytes")
        if not isinstance(size, int) or not 0 < size <= MAX_ARCHIVE_BYTES:
            errors.append(f"{where}: invalid archive size")
        preview = item.get("preview") or {}
        relative = str(preview.get("url", ""))
        if not relative.startswith("previews/"):
            errors.append(f"{where}: preview url must start with previews/")
        elif not (root / relative.split("?", 1)[0]).is_file():
            errors.append(f"{where}: preview file missing")
        if not (root / "thumbs" / f"{item_id}.webp").is_file():
            warnings.append(f"{where}: thumbnail missing")
        source = item.get("source") or {}
        if source.get("workshopId") != item_id:
            errors.append(f"{where}: source.workshopId must match folder")
        files = item.get("files") or []
        paths = [record.get("path") for record in files]
        if paths != sorted(paths):
            errors.append(f"{where}: files are not sorted")
        if len(files) > MAX_FILES:
            errors.append(f"{where}: more than {MAX_FILES} files in the index")
        file_count = item.get("fileCount")
        if not isinstance(file_count, int) or file_count < len(files):
            errors.append(f"{where}: fileCount smaller than the file list")
        truncated = bool(item.get("filesTruncated"))
        if file_count > len(files) and not truncated:
            errors.append(f"{where}: fileCount exceeds the list but filesTruncated is false")
        if file_count == len(files) and truncated:
            warnings.append(f"{where}: filesTruncated is true but nothing was truncated")
        if "id" in item or "aliases" in item or "thumbnail" in item:
            warnings.append(f"{where}: legacy id/aliases/thumbnail field")

    if check_assets:
        from .gh import assets

        remote = assets()
        for item in items:
            asset = item["download"]["url"].rsplit("/", 1)[-1]
            info = remote.get(asset)
            if not info:
                errors.append(f"release asset missing: {asset}")
                continue
            if info.get("size") != item["download"]["bytes"]:
                errors.append(f"release asset size mismatch: {asset}")
                continue
            digest = info.get("digest") or ""
            if digest and digest != f"sha256:{item['download']['sha256']}":
                errors.append(f"release asset digest mismatch: {asset}")

    if tracked:
        result = subprocess.run(
            ["git", "ls-files", "--", "previews", "thumbs"],
            cwd=root, text=True, capture_output=True,
        )
        tracked_files = set(result.stdout.splitlines()) if result.returncode == 0 else set()
        referenced = set()
        for item in items:
            referenced.add(str((item.get("preview") or {}).get("url", "")).split("?", 1)[0])
            referenced.add(f"thumbs/{item['folder']}.webp")
        for path in sorted(tracked_files - referenced):
            errors.append(f"tracked but unreferenced: {path}")

    if strict:
        errors.extend(f"warning: {warning}" for warning in warnings)
        warnings = []
    for warning in warnings:
        print(f"warning: {warning}")
    return errors
