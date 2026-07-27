# 陕西资本市场日报 V1 客户网页候选版 V2

> PREVIEW · NOT PUBLISHED · 数据截至 2026-07-23

本目录与正式 V1 页面、正式频道输出及日常自动化平行隔离。构建脚本只读取项目内既有数据源，只写入本候选目录。

## 构建与预览

```bash
python3 v1/review-candidate-v2/scripts/build_candidate_v2.py
python3 -m http.server 8766 --directory .
```

访问 `http://127.0.0.1:8766/v1/review-candidate-v2/`。

## 页面入口

- `index.html`：四项今日重点与五个频道
- `listed.html`：上市公司日报
- `private.html`：证券私募年度库
- `ma.html`：收并购年度库
- `tender.html`：金融招投标日报
- `soe.html`：国企动态早报
- `watchlist.html`：完整观察池上下文页，不进入首页导航
- `images/index.html`：分享图图库

所有页面读取同一份 `data/candidate-data.json`。静态资源和数据请求使用快照中的确定性 `build.version` 作为版本参数；数据请求使用 `cache: "no-store"`。

当前关键口径：

- 上市公告来源 29/29；每条只链接与公司和事项相匹配的官方公告。
- 私募 33 只年度产品、93 家管理人。
- 收并购 25 项，其中 8 项已核验、17 项待补来源；分享页只含 8 项已核验记录。
- 金融招投标 5 个正式项目、1 条待核实线索。
- 国企动态真实最新期为 2026-07-10，共 6 条。

详细验收结果见 `ACCEPTANCE.md`，事实数据边界见 `DATA_GAPS.md`。
