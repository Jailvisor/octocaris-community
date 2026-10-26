"""Repository constants. Override the repository with COMMUNITY_REPO for forks/tests."""

import os

REPO = os.environ.get("COMMUNITY_REPO", "Jailvisor/octocaris-community")
BRANCH = os.environ.get("COMMUNITY_BRANCH", "main")
RELEASE_TAG = os.environ.get("COMMUNITY_RELEASE_TAG", "wallpapers")
SCHEMA_VERSION = 1

# Every current item comes from the same Steam Workshop creator.
AUTHOR = os.environ.get("COMMUNITY_AUTHOR", "Z_DK")
SOURCE_KIND = "wallpaper-engine"
WORKSHOP_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={id}"

REPO_URL = f"https://github.com/{REPO}"
ASSET_BASE = f"{REPO_URL}/releases/download/{RELEASE_TAG}"
