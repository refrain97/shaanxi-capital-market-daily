# V1 客户验收记录

> PREVIEW · 2026-07-23 · 未发布

## 页面

- `index.html`：客户首页
- `listed.html`：上市公司候选页
- `private.html`：私募候选页，29 条备案可搜索/筛选/分页
- `ma.html`：收并购候选页，24 个案例可搜索/筛选/分页
- `tender.html`：招投标候选页，390px 下无水平溢出

## 分享图拆分

- 私募：拆分前 1 张 `1242×2234`；拆分后 4 张（摘要封面 1 张 `1242×1080`，备案明细 3 张 `1242×1750`，分别为 10+10+9 条）。
- 收并购：拆分前 1 张 `1800×7742`；拆分后 5 张（摘要封面 1 张 `1242×1080`，案例详情 4 张 `1242×1750`，每张 6 个案例）。
- 候选图索引：`images/index.html`。每张图的独立网页源在 `share/`，不与客户网页共用超长画布。
- 2026-07-23 实际样例：`private-cover.png`、`private-detail-1.png`–`private-detail-3.png`、`ma-cover.png`、`ma-detail-1.png`–`ma-detail-4.png`，共 9 张；不存在遗留的 `ma-detail-5/6`。
- Playwright 逐图量测：所有图 `scrollWidth=1242`；两张封面 `scrollHeight=1080`；七张详情 `scrollHeight=1750`；每个收并购详情页 6 张卡片，卡片内部溢出均为 0。

## Playwright

- 桌面：5 个页面均以 1440px 视口生成全页截图。
- 手机：5 个页面均以 390px 视口生成全页截图；实测 `scrollWidth=390`、`overflow=false`。
- 证据目录：`output/playwright/`。
- 2026-07-23 返修后重拍全部 10 张截图；5 个页面在 1440px 与 390px 下均为 `scrollWidth=clientWidth`。

## 隔离

本轮没有写入或覆盖正式 `v1/index.html`、四频道正式 `outputs/`、发布分支或部署目录；没有运行 `--finalize`、上传、发布、部署、提交。

现有 Codex 自动化 `v1` 已只同步动态观察池、PF2 allow-list 和事项级校验规则，并明确禁止读取或发布本候选目录；候选客户页面和新版分图仍待验收后启用。

## 未决风险

- L2 港股完整性仍需在日常生产中用 HKEX 披露易复核。
- 历史精读数据尚未全部回填显式 `matter_id`，校验器会使用来源指纹或稳定标题指纹回退；新数据应强制写入公告 ID。
- 私募年内注销详情仍存在上游公示分页限制；候选客户正文未暴露此生产细节，但运行日志仍应保留。
- 旧 `v1/scripts/check_v1_responsive.py` 直接启动的本机 Chrome 在当前更新期被系统 `SIGKILL`；候选版已改用 Playwright Firefox 完成 1440/390 实测并通过，但正式发布前仍需在 Chrome 完成更新或旧进程重启后重跑该旧检查器。
