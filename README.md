# Octocaris 社区壁纸

[Octocaris](https://github.com/Jailvisor/octocaris) 的社区壁纸目录。
应用读取 [`index.json`](index.json)，压缩包放在 GitHub Release `wallpapers`，
只有安装壁纸时才会下载。

## 在应用里使用

应用的默认索引地址已经指向这里。如果使用镜像，在 **设置 → 社区** 里修改索引地址；
预览图是相对路径，会跟随镜像，压缩包仍然从 `github.com` 下载。

## 目录

- **3 张壁纸 · 120.2 MB** 压缩包。
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
<tr id="3533267510"><td><a href="previews/3533267510.gif"><img src="thumbs/3533267510.webp" width="96" alt=""></a></td><td><strong>一花(泳装)｜ichika(swim)｜イチカ(水着)｜Blue Archive</strong><br><span>Z_DK</span><br><code>3533267510</code></td><td align="right">1.0.0<br>49.4 MB</td></tr>
<tr id="3253308696"><td><a href="previews/3253308696.gif"><img src="thumbs/3253308696.webp" width="96" alt=""></a></td><td><strong>小桃(女仆)｜momoi(maid)｜モモイ(メイド)｜Blue Archive</strong><br><span>Z_DK</span><br><code>3253308696</code></td><td align="right">1.0.0<br>30.9 MB</td></tr>
<tr id="3481411508"><td><a href="previews/3481411508.gif"><img src="thumbs/3481411508.webp" width="96" alt=""></a></td><td><strong>菲娜(导游)｜pina(guide)｜ピナ(ガイド)｜Blue Archive</strong><br><span>Z_DK</span><br><code>3481411508</code></td><td align="right">1.0.1<br>40.0 MB</td></tr>
</table>
