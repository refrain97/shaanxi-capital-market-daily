# 陕西资本市场日报 V2

这是陕西资本市场日报的当前生产仓库。主分支只保留 V2：五栏目官方来源扫描、结构化编辑、质量门禁、网页构建、日图归档和发布代码。

- 线上日报：<https://refrain97.github.io/shaanxi-capital-market-daily/v2/>
- 当前公开快照：`2026-07-29` / `53fb935994d3`
- 时区：`Asia/Shanghai`

V1 与 V3 已停止维护，其源代码和独立页面不再出现在主分支。Git 历史仍保留正常审计能力；V2 的日常生产不读取 V1/V3 的同日数据或流程。
仓库内的当前结构化快照来自上述线上构建，并已移除旧版本路径和迁移字段；线上发布记录仍以 GitHub Pages 为准。

## 仓库结构

```text
.
├── README.md
├── index.html                 # 指向线上 V2 的轻量入口
└── v2/
    ├── README.md              # V2 功能与运行入口
    ├── config/                # 来源、观察池与质量合同
    ├── data/                  # 当前发布快照和必要基线数据
    ├── docs/                  # 自动化规范、运行手册
    ├── scripts/               # 唯一生产链路及维护工具
    └── tests/                 # 来源、内容和发布门禁
```

运行日志、临时扫描、原始 PDF/TXT、截图、IMA 缓存和本地依赖不进入主分支。客户页面的发布资产由受控脚本按白名单写入 `gh-pages`，源码分支不承载历史静态站副本。

## 本地验证

首次准备运行环境：

```bash
sh v2/scripts/bootstrap_runtime.sh
```

运行仓库测试：

```bash
.venv/bin/python -m unittest discover -s v2/tests -p 'test_*.py'
```

正式生产只有一个入口：

```bash
sh v2/scripts/run_daily_v2.sh --date "$(TZ=Asia/Shanghai date +%F)" --slot morning --publish
```

生产任务不得安装依赖、改代码、绕过栏目门禁或直接调用发布器。完整约束见 [V2 运行手册](v2/docs/V2_RUNBOOK.md)。

## 数据与安全边界

- 关键事实必须回到交易所、监管机构或发行人原文。
- 原始公告仅在临时目录中处理；仓库保留来源 URL、文件哈希、文本质量和结构化结论。
- 任一必需来源、观察池、原文或哈希校验失败时，生产失败关闭。
- IMA 凭证只从环境变量读取，不写入代码、配置、日志或 Git 历史。
- 公开仓库不代表数据结论构成投资建议。
