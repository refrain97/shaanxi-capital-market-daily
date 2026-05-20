# V1 正式访问统计方案

目标不是统计本机打开次数，而是接入 Umami、Plausible、Google Analytics 或类似平台后，长期统计整个 V1 站点的真实访问情况。当前工程侧已按 Umami 做好正式统计注入，等待填入真实网站 ID 后开始记录线上访问。

## 统计口径

- `page_view`：页面被打开。用于看当天多少人访问、打开多少次、每篇日报访问量。
- `open_report`：用户从首页点击打开 HTML 日报。
- `download_asset`：用户点击 Markdown、PNG 或站内锚点等非 HTML 资源。
- `share_copy`：用户点击“复制分享链接”。这代表分享意图，不等于对方平台真实转发数。
- `filter_archive`：用户点击历史归档频道筛选。
- `search_archive`：用户在历史归档搜索框完成一次搜索。

## 关键指标

- 今日独立访客：统计平台里的 unique visitors。
- 今日打开次数：统计平台里的 page views。
- 每篇日报访问：按 URL 路径查看 page views 和 visitors。
- 首页导流：看 `open_report` 事件，并按 `channel`、`asset_type`、`target_url` 分组。
- 分享效果：看 `share_copy` 次数，以及带 `?from=share-copy` 参数进入的访问量。
- 频道兴趣：看 `filter_archive`、`search_archive` 和各频道链接点击。

## 当前实现位置

首页文件：`v1/index.html`

正式统计注入脚本：`v1/scripts/inject_analytics.py`

统计配置：`v1/config/analytics.json`

发布脚本 `v1/scripts/publish_v1_to_vercel.sh` 已在刷新首页后自动执行统计注入，避免每日更新首页后丢失统计代码。

趋势看板样板：`v1/analytics-dashboard-sample.html`

该页面使用演示数据展示“近 7 日趋势、核心指标、频道分布、来源渠道、热门日报、分享效果”。正式接入后，可以直接用 Umami/Plausible/GA 后台查看这些趋势；如果要做自有看板，则需要从统计平台 API 拉数据。

## 接入真实 Umami

在 Umami 后台新建网站后，把 `v1/config/analytics.json` 改成：

```json
{
  "provider": "umami",
  "enabled": true,
  "script_url": "https://cloud.umami.is/script.js",
  "website_id": "你的 Umami Website ID",
  "track_domains": [
    "refrain97.github.io",
    "shaanxi-capital-market-daily.vercel.app"
  ]
}
```

然后执行：

```bash
python3 v1/scripts/inject_analytics.py
```

也可以不改配置文件，发布时临时注入：

```bash
V1_UMAMI_WEBSITE_ID="你的 Umami Website ID" bash v1/scripts/publish_v1_to_vercel.sh --date YYYY-MM-DD
```

真实接入后，页面里的事件脚本会调用：

```js
window.umami.track(eventName, payload)
```

后台就能看到长期访问数据和自定义事件。Umami 默认会记录页面浏览量；自定义脚本负责记录打开日报、下载资源、复制分享链接、筛选和搜索等动作。

## 注意边界

- HTML 页面可以统计页面访问和点击事件。
- Markdown 和 PNG 本身不能执行 JS；如果用户直接打开 `.md` 或 `.png`，前端统计脚本无法记录。
- “转发多少次”通常无法从微信等平台直接获得；可以统计“复制分享链接次数”和“分享链接带来的访问次数”。
- GitHub `Insights -> Traffic` 只能看仓库维度的 14 天数据，不适合作为长期网站运营统计。
