from PIL import Image, ImageDraw, ImageFont
import argparse
import datetime as dt
from pathlib import Path
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Render the V1 Shaanxi M&A detailed case board.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Report date, YYYY-MM-DD.")
    return parser.parse_args()


args = parse_args()
REPORT_DATE = dt.date.fromisoformat(args.date)
W, H = 1800, 4800
BG = "#f7f5f0"
INK = "#242424"
MUTED = "#6b6258"
RED = "#8f1d21"
GOLD = "#b8924b"
TEAL = "#116a73"
LINE = "#dfd8cc"
CARD_BORDER = "#e4ded4"
WHITE = "#ffffff"
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
V1_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
WORK_OUTPUT_PATH = OUTPUT_DIR / "shaanxi_ma_cases_2026_detailed.png"
PUBLISH_OUTPUT_PATH = OUTPUT_DIR / f"{REPORT_DATE.year}年{REPORT_DATE.month}月{REPORT_DATE.day}日陕西辖区收并购事件详细案例看板.png"
LEGACY_OUTPUT_PATH = OUTPUT_DIR / "陕西辖区收并购事件详细案例看板.png"

sys.path.insert(0, str(V1_SCRIPTS_DIR))
from brand_v1_png import apply_branding  # noqa: E402


def font(size):
    return ImageFont.truetype(FONT_PATH, size=size, index=0)


F_TITLE = font(58)
F_SUB = font(24)
F_H2 = font(34)
F_H3 = font(28)
F_BODY = font(23)
F_SMALL = font(18)
F_TINY = font(16)
F_NUM = font(48)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)


def rounded(xy, r, fill, outline=None, width=1):
    d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def twidth(text, ft):
    return d.textbbox((0, 0), text, font=ft)[2]


def wrap_cn(text, ft, maxw):
    lines = []
    cur = ""
    for ch in text:
        trial = cur + ch
        if twidth(trial, ft) <= maxw:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def text(x, y, s, ft=F_BODY, fill=INK):
    d.text((x, y), s, font=ft, fill=fill)


def pill(x, y, label, fill, stroke, textcolor, w=None):
    w = w or (twidth(label, F_TINY) + 34)
    rounded((x, y, x + w, y + 34), 17, fill, stroke, 1)
    text(x + (w - twidth(label, F_TINY)) / 2, y + 7, label, F_TINY, textcolor)
    return w


def paragraph(x, y, s, ft=F_BODY, fill=INK, maxw=720, lh=34, max_lines=None):
    lines = wrap_cn(s, ft, maxw)
    if max_lines:
        lines = lines[:max_lines]
    for line in lines:
        text(x, y, line, ft, fill)
        y += lh
    return y


for x in range(W):
    if x < W * 0.55:
        t = x / (W * 0.55)
        c1 = (143, 29, 33)
        c2 = (184, 146, 75)
    else:
        t = (x - W * 0.55) / (W * 0.45)
        c1 = (184, 146, 75)
        c2 = (17, 106, 115)
    c = tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))
    d.line([(x, 0), (x, 16)], fill=c)

text(80, 50, "陕西辖区收并购事件详细案例看板", F_TITLE, INK)
text(
    80,
    122,
    f"2026-01-01 至 {REPORT_DATE:%Y-%m-%d}｜公开披露口径｜陕西主体、陕西标的、陕西上市公司及陕西项目公司相关事件",
    F_SUB,
    MUTED,
)

kpis = [
    ("15起", "主表事件", RED),
    ("67.96亿元", "可量化披露金额", GOLD),
    ("4类", "企业观察维度", TEAL),
    ("计入口径", "已完成、已签协议、挂牌底价或明确作价", INK),
]
x = 80
for i, (a, b, c) in enumerate(kpis):
    w = [400, 430, 350, 370][i]
    rounded((x, 190, x + w, 320), 16, WHITE, CARD_BORDER, 1)
    if i < 3:
        text(x + 30, 210, a, F_NUM, c)
        text(x + 30, 275, b, F_SUB, MUTED)
    else:
        text(x + 30, 220, a, F_H3, INK)
        paragraph(x + 30, 260, b, F_SMALL, MUTED, w - 60, 28)
    x += w + 30

text(80, 370, "一、四类企业维度", F_H2, INK)
d.line([(80, 415), (1720, 415)], fill=LINE, width=2)
dims = [
    ("已上市公司", "信息披露最完整，是交易金额、进度和估值口径最可靠的主线。", "金钼股份、北方长龙、天地源等", RED),
    ("拟上市与辅导企业", "关注IPO转并购、资产证券化、基金退出及上市公司收购。", "华羿微电为典型样本", GOLD),
    ("上市后备企业", "陕西520家后备库是潜在标的池，需逐项勾稽A/B/C档。", "目前主表暂未完全核验档位", INK),
    ("活跃非上市公司", "交易热区集中在军工电子、航空航天、AI零售和地产项目。", "思丹德、群健航空、中科西光等", TEAL),
]
x = 80
for title, desc, note, color in dims:
    rounded((x, 445, x + 390, 600), 15, WHITE, CARD_BORDER, 1)
    text(x + 24, 468, title, F_H3, color)
    paragraph(x + 24, 510, desc, F_SMALL, MUTED, 340, 27)
    text(x + 24, 565, note, F_TINY, TEAL)
    x += 416

