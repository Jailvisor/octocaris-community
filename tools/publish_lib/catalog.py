"""The flat catalog: index.json is the source of truth, README.md is for humans."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ASSET_BASE, BRANCH, REPO_URL, SCHEMA_VERSION


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_index() -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": now_iso(),
        "repository": REPO_URL,
        "releaseTag": ASSET_BASE.rsplit("/", 1)[-1],
        "assetBaseUrl": ASSET_BASE,
        "itemCount": 0,
        "items": [],
    }


def load_index(root: Path) -> dict:
    path = root / "index.json"
    if not path.is_file():
        return empty_index()
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized(index: dict) -> dict:
    items = sorted(index.get("items", []), key=lambda item: (item["name"].casefold(), item["folder"]))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "repository": REPO_URL,
        "releaseTag": ASSET_BASE.rsplit("/", 1)[-1],
        "assetBaseUrl": ASSET_BASE,
        "itemCount": len(items),
        "items": items,
    }


def write_index(root: Path, index: dict) -> None:
    path = root / "index.json"
    current = None
    if path.is_file():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            current.pop("generatedAt", None)
        except (OSError, json.JSONDecodeError):
            current = None
    normalized = _normalized(index)
    if current is not None and current == normalized:
        return
    normalized["generatedAt"] = now_iso()
    ordered = {
        "schemaVersion": normalized["schemaVersion"],
        "generatedAt": normalized["generatedAt"],
        "repository": normalized["repository"],
        "releaseTag": normalized["releaseTag"],
        "assetBaseUrl": normalized["assetBaseUrl"],
        "itemCount": normalized["itemCount"],
        "items": normalized["items"],
    }
    path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def asset_name(item_id: str, version: str) -> str:
    return f"octocaris-{item_id}-v{version}.zip"


def page_url(item_id: str) -> str:
    return f"{REPO_URL}/blob/{BRANCH}/README.md#{item_id}"


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def render_readme(root: Path, index: dict) -> None:
    items = sorted(index.get("items", []), key=lambda item: (item["name"].casefold(), item["folder"]))
    total_bytes = sum(item["download"]["bytes"] for item in items)
    rows = []
    for item in items:
        item_id = item["folder"]
        preview = (item.get("preview") or {}).get("url") or ""
        thumb = f"thumbs/{item_id}.webp"
        if (root / thumb).is_file() and preview:
            image = (
                f'<a href="{preview.split("?")[0]}">'
                f'<img src="{thumb}" width="96" alt=""></a>'
            )
        else:
            image = "—"
        rows.append(
            f'<tr id="{item_id}">'
            f"<td>{image}</td>"
            f'<td><strong>{item["name"]}</strong><br>'
            f'<span>{item.get("author", "")}</span><br><code>{item_id}</code></td>'
            f'<td align="right">{item["version"]}<br>{human_size(item["download"]["bytes"])}</td>'
            "</tr>"
        )

    release_tag = ASSET_BASE.rsplit("/", 1)[-1]
    readme = f"""# Octocaris 社区壁纸

[Octocaris](https://github.com/Jailvisor/octocaris) 的社区壁纸目录。
应用读取 [`index.json`](index.json)，压缩包放在 GitHub Release `{release_tag}`，
只有安装壁纸时才会下载。

## 在应用里使用

应用的默认索引地址已经指向这里。如果使用镜像，在 **设置 → 社区** 里修改索引地址；
预览图是相对路径，会跟随镜像，压缩包仍然从 `github.com` 下载。

## 目录

- **{len(items)} 张壁纸 · {human_size(total_bytes)}** 压缩包。
- `folder` 是 Steam 创意工坊 id：既是目录主键，也是安装目录名。更新时目录不变，
  壁纸选项、轮换和播放列表都会保留。
- 动图预览在 [`previews/`](previews)，静态缩略图在 [`thumbs/`](thumbs)。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `index.json` | 应用读取的目录索引 |
| `previews/<id>.gif` | 每张壁纸一张动图预览 |
| `thumbs/<id>.webp` | README 表格用的 150px 静态图 |
| `schema/index.schema.json` | `index.json` 的 JSON Schema |
| `tools/publish.py` | 发布工具：scan / build / upload / render / validate |
| `docs/repository.md` | 仓库格式、容量限制和发布流程 |

> 内容来源、署名与下架方式见 [NOTICE.md](NOTICE.md)。
> English: `docs/repository.md` documents the format and the publish workflow.

## 壁纸列表

<table>
<tr><th>预览</th><th>壁纸</th><th align="right">版本</th></tr>
{chr(10).join(rows)}
</table>
"""
    (root / "README.md").write_text(readme, encoding="utf-8")


def render_all(root: Path, items: list[dict] | None = None) -> None:
    index = load_index(root)
    if items is not None:
        index["items"] = items
    write_index(root, index)
    rendered = load_index(root)
    render_readme(root, rendered)
    print(f"rendered {rendered['itemCount']} item(s)")
