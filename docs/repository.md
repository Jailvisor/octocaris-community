# Repository layout and publishing

## Layout

```
index.json                generated catalog: the app's only entry point
README.md                 generated catalog table with 96 px thumbnails
NOTICE.md                 attribution and takedown
schema/index.schema.json  schema of index.json
previews/<id>.gif         animated preview shown by the app (only referenced ones tracked)
thumbs/<id>.webp          150 px still used by README.md (only referenced ones tracked)
dist/                     generated archives (gitignored)
tools/publish.py          publisher
tools/publish_lib/        publisher modules
docs/repository.md        this document
```

Archives are **never committed**. They live in the rolling GitHub release
`wallpapers`, one asset per wallpaper, named `octocaris-<id>-v<version>.zip`.

`previews/*` and `thumbs/*` are gitignored so a partial build does not leak into
the repository. `publish.py push` force-adds only the files referenced by
`index.json` and untracks anything else. CI runs `validate --strict --tracked`,
which fails when a tracked preview/thumb is not in the index.

## Limits we rely on

| Where | Limit | Our usage |
| --- | --- | --- |
| Single file in git | 100 MiB blocked, warning over 50 MiB | previews ≤ ~1 MiB, index ~1–2 MiB |
| Repository size | ideally < 1 GB, < 5 GB strongly recommended | ~90 MB (264 previews + 264 thumbs) |
| Files per repository | no documented count limit | ~560 files |
| Release assets | 1000 assets per release | 264 |
| Release asset size | under 2 GiB each | max ~170 MB |
| Release total size | no documented limit | ~10 GB |

Because archives are 20–170 MB each and total ~10 GB, they cannot live in git:
some would exceed the 100 MiB per-file block, and the repository would blow past
the size guidance. Release assets are the supported place for them.

## Identity and naming

- `folder` is the Steam Workshop id (`project.json.workshopid`). It is both the
  catalog key and the install directory, so an update keeps the same folder and
  the user's options/rotation entries survive.
- `name` is the source folder name and must be
  `中文｜English｜日本語｜Blue Archive` using the full-width `｜` (ASCII `|` is illegal
  in Windows names). Use the full-width bar everywhere.
- `version` is `x.y.z`. A content change bumps patch by default; a new asset name
  is generated, so the old asset stays valid for old indexes.
- `preview.url` is relative to `index.json` and carries `?v=<sha8>` for cache
  busting. Preview files stay GIF because the app's preview cache only special-cases
  `gif`/`png` extensions.

## Publisher

```
python tools/publish.py scan                    # what would be built, and its state
python tools/publish.py build                   # pack, previews, thumbnails
python tools/publish.py build --only 3253308696 # one item
python tools/publish.py build --limit 15        # first 15 by name
python tools/publish.py upload                  # resumable, verifies size/sha256
python tools/publish.py upload --limit 15       # upload in batches
python tools/publish.py render                  # index.json/README.md from uploaded items
python tools/publish.py validate --strict
python tools/publish.py validate --check-assets # also checks the release
python tools/publish.py push                    # commit index/README + referenced assets only
python tools/publish.py sync --batch-size 20    # build, then upload/render/validate/push per batch
python tools/publish.py sync --skip-build       # resume a stopped sync without repacking
```

- Default source root is `/mnt/c/fileHub/wallpaper` (`COMMUNITY_SOURCE` overrides).
- `build` writes `dist/`, `previews/`, `thumbs/` and `.publish-cache.json`.
- `render` only includes items marked uploaded, so the index never points at a
  missing asset. `--all` includes built-but-not-uploaded items for local review.
- `upload` checks the release first, skips assets whose size and digest already
  match, and uploads one file per `gh release upload` call. Transient errors
  (408/429/5xx/timeouts) are retried with backoff (`--retries`, default 3).
  `--jobs N` uploads files in parallel (default 2); `--force` uses `--clobber`.
- Re-running after a network failure resumes where it stopped because upload
  state lives in `.publish-cache.json` and the release is re-checked first.
- `sync` is the unattended path: it runs `build`, then loops
  `upload --limit <batch-size>` → `render` → `validate --strict --check-assets` →
  `push`. It stops on the first failure and resumes when rerun, because upload
  state lives in `.publish-cache.json`. `--max-batches` limits a run;
  `--skip-build` resumes after a finished build.
- Archives are deterministic: sorted entries, 1980 timestamps, deflate level 9,
  single `<id>/` root. Rebuilding unchanged content produces the same SHA-256.

### First publish / reset

The repository was reset to one clean commit. To rebuild the release from scratch:

```
gh release delete wallpapers --repo Jailvisor/octocaris-community --yes --cleanup-tag
git checkout --orphan clean-main && git rm -rf --cached . && git add -A
git commit -m "Wallpaper catalog" && git branch -M main
git push --force origin main
python tools/publish.py upload && python tools/publish.py render && python tools/publish.py push
```

### Review flow

1. `build --only <id>` → `upload --only <id>` → `render` → `push`.
2. Inspect the repo page, README row, preview and the app (browse → install).
3. Then `build`, `upload` in batches, `render`, `push`.

## Verification

```
python tools/publish.py validate --strict --check-assets
python tools/publish.py status
```

`status` prints built/uploaded counts, local archive sizes and the number of
remote assets. `validate --check-assets` checks every asset's size and SHA-256
digest through the GitHub API.

In the app, set the index URL in Settings if you use a mirror (for example
`https://cdn.jsdelivr.net/gh/Jailvisor/octocaris-community@main/index.json`).
Previews are relative, so they follow the mirror automatically; archives still
come from `github.com`.
