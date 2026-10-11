"""YASB custom widget: 农历 + 黄历（宜/忌）+ 八卦（九宫飞星、方位吉神）。
输出一行 JSON {brief, detail, tip}。依赖：pip install lunar_python（纯 Python，离线计算，不联网）。
"""
import datetime
import json
import sys

from lunar_python import Solar

sys.stdout.reconfigure(encoding="utf-8")
n = datetime.date.today()
l = Solar.fromYmd(n.year, n.month, n.day).getLunar()


GUA = {"乾": "☰", "兑": "☱", "离": "☲", "震": "☳", "巽": "☴", "坎": "☵", "艮": "☶", "坤": "☷"}


def gua(name):
    """卦名 → 『☰乾』（卦形 U+2630..2637，Segoe UI Symbol 自带）"""
    return f"{GUA.get(name, '')}{name}"


def star(s):
    """九星 → 『☰乾卦·六白金·西北』：后天八卦的卦形/卦名 + 九宫飞星 + 五行 + 方位"""
    return f"{gua(s.getPosition())}卦·{s.getNumber()}{s.getColor()}{s.getWuXing()}·{s.getPositionDesc()}"


def palace(stars):
    """后天八卦九宫图（上南下北）。stars = [(标记, 九星)]，标出当天/当月/当年九星所落之宫"""
    def cell(name):
        marks = "".join(m for m, s in stars if s.getPosition() == name)
        return (GUA.get(name, "") + name if name != "中" else "中") + (marks or "　")
    rows = (("巽", "离", "坤"), ("震", "中", "兑"), ("艮", "坎", "乾"))
    return "\n".join("　".join(cell(c) for c in r) for r in rows)


jq = l.getJieQi()
extra = l.getFestivals() + l.getOtherFestivals()
tag = jq or (extra[0] if extra else "")
brief = f"农历{l.getMonthInChinese()}月{l.getDayInChinese()}" + (f" · {tag}" if tag else "")

yi = [x for x in l.getDayYi() if x != "无"]
ji = [x for x in l.getDayJi() if x != "无"]
ds = l.getDayNineStar()
detail = (f"宜 {' '.join(yi[:3]) or '无'} ｜ 忌 {' '.join(ji[:3]) or '无'}"
          f" ｜ 日{gua(ds.getPosition())}卦 {ds.getNumber()}{ds.getColor()}")

nxt = l.getNextJieQi()
nxt_days = (datetime.date(*map(int, nxt.getSolar().toYmd().split("-"))) - n).days
# ── 名词白话：传统择日的说法，仅供参考 ──
JIANCHU = {
    "建": "诸事起头，宜出行、上任，忌动土", "除": "除旧布新，宜清扫、祭祀、治病，忌结婚",
    "满": "圆满之日，宜祈福、庆典，忌服药", "平": "平常之日，宜修饰、平整，忌开仓",
    "定": "安定之日，宜订约、嫁娶，忌诉讼", "执": "执守之日，宜捕捉、守成，忌搬迁远行",
    "破": "冲破之日，诸事不利，只宜拆除", "危": "危险之日，宜守不宜进，忌登高",
    "成": "成就之日，宜开业、签约、嫁娶", "收": "收藏之日，宜收债、入库，忌出行",
    "开": "开通之日，宜开业、动土、求学", "闭": "闭塞之日，宜收尾、封存，忌开张",
}
STAR = {  # 九宫飞星：数字 → 一句话
    1: "水，主人缘贵人（偏吉）", 2: "土，主病气（偏凶）", 3: "木，主口舌是非（小凶）",
    4: "木，主文昌学业（平吉）", 5: "土，五黄，最凶之星", 6: "金，主权威贵人（吉）",
    7: "金，主口舌破财（小凶）", 8: "土，主财运（吉）", 9: "火，主喜庆（吉）",
}
GUA_XIANG = "☰天 ☱泽 ☲火 ☳雷 ☴风 ☵水 ☶山 ☷地（三画自下往上读，实线阳、断线阴）"
chong = l.getDayChongShengXiao()
dn = ds.getNumber() if isinstance(ds.getNumber(), int) else 0
dn = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}.get(ds.getNumber(), dn)
H = "　　↳ "  # 提示行前缀

tip = "\n".join([
    f"{l.getYearInGanZhi()}年（{l.getYearShengXiao()}） {l.getMonthInGanZhi()}月 {l.getDayInGanZhi()}日",
    f"{H}干支：天干(10)×地支(12)配成的60轮回纪法，用来记年、月、日",
    f"纳音 {l.getDayNaYin()}",
    f"{H}干支对应的五行意象，如「大溪水」= 山涧流水",
    f"节气：{jq or '距' + nxt.getName() + ' ' + str(nxt_days) + ' 天'}",
    f"{H}一年24个太阳位置节点，是农历里对应农时/气温的刻度",
    f"宜：{' '.join(yi) or '无'}",
    f"忌：{' '.join(ji) or '无'}",
    f"{H}传统认为当天适合/不适合做的事；「无」「诸事不宜」按字面理解",
    "── 八卦 · 九宫飞星 ──",
    f"{H}1–9九颗星按固定路线轮流入驻九宫，年/月/日各一颗；",
    f"{H}星落在哪一宫，就对应那一宫的卦。一白六白八白九紫偏吉，二黑五黄偏凶",
    f"年 {star(l.getYearNineStar())}",
    f"月 {star(l.getMonthNineStar())}",
    f"日 {star(ds)}",
    f"{H}今日 {ds.getNumber()}{ds.getColor()}：{STAR.get(dn, '')}",
    palace([("●", ds), ("○", l.getMonthNineStar()), ("△", l.getYearNineStar())]),
    "（● 日　○ 月　△ 年　上南下北）",
    GUA_XIANG,
    "── 今日方位 ──",
    f"喜神 {l.getDayPositionXiDesc()}　← 出门、会客、办喜事面向此方",
    f"财神 {l.getDayPositionCaiDesc()}　← 谈生意、求财宜朝此方",
    f"福神 {l.getDayPositionFuDesc()}　← 求福、祈愿宜朝此方",
    f"阳贵 {l.getDayPositionYangGuiDesc()}　阴贵 {l.getDayPositionYinGuiDesc()}",
    f"{H}贵人方位：白天求人帮忙看阳贵，夜晚看阴贵",
    "── 值日神煞 ──",
    f"建除 {l.getZhiXing()}　← 十二值日之一：{JIANCHU.get(l.getZhiXing(), '')}",
    f"二十八宿 {l.getXiu()}（{l.getXiuLuck()}）",
    f"{H}月亮每天经过一宿，二十八宿轮流值日，各有吉凶",
    f"天神 {l.getDayTianShen()}（{l.getDayTianShenLuck()}）",
    f"{H}十二天神：黄道=吉日（青龙明堂金匮天德玉堂司命），黑道=凶日",
    f"冲 {l.getDayChongDesc()}　← 与今日相冲的是属{chong}的人，传统说宜低调谨慎",
    f"煞 {l.getDaySha()}　← 今日{l.getDaySha()}方不宜动土、远行",
    "（以上均为传统民俗说法，仅供文化参考）",
])
print(json.dumps({"brief": brief, "detail": detail, "tip": tip}, ensure_ascii=False))
