# 陕西资本市场日报 V2

V2 是本仓库唯一维护的日常检索、数据处理和客户网页生产系统：

<https://refrain97.github.io/shaanxi-capital-market-daily/v2/>

- V2 运行数据只从 `v2/config/source-contract.json` 列明的 V2 路径读取。
- V1/V3 源码不在当前主分支，V2 不读取其同日数据、网页或生产流程。
- 05:30、12:00、17:00 分别运行早间全量、午间增量和收盘增量/归档。
- 证券私募与收并购只保留全年客户网页，不再生成三个月图片或图库。
- 收并购、金融招投标和国企动态均必须生成 V2 自有专用扫描回执；仅写栏目扫描状态不足以进入构建。

完整运行：

```bash
sh v2/scripts/run_daily_v2.sh --date 2026-07-27 --slot morning --publish
sh v2/scripts/run_daily_v2.sh --date 2026-07-27 --slot midday
sh v2/scripts/run_daily_v2.sh --date 2026-07-27 --slot closing --publish
```

唯一生产入口负责上市公司逐主体巨潮扫描、港股逐主体官方复核、公告 PDF 原文提取、
AMAC 私募快照、国企官网取证、收并购/招投标扫描、栏目登记、统一事件库、就绪门禁、
构建、测试、发布和终态归档。自动化不得在入口外手工登记状态或重复扫描。

栏目门禁仅允许 `ready` 对外发布；任一栏必需来源受限、原文缺失、观察池数量漂移或快照
哈希不一致均为 `blocked`。唯一例外是招投标已证明官方等价覆盖完整而补充来源受限：页面必须
明确显示“已完成扫描，来源受限”，绝不把旧数据冒充当天更新。

MA 与 tender 的正式刷新入口分别为：

```bash
python3 v2/scripts/refresh_ma_events.py --date YYYY-MM-DD --slot morning --verify-network
python3 v2/scripts/refresh_tender_events.py --date YYYY-MM-DD --slot morning
```

两者会分别保存原始命中、候选、排除清单和扫描回执。MA 已接入西部产权交易所、
陕西国资委三栏目和有限企业官网注册表；tender 已接入陕西政府采购签名列表 API、
陕西采购与招标公开 API 及中国招标投标公共服务平台官方覆盖组。验证码、正文未取得
或搜索覆盖不全时，脚本以非零状态退出并写 `blocked`/`external_blocked` 证据，
不会把首页健康探针或旧项目标成当天更新。

MA 的“完成、终止、交割、工商变更、交易”等词只表示生命周期，不能单独形成候选；
必须同时存在股权、增资、控制权、重大重组或企业/业务收购出售等实质信号。产权平台
的车辆、单宗土地/房产、报废物资、设备和租赁权等单项实物处置默认进入排除清单。
回执以 `candidateOnScanDate` 表示当日待核候选，仅在已核验事项实际写入正式事件库时
才将 `eventOnScanDate` 标为 `true`。

详见 `v2/docs/V2_RUNBOOK.md`。
