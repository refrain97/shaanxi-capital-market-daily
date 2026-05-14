# 部署与迁移清单

当前仓库已按静态站方式准备，可先把 `v1/index.html` 作为线上首页。

## 已准备

- `index.html`：根路径入口，使用相对路径自动跳转到 `v1/`，便于整包迁移、本地打开和国内静态托管。
- `vercel.json`：Vercel 静态站配置、`/v1/` 路由和基础响应头。
- `.vercelignore`：只上传公开静态站需要的页面、预览图和归档输出，排除本地会话、环境变量、脚本、模板、配置和原始数据。
- `v1/`：日报、看板、Markdown、PNG、JSON 等 V1 归档内容。

## 还需要你提供或确认

- Vercel 账号。
- 一个 GitHub/GitLab/Bitbucket 仓库，或允许用 Vercel CLI 从本机部署。
- 站点名称：`shaanxi-capital-market-daily`。
- 自定义域名：暂不绑定，先使用 Vercel 默认域名。
- 访问方式：公开访问。

## 推荐部署方式

当前先用 Vercel CLI 从本机部署：

```bash
bash v1/scripts/publish_v1_to_vercel.sh
```

部署完成后访问根域名，会自动进入 `/v1/`：

```text
https://shaanxi-capital-market-daily.vercel.app
```

## 整包迁移

生成一个可迁移压缩包：

```bash
python3 v1/scripts/package_portable_project.py
```

脚本会输出：

- `dist/shaanxi-capital-market-daily/`：可直接作为静态站根目录验证。
- `packages/shaanxi-capital-market-daily-YYYYMMDD-HHMMSS.zip`：给新项目、服务器或对象存储使用的单文件包。

脚本会排除 `.git/`、`.vercel/`、`node_modules/`、`.env*`、本地缓存和历史打包产物，并校验压缩包内所有 HTML 的本地 `href`、`src`、`srcset` 路径是否能找到文件。

## 国内部署建议

如果 Vercel 在国内访问不稳定，可以先走静态托管：

- 云服务器/Nginx：解压 zip 后，把站点根目录指向 `shaanxi-capital-market-daily/`。
- 对象存储静态网站：上传解压后的目录，入口页设为 `index.html`。
- CDN：源站指向上述静态站，缓存 HTML 使用短缓存，PNG/JPG/WebP 使用长缓存。

当前页面不依赖前端构建工具；只要静态服务器能保留中文路径和文件扩展名，`index.html`、`v1/index.html` 以及四个 V1 频道输出都能直接访问。

后续如果接入 GitHub 自动部署，再按下面方式迁移：

1. 把当前目录推送到 GitHub。
2. 在 Vercel 导入该仓库。
3. Framework Preset 选择 `Other`。
4. Build Command 留空。
5. Output Directory 留空或设为 `.`。

## 项目设置建议

- Project Name：`shaanxi-capital-market-daily`
- Framework Preset：`Other`
- Build Command：留空
- Output Directory：留空或 `.`
- Install Command：留空
- Domain：先使用 Vercel 自动生成的 `*.vercel.app`
- Protection：关闭 Password Protection，作为公开站点访问

## 文件归属

- `vercel.json` 和 `.vercelignore` 需要提交，用于保证静态站路由、响应头和部署包内容一致。
- `.vercel/` 是本机 Vercel CLI 绑定信息，包含项目和团队 ID，只保留在本机，不提交到仓库，也不上传到部署包。
- `v1/config/`、`v1/scripts/`、`v1/**/data/`、`v1/**/templates/` 只服务于本地生成流程，不作为公开站点资产发布。

## 后续演进

- 第一阶段：继续用静态文件发布，保证日报可访问、可分享。
- 第二阶段：国内静态托管稳定后，把发布脚本从 Vercel CLI 拆成“生成整包”和“上传国内平台”两步。
- 第三阶段：如新增 `v2/` 或新增 V1 频道，继续保持“版本目录/频道目录/outputs”结构，打包脚本会随整包复制；网页索引脚本再按新频道补扫描规则。
- 第四阶段：需要更强检索时，再抽取 JSON 索引或迁移到 Next.js，把 Markdown/JSON 渲染成结构化详情页。

## V1 流程接入建议

四个 V1 流程生成当日 Markdown、HTML 或 PNG 后，把 `v1/index.html` 的最新日报区和历史归档补齐，然后执行：

```bash
bash v1/scripts/publish_v1_to_vercel.sh
```

发布脚本会先运行 `v1/scripts/update_v1_index.py`，自动扫描四个频道的 `outputs/`，刷新历史归档条目和首页数量，再推送到 Vercel。

若当天低频频道没有新增内容，只记录观察结果，不必重复发布网页。
