"""Item identity rules (Workshop ids) and version helpers."""

import re

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
WORKSHOP_ID_RE = re.compile(r"^\d{6,12}$")

RESERVED_FOLDERS = {"default", "gradient", "conformance", "community"}
DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}
INVALID_CHARS = set('<>:"/\\|?*')


def validate_id(value: str) -> bool:
    """A Workshop id is the catalog key and the install directory name."""
    return bool(WORKSHOP_ID_RE.fullmatch(value or ""))


def validate_folder(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    if name.startswith("."):
        return False
    if name != name.rstrip(" ."):
        return False
    if any(ord(ch) < 32 for ch in name):
        return False
    if any(ch in INVALID_CHARS for ch in name):
        return False
    if name.split(".")[0].upper() in DEVICE_NAMES:
        return False
    if name.lower() in RESERVED_FOLDERS:
        return False
    return True


def bump_version(version: str, part: str) -> str:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise ValueError(f"invalid version {version!r}")
    major, minor, patch = (int(group) for group in match.groups())
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