text(80, 675, "二、逐笔并购案例", F_H2, INK)
d.line([(80, 720), (1720, 720)], fill=LINE, width=2)

cases = [
    ("01 金钼股份收购金沙钼业24%股权", "已上市公司", "已完成", "red", "teal", "2026-01-15公告；2026-03-05完成工商变更", "陕西上市公司对外收购｜现金收购参股公司股权", "安徽金沙钼业；向紫金矿业收购", "17.3087亿元；100%隐含估值约72.12亿元", "钼矿资源/有色金属", "加强上游资源控制，持股由10%升至34%", "冶炼项目设立、金沙钼业业绩并表、资源储量披露"),
    ("02 北方长龙收购顺义科技51%股权", "已上市公司", "草案披露/推进", "red", "gold", "2026-01-08意向；2026-04-23草案", "陕西上市公司对外收购｜现金重大资产购买", "沈阳顺义科技；北方长龙", "4.26亿元；100%隐含估值约8.35亿元", "军工智能装备", "补齐智能检测、仿真、维修保障能力", "股东会、深交所问询、业绩承诺、现金支付安排"),
    ("03 天地源挂牌转让深宝水电51%股权", "已上市公司", "挂牌中", "red", "gold", "2026-01-09", "陕西上市公司出售资产｜国资平台挂牌转让", "陕西深宝水电；受让方待挂牌确定", "挂牌底价4853.40万元；另涉应收债权4605.55万元", "水电/资产处置", "房地产上市公司剥离非核心资产、回收资金", "是否成交、受让方背景、债权回收安排"),
    ("04 华天科技收购华羿微电100%股份", "拟上市与辅导企业", "推进中", "gold", "teal", "2026-02-10/11披露重组报告书", "外地上市公司收购陕西硬科技标的", "华羿微电100%股份；华天科技", "29.96亿元；媒体披露溢价率约166.17%", "半导体功率器件/封测", "典型IPO折戟资产转并购退出，含陕西股东方退出", "深交所审核、配套募资、业绩承诺、退出收益"),
    ("05 陕西华达终止收购华经微电子", "已上市公司", "已终止", "red", "gray", "2026-02-13终止", "陕西上市公司终止收购｜原拟发行股份购买资产", "陕西华经微电子；陕西华达", "未最终确定；发行股份价格34.75元/股", "电子元器件/集团资产整合", "交易结构与作价谈判仍是省内整合难点", "是否重启、后续IPO/并购路径、集团内部整合"),
    ("06 西安旅游转让红土创新等参股股权", "已上市公司", "董事会通过", "red", "gold", "2026-03-06", "陕西上市公司出售参股股权｜关联股权转让", "西安红土创新50%、西旅创投30%；西旅集团实业", "合计1581.25万元；红土公司评估值2796.31万元", "文旅/创投平台", "退市风险压力下小额资产处置，改善流动性有限", "交易交割、继续处置资产、定增输血进展"),
    ("07 招商局置地体系内收购西安项目公司", "活跃非上市公司", "已签协议", "teal", "gold", "2026-03-06", "港股上市公司体系内收购西安项目公司", "西安招玺锦樾；西安茂安", "7958.96万元；参考目标公司2025-11-30资产净值", "房地产项目公司", "集团体系内整合，显示西安地产资产仍有交易活动", "交割、项目去化、关联资金往来"),
    ("08 恒天海龙拟收购群健航空不少于40%股权", "活跃非上市公司", "意向协议", "teal", "gray", "2026-03-12", "外地上市公司拟收购西安高端制造标的", "西安市群健航空精密制造；海龙飞控", "未披露；价格和比例待正式协议", "航空发动机/燃机零部件", "西安航空精密制造资产被传统行业上市公司跨界关注", "尽调结果、正式协议、交易价格、是否形成控股"),
    ("09 顶固集创收购西安思丹德51.5488%股权", "活跃非上市公司", "已签协议", "teal", "gold", "2026-03-13", "外地上市公司收购西安军工电子标的｜现金控股收购", "西安思丹德；顶固集创", "2.680538亿元；100%评估值5.21亿元", "军工电子/精确制导/通信", "跨界买入西安硬科技资产，体现军工电子标的稀缺性", "股东会、业绩承诺、商誉、军工资质和订单稳定性"),
    ("10 西安招商花园城引入深圳海越锦", "活跃非上市公司", "合作开发", "teal", "gold", "2026-04-29", "西安项目公司引入外部股东｜增资入股", "西安招商花园城；深圳海越锦", "1.74454286亿元；以注册资本注入取得30%股权", "房地产项目公司", "通过引资降低上市公司资金占用", "股权变更、项目开发进度、少数股东权益安排"),
    ("11 汉朔科技控股西安超嗨网络", "活跃非上市公司", "工商变更完成", "teal", "teal", "2026-04-29工商变更披露", "外地上市公司战略控股西安AI零售标的", "西安超嗨；汉朔科技全资子公司", "5622.752195万元；100%隐含估值约1.19亿元", "AI零售/智能购物车", "产业方控股，而非纯财务退出", "并表影响、海外订单协同、原股东退出情况"),
    ("12 金利华电筹划收购中科西光", "活跃非上市公司", "筹划停牌", "teal", "gray", "2026-05-05", "外地上市公司筹划收购西安商业航天标的", "西安中科西光；金利华电", "待方案；全部或部分股权", "商业航天/高光谱卫星/遥感数据", "若落地，将是陕西硬科技资产证券化重点案例", "10个交易日内方案、估值、交易对方、是否重大重组"),
    ("13 飞亚达拟收购陕西长空齿轮100%股权", "活跃非上市公司", "董事会通过", "teal", "gold", "2026-04-30公告；2026-05-08股东会补充通知；2026-05-12复核", "外地上市公司收购陕西军工精密制造标的｜现金收购", "陕西长空齿轮；汉中汉航机电、航空工业转让", "3.247904亿元；评估后净资产约3.396904亿元", "航空精密齿轮/精密减速器", "航空工业体系内资产证券化，补强飞亚达精密科技业务", "5月20日股东会审议、航空工业批复、交割及并表安排"),
    ("14 京投发展筹划收购西安奇芯光电股权", "活跃非上市公司", "筹划/问询中", "teal", "gray", "2026-05-11提示；2026-05-12问询", "外地上市公司收购陕西光电子标的｜现金关联交易", "西安奇芯光电；北京新基建产业一期股权投资中心", "比例和价格未定；新基建持有20.9052%股权", "光电子器件/光电子集成", "北京国资房企跨界收购西安硬科技未盈利标的", "5个交易日内回复问询、董事会/股东会、国资审批和评估备案"),
    ("15 紫光国芯完成15%股份协议转让", "拟上市与辅导企业", "过户完成", "gold", "teal", "2026-03-10协议；2026-05-11过户完成", "西安新三板半导体企业股份协议转让｜产业投资者入股", "西安紫光国芯；中关村科学城、倍特启新、宿迁裕朗受让", "合计约6.7499亿元；三方各受让681.6036万股、各持5%", "半导体/存储芯片", "引入多地产业资本，控股股东紫光存储持股降至45.67%但控制权未变", "后续融资、IPO路径、产业资本协同和股东结构稳定性"),
]

