"""Thin wrapper around the gh CLI for release assets."""

import json
import subprocess

from .config import RELEASE_TAG, REPO


class GhError(RuntimeError):
    pass


def run(args: list[str], check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(["gh", *args], text=True, capture_output=True, timeout=timeout)
    if check and result.returncode != 0:
        raise GhError(result.stderr.strip() or f"gh {' '.join(args)} failed")
    return result


def release_id() -> int | None:
    result = run(["api", f"repos/{REPO}/releases/tags/{RELEASE_TAG}", "--jq", ".id"], check=False)
    if result.returncode != 0:
        return None
    return int(result.stdout.strip())


def ensure_release() -> None:
    if release_id() is not None:
        return
    run([
        "release", "create", RELEASE_TAG,
        "--repo", REPO,
        "--title", "Wallpaper catalog",
        "--notes",
        "Community wallpaper archives for Octocaris. Asset names are referenced by "
        "index.json; they are immutable, so a new version gets a new file name.",
    ])
    print(f"created release {RELEASE_TAG}")


def delete_release() -> None:
    run(["release", "delete", RELEASE_TAG, "--repo", REPO, "--yes", "--cleanup-tag"], check=False)
    print(f"deleted release {RELEASE_TAG} (if it existed)")


def assets() -> dict[str, dict]:
    """All assets of the rolling release, following pagination."""
    identifier = release_id()
    if identifier is None:
        return {}
    result = run([
        "api", "--paginate",
        f"repos/{REPO}/releases/{identifier}/assets?per_page=100",
        "--jq", '.[] | [.name, .size, (.digest // "")] | @tsv',
    ])
    remote: dict[str, dict] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        name, size, digest = parts
        remote[name] = {"name": name, "size": int(size), "digest": digest}
    return remote


def upload(paths: list[str], force: bool = False) -> None:
    if not paths:
        return
    args = ["release", "upload", RELEASE_TAG, *paths, "--repo", REPO]
    if force:
        args.append("--clobber")
    run(args)
    print(f"uploaded {len(paths)} asset(s)")
