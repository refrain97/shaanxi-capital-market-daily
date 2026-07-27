# Codex V1 自动化提示审计与监督同步结果

> PREVIEW · 2026-07-23

- 自动化 ID：`v1`
- 名称：`V1版陕西资本市场动态全自动日报`
- 本机证据：`/Users/refrain97/.codex/automations/v1/automation.toml`
- 过时原文：第 4 条含“若 CNINFO errorCount>0，尤其是 85 家全失败或 DNS 失败”。
- 问题：把旧 L1 85 家当成固定失败阈值，没有指定 V3 正式池与私募 PF2 配置，也没有事项级 `matter_id` 纪律。
- 客户页面与分图正式启用后可整体替换的完整提示：`v1/docs/AUTOMATION_PROMPT_V1.md`。该文件逐项保留现行 1–14 条纪律，包括交易日窗口、网络检查、项目虚拟环境、CNINFO/AMAC、低频频道、预览与统计、发布前校验、IMA、仅 GitHub Pages、运行栏、双看板入口、简报和线程归档；只在第 4–7 条替换或补充动态池契约、PF2 allow-list、事项级 `matter_id`、客户正文与分图规则。

提示文本静态校验：编号必须严格为 1–14，并包含 `上一交易日`、`network_access=false`、`.venv/bin/python`、`CNINFO`、`AMAC`、`IMA`、`GitHub Pages`、`每日运行记录`、两个看板入口和 `自动化看板`。2026-07-23 候选验收已通过该检查。

执行线程仅使用查看模式核对 ID。主任务完成测试与视觉复核后，已更新现有 `v1` 自动化中的观察池和事项规则：上市公司读取 `listedUniverse.path`，私募读取 `privateFundUniverse.path`，全失败阈值按动态池数量计算，并明确禁止读取或发布 `v1/review-candidate/`。自动化名称、状态、运行时间、模型及原 14 项运行纪律均保持不变。

候选客户页面和新版私募/收并购分图尚未进入正式自动发布；待客户验收后，再使用上述完整提示和正式生成器同步启用。
