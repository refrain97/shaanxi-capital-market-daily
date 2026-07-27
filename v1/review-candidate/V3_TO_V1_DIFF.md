# V3 → V1 口径差异（2026-07-23）

> PREVIEW · 审计证据，未发布

## 唯一数据源

- 路由契约：`v1/config/v1-source-contract.json`
- 上市公司正式池：`v3/data/listed/universe.json`。其 `counts` 字段是 110 家构成的唯一可机读事实源；V1 脚本、SOP 和页面不另存一份数量配置。
- 私募正式池：`v3/config/private-fund-universe.json`，只允许 PF1 与经人工准入的 material PF2。

## 上市公司新增 25 家

V1 旧表为 85 家 L1。V3 正式池确认应同步：

- L2（14家）：彩虹新能源、麦科医药-B、德银天下、经发物业、海天天线、西部水泥、天瑞汽车内饰、新丰泰集团、申港控股、巨子生物、世纪金花、大唐西市、延长石油国际、普汇中金国际。
- L3（11家）：华天科技、特变电工、绿能慧充、光电股份、东华科技、北化股份、ST应急、航天电子、华仁药业、珠海中富、科华生物。

V3 的弱关联排除与逐家人工准入规则保持不变；本次未新增任何未在正式池的候选。

## 私募新增观察对象

- 管理人：深圳抱朴容易私募证券基金管理有限公司
- `managerId`：`101000026206`；登记编号：`P1020607`
- 准入级别：`PF2`；`relationStrength=material`；不存在 PF3。
- 注册地/办公地：当前 AMAC 公示均为广东省。
- 陕西关系：`relationType=current_xian_branch_and_shaanxi_group`；陕西泰发祥集团官网确认其是集团旗下资产配置平台，总部在深圳，并在西安、上海设有分部。
- 证据：上述字段及官方 URL 全部来自 `v3/config/private-fund-universe.json` 的唯一 `relatedTargets` 记录。

`automaticExclusions` 中的人员籍贯、校友、一般项目合作、产品名相似或仅搜索摘要等弱关联继续排除，没有重新纳入任何此类对象。
