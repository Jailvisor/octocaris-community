#!/usr/bin/env python3
"""Package and publish the Octocaris community catalog.

The repository is flat: `index.json` is the catalog, `previews/<id>.gif` holds the
animated preview, `thumbs/<id>.webp` the still used by README.md, and the zip
archives live in the GitHub release. The folder key is the Steam Workshop id.

    python tools/publish.py scan
    python tools/publish.py build --only 3253308696
    python tools/publish.py upload --only 3253308696
    python tools/publish.py render && python tools/publish.py push
    python tools/publish.py build && python tools/publish.py upload && python tools/publish.py render
    python tools/publish.py validate --strict --check-assets
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_lib import catalog, gh, packer, preview, text, validate  # noqa: E402
from publish_lib.config import ASSET_BASE, AUTHOR, SOURCE_KIND, WORKSHOP_URL  # noqa: E402
from publish_lib.ids import VERSION_RE, bump_version, validate_id  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
PREVIEWS = ROOT / "previews"
THUMBS = ROOT / "thumbs"
CACHE_PATH = ROOT / ".publish-cache.json"
DEFAULT_SOURCE = os.environ.get("COMMUNITY_SOURCE", "/mnt/c/fileHub/wallpaper")
SKIP_NAMES = {"default", "conformance", "monitor-probe"}


def load_cache() -> dict:
    if not CACHE_PATH.is_file():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(
        json.dumps(cache, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def now_utc() -> str:
    return catalog.now_iso()


def source_items(root: Path) -> list[Path]:
    folders = []
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or folder.name in SKIP_NAMES:
            continue
        if packer.project_metadata(folder) is None:
            continue
        folders.append(folder)
    return folders


def item_id(folder: Path, project: dict) -> str:
    value = str(project.get("workshopid") or "").strip()
    if not value and folder.name.isdigit():
        value = folder.name
    return value


def selected(folder: Path, project: dict, only: set[str] | None) -> bool:
    if not only:
        return True
    identifier = item_id(folder, project)
    return identifier in only or folder.name in only


def resolve_version(cache_entry: dict | None, fingerprint: str, args,
                    allow_default_bump: bool) -> str:
    explicit = getattr(args, "version", None)
    if explicit:
        if not VERSION_RE.fullmatch(explicit):
            raise SystemExit(f"invalid --version {explicit!r}")
        return explicit
    if cache_entry and cache_entry.get("fingerprint") == fingerprint and not getattr(args, "all", False):
        return cache_entry["version"]
    if cache_entry:
        part = getattr(args, "bump", None) or ("patch" if allow_default_bump else None)
        if not part:
            raise SystemExit("content changed; pass --bump major|minor|patch or --version")
        return bump_version(cache_entry["version"], part)
    return "1.0.0"


def build_one(folder: Path, args, cache: dict, allow_default_bump: bool) -> dict:
    project = packer.project_metadata(folder)
    if project is None:
        raise SystemExit("not a Wallpaper Engine web package")
    identifier = item_id(folder, project)
    if not validate_id(identifier):
        raise SystemExit(f"missing or invalid workshopid {identifier!r}")
    name = folder.name
    problems = text.name_problems(name)
    if problems:
        raise SystemExit(f"folder name is not standard: {', '.join(problems)}")

    if identifier in cache and cache[identifier].get("source") != str(folder.resolve()):
        raise SystemExit(f"workshopid {identifier} is already used by {cache[identifier]['source']}")

    cached = cache.get(identifier)
    fingerprint = packer.fingerprint(folder)
    version = resolve_version(cached, fingerprint, args, allow_default_bump)
    asset = catalog.asset_name(identifier, version)
    dist_path = DIST / asset
    changed = not cached or cached.get("fingerprint") != fingerprint or cached.get("version") != version
    need_pack = (
        changed
        or getattr(args, "all", False)
        or getattr(args, "force_repack", False)
        or cached.get("asset") != asset
        or not dist_path.is_file()
    )

    description = text.sanitize_description(project.get("description"))
    entry = str(project.get("file") or "index.html")
    workshop_url = WORKSHOP_URL.format(id=identifier)

    if need_pack:
        packed = packer.pack(
            folder, identifier, dist_path, version,
            name=name, author=AUTHOR, description=description,
            source_url=workshop_url, entry=entry,
        )
    else:
        packed = {
            "bytes": cached["bytes"],
            "sha256": cached["sha256"],
            "fileCount": cached["fileCount"],
            "files": cached["files"],
            "filesTruncated": cached["filesTruncated"],
            "fingerprint": fingerprint,
        }

    manifest = packer.octos_manifest(folder) or {}
    preview_source = preview.choose_preview(folder, manifest)
    if preview_source is None:
        raise SystemExit("no preview image found")
    installed = preview.install_preview(preview_source, PREVIEWS, THUMBS, identifier)
    for stale in PREVIEWS.glob(f"{identifier}.*"):
        if stale.name != installed["file"]:
            stale.unlink()

    updated_at = now_utc() if changed else cached.get("updatedAt") or now_utc()
    cache_entry = {
        "id": identifier,
        "source": str(folder.resolve()),
        "name": name,
        "description": description,
        "entry": entry,
        "fingerprint": fingerprint,
        "version": version,
        "asset": asset,
        "bytes": packed["bytes"],
        "sha256": packed["sha256"],
        "fileCount": packed["fileCount"],
        "filesTruncated": packed["filesTruncated"],
        "files": packed["files"],
        "preview": installed,
        "updatedAt": updated_at,
        "uploaded": bool((cached or {}).get("uploaded")) and not changed,
    }
    cache[identifier] = cache_entry
    return cache_entry


def scan_line(folder: Path, args, cache: dict) -> dict | None:
    project = packer.project_metadata(folder)
    if project is None or not selected(folder, project, args.only):
        return None
    identifier = item_id(folder, project)
    cached = cache.get(identifier)
    fingerprint = packer.fingerprint(folder)
    size = sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())
    state = "new"
    if cached:
        state = "uploaded" if cached.get("uploaded") else "built"
        if cached.get("fingerprint") != fingerprint:
            state = "changed"
    return {
        "id": identifier,
        "name": folder.name,
        "bytes": size,
        "state": state,
        "problems": ([] if validate_id(identifier) else ["invalid workshopid"]) + text.name_problems(folder.name),
    }


def command_scan(args) -> None:
    root = Path(args.root or DEFAULT_SOURCE).resolve()
    cache = load_cache()
    rows = [row for folder in source_items(root) if (row := scan_line(folder, args, cache))]
    rows.sort(key=lambda row: row["name"].casefold())
    total = 0
    for row in rows:
        total += row["bytes"]
        warning = f"  !! {'; '.join(row['problems'])}" if row["problems"] else ""
        print(f"{row['id']:>12}  {row['state']:<8} {catalog.human_size(row['bytes']):>9}  {row['name']}{warning}")
    print(f"\n{len(rows)} item(s), {catalog.human_size(total)} unpacked")
    if args.limit:
        print(f"(build --limit {args.limit} will take the first {args.limit} by name)")


def command_build(args) -> None:
    root = Path(args.root or DEFAULT_SOURCE).resolve()
    cache = load_cache()
    folders = []
    for folder in source_items(root):
        project = packer.project_metadata(folder)
        if project is not None and selected(folder, project, args.only):
            folders.append((folder.name.casefold(), folder))
    folders.sort()
    if args.limit:
        folders = folders[:args.limit]
    if not folders:
        raise SystemExit("no wallpaper folders matched")

    failures = 0
    started = time.time()
    for index, (_, folder) in enumerate(folders, 1):
        try:
            entry = build_one(folder, args, cache, allow_default_bump=True)
            state = "uploaded" if entry["uploaded"] else "built"
            print(
                f"[{index}/{len(folders)}] {entry['id']} v{entry['version']} "
                f"{catalog.human_size(entry['bytes'])} preview {catalog.human_size(entry['preview']['bytes'])} "
                f"{state}  {entry['name']}"
            )
        except (SystemExit, packer.PackError) as error:
            failures += 1
            message = error.code if isinstance(error, SystemExit) and error.code else error
            print(f"[{index}/{len(folders)}] {folder.name}: {message}")
        if index % 10 == 0:
            save_cache(cache)
    save_cache(cache)
    print(f"built {len(folders) - failures}/{len(folders)} in {time.time() - started:.0f}s")
    if failures:
        raise SystemExit(1)


def item_from_cache(entry: dict) -> dict:
    identifier = entry["id"]
    preview_info = entry["preview"]
    preview_object = {
        "url": f"previews/{preview_info['file']}?v={preview_info['sha8']}",
        "bytes": preview_info["bytes"],
    }
    if preview_info.get("width"):
        preview_object["width"] = preview_info["width"]
    if preview_info.get("height"):
        preview_object["height"] = preview_info["height"]
    return {
        "folder": identifier,
        "name": entry["name"],
        "author": AUTHOR,
        "description": entry.get("description", ""),
        "version": entry["version"],
        "tags": [],
        "entry": entry.get("entry", "index.html"),
        "license": "unknown",
        "preview": preview_object,
        "download": {
            "url": f"{ASSET_BASE}/{entry['asset']}",
            "bytes": entry["bytes"],
            "sha256": entry["sha256"],
        },
        "fileCount": entry["fileCount"],
        "filesTruncated": entry["filesTruncated"],
        "files": entry["files"],
        "source": {
            "kind": SOURCE_KIND,
            "workshopId": identifier,
            "workshopUrl": WORKSHOP_URL.format(id=identifier),
        },
        "pageUrl": catalog.page_url(identifier),
        "updatedAt": entry["updatedAt"],
    }


def command_render(args) -> None:
    cache = load_cache()
    only = set(part.strip() for part in args.only.split(",")) if args.only else None
    entries = [
        entry for entry in cache.values()
        if (only is None or entry["id"] in only)
        and (args.all or entry.get("uploaded"))
    ]
    entries.sort(key=lambda entry: entry["name"].casefold())
    missing = [entry["id"] for entry in entries if not (PREVIEWS / entry["preview"]["file"]).is_file()]
    if missing:
        raise SystemExit(f"preview files missing for {missing[:5]}")
    catalog.render_all(ROOT, [item_from_cache(entry) for entry in entries])
    if not entries:
        print("no uploaded items: index.json is empty (use --all to render built items)")


def pending_uploads(cache: dict, args) -> list[dict]:
    only = set(part.strip() for part in args.only.split(",")) if args.only else None
    entries = []
    for entry in cache.values():
        if only is not None and entry["id"] not in only:
            continue
        if entry.get("uploaded") and not args.force:
            continue
        path = DIST / entry["asset"]
        if not path.is_file():
            print(f"warning: {path} is missing; run build first")
            continue
        entries.append(entry)
    entries.sort(key=lambda entry: entry["name"].casefold())
    if args.limit:
        entries = entries[:args.limit]
    return entries


def command_upload(args) -> None:
    cache = load_cache()
    pending = pending_uploads(cache, args)
    if not pending:
        print("nothing to upload")
        return
    gh.ensure_release()
    total_bytes = sum(entry["bytes"] for entry in pending)
    print(f"uploading {len(pending)} asset(s), {catalog.human_size(total_bytes)}")

    batches = [
        pending[start:start + args.batch_size]
        for start in range(0, len(pending), args.batch_size)
    ]

    def upload_batch(batch: list[dict]) -> list[dict]:
        paths = [str(DIST / entry["asset"]) for entry in batch]
        gh.upload(paths, force=args.force)
        return batch

    done = 0
    uploaded_bytes = 0
    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for batch in pool.map(upload_batch, batches):
                done += len(batch)
                uploaded_bytes += sum(entry["bytes"] for entry in batch)
                print(f"  {done}/{len(pending)} sent ({catalog.human_size(uploaded_bytes)})")
    else:
        for batch in batches:
            upload_batch(batch)
            done += len(batch)
            uploaded_bytes += sum(entry["bytes"] for entry in batch)
            print(f"  {done}/{len(pending)} sent ({catalog.human_size(uploaded_bytes)})")

    print("verifying remote assets")
    remote = gh.assets()
    failed = 0
    for entry in pending:
        info = remote.get(entry["asset"])
        if not info:
            print(f"error: {entry['asset']} missing after upload")
            failed += 1
            continue
        if info["size"] != entry["bytes"]:
            print(f"error: {entry['asset']} size {info['size']} != {entry['bytes']}")
            failed += 1
            continue
        digest = info.get("digest") or ""
        if digest and digest != f"sha256:{entry['sha256']}":
            print(f"error: {entry['asset']} digest mismatch")
            failed += 1
            continue
        entry["uploaded"] = True
        save_cache(cache)
    print(f"verified {len(pending) - failed}/{len(pending)} asset(s)")
    if failed:
        raise SystemExit(1)


def command_status(args) -> None:
    cache = load_cache()
    built = [entry for entry in cache.values()]
    uploaded = [entry for entry in built if entry.get("uploaded")]
    print(f"cache: {len(built)} built, {len(uploaded)} uploaded")
    print(f"archives: {catalog.human_size(sum(entry['bytes'] for entry in built))} "
          f"(uploaded {catalog.human_size(sum(entry['bytes'] for entry in uploaded))})")
    print(f"previews: {catalog.human_size(sum(entry['preview']['bytes'] for entry in built))}")
    remote = gh.assets()
    print(f"release {ASSET_BASE.rsplit('/', 1)[-1]}: {len(remote)} remote asset(s)")


def command_validate(args) -> None:
    errors = validate.validate(ROOT, check_assets=args.check_assets, strict=args.strict,
                               tracked=args.tracked)
    if errors:
        for error in errors:
            print(f"error: {error}")
        raise SystemExit(1)
    print("validation passed")


def referenced_assets(root: Path) -> set[str]:
    """Preview and thumbnail files the current index actually points at."""
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assets: set[str] = set()
    for item in index.get("items", []):
        preview = str((item.get("preview") or {}).get("url", "")).split("?", 1)[0]
        if preview:
            assets.add(preview)
        assets.add(f"thumbs/{item['folder']}.webp")
    return assets


def pending_count() -> tuple[int, int]:
    """(not uploaded, missing dist) counts."""
    cache = load_cache()
    entries = [entry for entry in cache.values() if not entry.get("uploaded")]
    missing = [entry for entry in entries if not (DIST / entry["asset"]).is_file()]
    return len(entries), len(missing)


def run_self(arguments: list[str], retries: int = 0) -> int:
    command = [sys.executable, str(Path(__file__).resolve()), *arguments]
    for attempt in range(retries + 1):
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode == 0:
            return 0
        if attempt < retries:
            delay = 10 * (attempt + 1)
            print(f"retrying in {delay}s: publish.py {' '.join(arguments)}")
            time.sleep(delay)
    return result.returncode


def command_sync(args) -> None:
    """Build, then upload + render + validate + push one batch at a time."""
    if not args.skip_build:
        build_args = ["build"]
        if args.root:
            build_args += ["--root", args.root]
        if run_self(build_args) != 0:
            print("build failed; stopping")
            raise SystemExit(1)

    pending, missing = pending_count()
    if missing:
        print(f"{missing} asset(s) missing from dist; run build first")
        raise SystemExit(1)
    if pending == 0:
        print("nothing to upload")
        return

    total_batches = (pending + args.batch_size - 1) // args.batch_size
    print(f"{pending} pending, {total_batches} batch(es) of {args.batch_size}")

    batch = 0
    while True:
        pending, _ = pending_count()
        if pending == 0:
            break
        if args.max_batches and batch >= args.max_batches:
            print(f"stopped after {batch} batch(es), {pending} still pending")
            break
        batch += 1
        print(f"=== batch {batch}/{total_batches}: {pending} pending ===")
        upload_args = [
            "upload", "--limit", str(args.batch_size),
            "--batch-size", str(args.upload_batch), "--jobs", str(args.jobs),
        ]
        if run_self(upload_args) != 0:
            print("upload failed; rerun sync to resume")
            raise SystemExit(1)
        if run_self(["render"]) != 0:
            raise SystemExit(1)
        if not args.skip_validate and run_self(["validate", "--strict", "--check-assets"]) != 0:
            print("validation failed; stopping")
            raise SystemExit(1)
        if run_self(["push", "--message", f"{args.message} (batch {batch})"], retries=2) != 0:
            print("push failed; rerun sync to resume")
            raise SystemExit(1)

    print(f"done: {batch} batch(es)")


def command_push(args) -> None:
    referenced = referenced_assets(ROOT)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    subprocess.run(["git", "reset", "-q", "--", "previews", "thumbs"], cwd=ROOT, check=True)
    present = sorted(path for path in referenced if (ROOT / path).is_file())
    if present:
        subprocess.run(["git", "add", "-f", "--", *present], cwd=ROOT, check=True)
    tracked = subprocess.run(
        ["git", "ls-files", "--", "previews", "thumbs"],
        cwd=ROOT, text=True, capture_output=True, check=True,
    ).stdout.splitlines()
    stale = sorted(set(tracked) - referenced)
    if stale:
        subprocess.run(["git", "rm", "-q", "--cached", "--", *stale], cwd=ROOT, check=True)
        print(f"untracked {len(stale)} unreferenced preview/thumb file(s)")
    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True)
    if not status.stdout.strip():
        print("nothing to commit")
        return
    subprocess.run(["git", "commit", "-m", args.message], cwd=ROOT, check=True)
    subprocess.run(["git", "push"], cwd=ROOT, check=True)
    print("pushed catalog changes")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list the source folders and their state")
    scan.add_argument("--root")
    scan.add_argument("--only", help="comma separated workshop ids or folder names")
    scan.add_argument("--limit", type=int)

    build = sub.add_parser("build", help="pack archives, previews and thumbnails")
    build.add_argument("--root")
    build.add_argument("--only", help="comma separated workshop ids or folder names")
    build.add_argument("--limit", type=int, help="only the first N folders by name")
    build.add_argument("--all", action="store_true", help="repack even when nothing changed")
    build.add_argument("--force-repack", action="store_true")
    build.add_argument("--bump", choices=["major", "minor", "patch"])
    build.add_argument("--version")

    render = sub.add_parser("render", help="regenerate index.json and README.md")
    render.add_argument("--all", action="store_true", help="include items that are not uploaded yet")
    render.add_argument("--only", help="comma separated workshop ids")

    upload = sub.add_parser("upload", help="upload built archives to the release")
    upload.add_argument("--only", help="comma separated workshop ids")
    upload.add_argument("--limit", type=int)
    upload.add_argument("--batch-size", type=int, default=8)
    upload.add_argument("--jobs", type=int, default=1)
    upload.add_argument("--force", action="store_true", help="re-upload and clobber existing assets")

    validate_cmd = sub.add_parser("validate", help="validate index, previews and assets")
    validate_cmd.add_argument("--strict", action="store_true")
    validate_cmd.add_argument("--check-assets", action="store_true")
    validate_cmd.add_argument("--tracked", action="store_true", help="fail on tracked but unreferenced previews")

    sub.add_parser("status", help="show cache and release summary")

    sync = sub.add_parser("sync", help="build, then upload/render/validate/push in batches")
    sync.add_argument("--root")
    sync.add_argument("--batch-size", type=int, default=20)
    sync.add_argument("--upload-batch", type=int, default=8)
    sync.add_argument("--jobs", type=int, default=1)
    sync.add_argument("--max-batches", type=int)
    sync.add_argument("--skip-build", action="store_true")
    sync.add_argument("--skip-validate", action="store_true")
    sync.add_argument("--message", default="Add wallpapers")

    push = sub.add_parser("push", help="commit and push the catalog")
    push.add_argument("--message", default="Update wallpaper catalog")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    handlers = {
        "scan": command_scan,
        "build": command_build,
        "render": command_render,
        "upload": command_upload,
        "validate": command_validate,
        "status": command_status,
        "push": command_push,
        "sync": command_sync,
    }
    handlers[args.command](args)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
