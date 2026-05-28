# 自动化额度观察记录

用于观察 V1 全自动日报夜间运行前后的额度变化。截图口径为 Codex/ChatGPT 客户端显示的剩余额度。

## 2026-05-26 00:20 运行前快照

- 5 小时额度：剩余 96%，重置时间 05:13
- 1 周额度：剩余 72%，重置日期 6月1日
- 自动化计划：03:30 运行 V1 版陕西资本市场动态全自动日报
- 观察目标：2026-05-26 早上查看自动化运行后剩余额度，估算一次完整日报消耗

## 2026-05-26 03:30 首次自动化结果

- 结论：自动化已启动，但未发布。
- 主因：自动化线程运行在受限网络沙盒，CNINFO 85 家逐公司请求全部 DNS 失败，AMAC 也因 DNS 失败。
- 发布闸门：`validate_v1_outputs.py --date 2026-05-26` 因缺上市公司 Markdown 拦截，IMA/Vercel/GitHub Pages 均未执行。
- 修复：Codex 默认配置已切到 full-access/never；V1 脚本已改为优先使用 `.venv/bin/python`，并在 CNINFO/AMAC 失败时硬停。

## 2026-05-26 手动补跑与二次修复

- 结论：2026-05-26 全流程已手动跑通，四个频道 PNG 均上传 IMA，Vercel 生产部署完成，GitHub Pages 已验证出现 `2026-05-26 更新`。
- 二次问题1：AMAC 年内注销明细共501条，长时间请求时出现一次 SSL EOF 断连。修复：详情页请求加入8次退避重试，并将总流程 AMAC 明细请求间隔调为0.3秒。
- 二次问题2：`--finalize` 在发布脚本更新首页前先校验首页日期，导致“首页未更新”的假失败。修复：去掉 finalize 入口的提前校验，由发布脚本在生成预览和更新首页后统一校验。
- 今日补跑窗口：上市公司公告按 2026-05-25 至 2026-05-26；后续日报口径仍按上一交易日至当日，周一覆盖上周五、六、日。

## 2026-05-28 自动化稳定性复盘

- 主因1：本机网络处在代理 fake-ip 模式，多个关键域名解析到 `198.18.0.0/15`，AMAC 直连表现为 `RemoteDisconnected` / `Empty reply from server`。这不是 AMAC 登录或账号问题。
- 修复1：新增 `v1/scripts/preflight_v1_network.py`，开跑前记录 DNS、代理、CNINFO、AMAC、Vercel、GitHub Pages/Git 和 Chrome 体检结果。AMAC 体检复用正式脚本 fallback，直连失败但 fallback 成功时允许继续运行。
- 主因2：GitHub Pages 发布已经 push 到 `gh-pages`，但 Pages build 超过原脚本等待窗口；脚本过早把 CDN 未刷新判定为失败。
- 修复2：`publish_v1_to_github_pages.sh` 改为查询 latest Pages build，等待 `built` 后再验证线上首页日期，默认最多等待 60 次、每次 10 秒。
- 修复3：CNINFO 逐公司请求和 PDF 下载加入请求级重试，降低单次网络抖动导致整日报失败的概率。
- 2026-05-28 体检结果：存在 fake-ip DNS，AMAC 使用 `module_fallback` 跑通；Vercel 与 GitHub Pages 最终均验证 `2026-05-28 更新`。
