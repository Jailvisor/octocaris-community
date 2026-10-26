"""Deterministic wallpaper zips plus the file inventory stored in index.json."""

import hashlib
import json
import zipfile
from pathlib import Path

MAX_ENTRIES = 10_000
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
MAX_FILES_IN_INDEX = 1_000
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db", "octos-community.json", "desktop.ini"}
MANIFEST_NAMES = ("octos.json", "mod.json")


class PackError(RuntimeError):
    pass


def read_json(path: Path):
    # Wallpaper Engine writes project.json with a UTF-8 BOM.
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def project_metadata(folder: Path) -> dict | None:
    path = folder / "project.json"
    if not path.is_file():
        return None
    try:
        project = read_json(path)
    except (OSError, json.JSONDecodeError):
        return None
    if str(project.get("type", "")).strip().lower() != "web":
        return None
    return project


def octos_manifest(folder: Path) -> dict | None:
    for name in MANIFEST_NAMES:
        path = folder / name
        if path.is_file():
            try:
                return read_json(path)
            except (OSError, json.JSONDecodeError):
                return None
    return None


def iter_files(folder: Path) -> list[str]:
    entries: list[str] = []
    for path in folder.rglob("*"):
        if path.is_dir():
            continue
        if path.is_symlink():
            raise PackError(f"refusing to pack symlink: {path}")
        if path.name in EXCLUDED_NAMES or path.suffix.lower() == ".lnk":
            continue
        relative = path.relative_to(folder).as_posix()
        if relative.startswith("."):
            continue
        entries.append(relative)
    entries.sort()
    if len(entries) > MAX_ENTRIES:
        raise PackError(f"{folder} has {len(entries)} files (limit {MAX_ENTRIES})")
    return entries


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fingerprint(folder: Path) -> str:
    digest = hashlib.sha256()
    for relative in iter_files(folder):
        data = (folder / relative).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(data).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_manifest(folder: Path, version: str, *, name: str, author: str,
                   description: str, source_url: str | None, entry: str) -> dict:
    manifest = octos_manifest(folder)
    if manifest is None:
        project = project_metadata(folder)
        if project is None:
            raise PackError(f"{folder} is not an Octos mod or a Wallpaper Engine web package")
        manifest = {
            "name": name,
            "author": author,
            "description": description,
            "image": str(project.get("preview") or ""),
            "entry": entry,
        }
    manifest = dict(manifest)
    manifest["name"] = name
    manifest["version"] = version
    manifest["entry"] = entry
    if description:
        manifest["description"] = description
    if author:
        manifest["author"] = author
    if source_url:
        manifest["source"] = source_url
    return manifest


def _zipinfo(relative: str, folder_name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(f"{folder_name}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0o100644 << 16
    return info


def pack(folder: Path, folder_name: str, out_path: Path, version: str, *,
         name: str, author: str, description: str, source_url: str | None,
         entry: str) -> dict:
    files = iter_files(folder)
    manifest = build_manifest(
        folder, version, name=name, author=author, description=description,
        source_url=source_url, entry=entry,
    )
    manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    has_manifest = any(relative in MANIFEST_NAMES for relative in files)

    sizes = {relative: (folder / relative).stat().st_size for relative in files}
    total = sum(sizes.values())
    if not has_manifest:
        total += len(manifest_bytes)
    if total > MAX_TOTAL_UNCOMPRESSED:
        raise PackError(f"{folder} is {total} bytes uncompressed (limit {MAX_TOTAL_UNCOMPRESSED})")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as archive:
        for relative in files:
            if relative in MANIFEST_NAMES:
                data = manifest_bytes
            else:
                data = (folder / relative).read_bytes()
            archive.writestr(_zipinfo(relative, folder_name), data, compresslevel=9)
        if not has_manifest:
            archive.writestr(_zipinfo("octos.json", folder_name), manifest_bytes, compresslevel=9)

    records = [{"path": relative, "bytes": len(manifest_bytes) if relative in MANIFEST_NAMES
                else sizes[relative]} for relative in files]
    if not has_manifest:
        records.append({"path": "octos.json", "bytes": len(manifest_bytes)})
    records.sort(key=lambda record: record["path"])
    file_count = len(records)
    truncated = file_count > MAX_FILES_IN_INDEX
    records = records[:MAX_FILES_IN_INDEX]

    digest = hashlib.sha256()
    with out_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return {
        "bytes": out_path.stat().st_size,
        "sha256": digest.hexdigest(),
        "fileCount": file_count,
        "files": records,
        "filesTruncated": truncated,
        "fingerprint": fingerprint(folder),
    }