color_map = {
    "red": ("#f7e9e9", "#d9b2b4", RED),
    "gold": ("#f5eedf", "#d9c28d", GOLD),
    "teal": ("#e4f1f1", "#a9cdcf", TEAL),
    "gray": ("#eeeae3", "#d4cabd", MUTED),
}


def draw_case(x, y, c):
    rounded((x, y, x + 800, y + 445), 0, WHITE, CARD_BORDER, 1)
    text(x + 28, y + 26, c[0], F_H3, INK)
    p1 = color_map[c[3]]
    p2 = color_map[c[4]]
    w1 = pill(x + 28, y + 78, c[1], *p1)
    pill(x + 42 + w1, y + 78, c[2], *p2)
    labels = [
        ("日期", c[5]),
        ("方向", c[6]),
        ("标的/收购方", c[7]),
        ("金额/估值", c[8]),
        ("产业", c[9]),
        ("意义", c[10]),
        ("跟踪", c[11]),
    ]
    yy = y + 130
    label_x = x + 28
    value_x = x + 205
    value_w = 555
    for lab, val in labels:
        label_color = MUTED if lab == "跟踪" else INK
        value_color = MUTED if lab == "跟踪" else INK
        text(label_x, yy, lab + "：", F_BODY, label_color)
        line_count = len(wrap_cn(val, F_BODY, value_w))
        paragraph(value_x, yy, val, F_BODY, value_color, value_w, 32, 2)
        yy += 40 if line_count <= 1 else 66


start_y = 750
card_h = 445
gap_y = 42
for idx, c in enumerate(cases):
    col = idx % 2
    row = idx // 2
    draw_case(80 + 840 * col, start_y + (card_h + gap_y) * row, c)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
for output_path in (WORK_OUTPUT_PATH, PUBLISH_OUTPUT_PATH, LEGACY_OUTPUT_PATH):
    img.save(output_path, quality=95)
    apply_branding(output_path)
    print(f"Wrote {output_path}")
