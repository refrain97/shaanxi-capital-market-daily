# Codex 自动化执行规范｜陕西资本市场日报 V2

## 全部时点的共同约束

1. 只读写 `v2/` 生产路径，不调用或读取旧版本的当日流程、业务数据、日图、交接清单
   或网页。V1/V3 源码不在当前主分支。
2. 以上市公司 110 家正式池、私募 92 家正式池和 V2 统一事件库为检索范围。
3. 交易所、监管及发行人原文优先；媒体只用于发现线索。关键金额、比例、日期、阶段必须回到原文。
4. 同一项目用稳定 `eventId` 追加时间线，不新建重复项目。
5. `record_channel_scan.py` 只由 V2 唯一入口在正式采集和核验完成后调用。不得在入口外
   人工声明任一栏目 `completed/no_new`。
6. 历史待补原文只进入核验区，不进入首页重点；当天任一栏目未完成必需来源合同即全站
   `blocked`。唯一例外是 tender 回执同时证明官方等价覆盖完整、受限者仅为合同声明的补充来源
   并写出受限来源 ID；该情况下页面必须显示“已完成扫描，来源受限”，不得写成“今日无新增”。
7. MA 与 tender 不能只登记 `record_channel_scan.py`。统一生产入口会分别运行
   `refresh_ma_events.py --verify-network` 和 `refresh_tender_events.py`；
   回执只有在全部必需来源完成检索、正文核验和事件库哈希匹配后才可 `completed`。
   仅健康探针、部分查询必须 `blocked`；配置内官方等价覆盖组只有在完整查询矩阵、
   陕西区域证明和当日命中正文核验均通过时才可替代单站外部失败。陕西政府采购当前
   验证码阻断不得用首页样本或手工 `no_new` 覆盖。
8. SOE 不能只登记 `record_channel_scan.py`。必须生成同日同时点的
   `v2/data/source/soe/evidence/verified-YYYY-MM-DD-SLOT.json`，再运行
   `refresh_soe_events.py --verify-network`，由其写出专用扫描回执。
9. 输入获取、来源核验、栏目状态、统一事件库、网页、日图归档和 IMA 补传必须围绕
   `run_daily_v2.sh` 的唯一生产链路完成。禁止在入口外手工登记状态、运行
   MA/tender/SOE、发布网页或上传 IMA；生产期间禁止安装依赖或修改代码。
10. 正式入口默认按 05:30 / 12:00 / 17:00 检查启动滞后。超过 60 分钟必须写为
    `blocked`，不能把迟到运行包装成对应时点的成功；后续时点只能按“完整补偿”重新运行。

## 05:30 早间全量

- 对上市公司正式观察池逐公司检索巨潮资讯/交易所公告并生成同日 raw 与 curated。
- 运行 AMAC 日增量扫描，按 `fundNo` 与 V2 年库合并；周末全量复核、每月1日完整
  回溯，禁止因接口漂移删除历史产品。
- 生成SOE同日核验批次；收并购、金融招投标和SOE专用刷新由唯一生产入口执行，
  不得提前重复运行。
- MA/tender 使用默认完整查询范围；正式运行禁止传 `--max-queries`。
- 五栏目记录完成后执行：

```bash
sh v2/scripts/run_daily_v2.sh --date "$(TZ=Asia/Shanghai date +%F)" --slot morning --publish
```

05:30 的完整早报通过后，统一入口从 V2 冻结快照生成一次四张日图（上市公司、
证券私募、收并购、金融招投标），并在各自 V2 栏目建立在线归档。私募与收并购三个月
分享图永久不生成。网页与日图在线确认后才上传 IMA；IMA 失败只进入待补传队列，不阻断
已确认网页。
统一入口会自动写最终运行清单，失败时保留任务并报告具体栏目。

## 12:00 午间增量

- listed/private 可在真实 morning 基线上扫描早间之后的新公告和状态变化。
- MA/tender 当前没有可靠的“上次游标后”增量窗口，必须按同日完整配置范围扫描，
  不得声称只覆盖早间以后；正式运行禁止传 `--max-queries`。
- SOE 必须使用同日 midday 证据批次和专用回执。
- 无更新的栏目明确记录 `no_new`。
- 执行：

```bash
sh v2/scripts/run_daily_v2.sh --date "$(TZ=Asia/Shanghai date +%F)" --slot midday --publish
```

## 17:00 收盘增量与归档

- listed/private 可在真实 midday 基线上扫描午间之后的新公告；基线缺失时执行同日完整补偿。
- MA/tender 当前按同日完整配置范围扫描，不得虚构游标增量；正式运行禁止传
  `--max-queries`。
- SOE 必须使用同日 closing 证据批次和专用回执。
- 完成五栏目当日归档和就绪记录；只更新网页，不创建第二套当日日图，并自动重试 IMA
  待补传队列。
- 执行：

```bash
sh v2/scripts/run_daily_v2.sh --date "$(TZ=Asia/Shanghai date +%F)" --slot closing --publish
```

closing 发布成功后自动写入 V2 当日终态清单。旧版本不参与任何日常生成、上传或发布。
