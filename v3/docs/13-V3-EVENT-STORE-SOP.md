# V3 统一事件库 SOP

## 目标

统一事件库用于解决跨日报、跨频道重复描述同一事项的问题。页面、年度统计、收藏跟踪和项目时间线最终都应引用稳定的 `event_id`，不得复制一份新事件。

## 核心对象

- `raw_snapshots`：按数据集和内容哈希保存不可变输入，重复输入不重复写入。
- `entities`：公司、私募管理人、拟上市企业等统一主体。
- `events`：跨频道唯一事件，`event_key` 必须唯一。
- `event_versions`：事件字段发生变化时新增版本，不覆盖历史版本。
- `sources` 与 `event_sources`：事实来源及事件证据关系。
- `event_timeline`：同一事项的公告、审议、问询、结果、交割等节点。

## 入库顺序

1. 保存五类当前输入的原始快照与 SHA-256。
2. 更新主体和来源记录。
3. 依据稳定事件键执行新增或更新。
4. 内容哈希变化时写入事件新版本。
5. 追加未出现过的时间线节点。
6. 执行外键、唯一性、版本完整性和频道覆盖校验。

## 招投标特殊规则

招投标记录先按 `projectFingerprint` 合并为项目事件。招标公告、变更、候选和中标结果进入同一事件时间线，不分别增加年度项目数。只有公告期发现且尚未截止的节点可以进入即时机会区。

## 运行

```bash
python3 v3/scripts/build_event_store.py
python3 v3/scripts/validate_event_store.py
```

数据库保存在 `data/runtime/event-store.sqlite3`，不进入 Git；页面只发布不含敏感字段的 `event-store-summary.json`。每日 V3 统一流程必须先更新上游数据，再构建和校验事件库。
