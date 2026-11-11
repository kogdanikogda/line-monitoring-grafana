"""Build "Линия Цесис 2" for local Grafana 12.4: the GitHub prototype (production head view) adapted to Grafana.

One screen for any period: a shift, a day, a week or a month. Everything is recalculated for the chosen period with
standard Grafana transformations (filter by ${__from}/${__to}, group by, reduce). Standard panels everywhere except
the header (HTML graphics panel, already installed in Peresvet): one period field with a calendar that applies at once,
presets, and the verdict sentence.

Demo data: October 2026, line Cesis 2, two 12-hour shifts (08:00 and 20:00), Sundays off. Rates, plan, states and
colours follow prototype/line-cesis2.html. Story: servo faults of carriage 2 spike on 12–17 Oct, encoder replaced on
Sunday 18 Oct; unexplained stops decline over the month.
Run: python3 generator/make_line.py  -> writes dashboard/line.json
"""
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(11)
TZ = "+03:00"
START = datetime(2026, 10, 1, 8)
END = datetime(2026, 11, 1, 8)
SHIFT = 720
PLAN_SHIFT = 520
SETUP_NORM = 20
TPL = {"№12": 52, "№27": 44, "№34": 48}          # cards per hour of pure work
MON = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

# state colours = prototype tokens --s-* ("Тихая норма")
STATE_C = {"Работа": "#C9DCD0", "Стоп": "#C8372D", "Пауза": "#F2C14E", "Ожидание материала": "#E3C79A",
           "Переналадка": "#CFC9EE", "Тепловая защита": "#EE9A5B", "Авария привода": "#7E1F1A",
           "Нет данных": "#E4E4E1", "Выходной": "#F1F1EE"}
TPL_C = {"№12": "#3F6FD1", "№27": "#22899B", "№34": "#7A6FC4", "переналадка": "#CFC9EE", "Выходной": "#F1F1EE"}
INK, BAD, LOSS, PLANC, MUTED = "#24513A", "#C8372D", "#E8A39C", "#8C8C88", "#5F5E5A"


def ms(dt):
    return int((dt - datetime(1970, 1, 1, 3)).total_seconds() * 1000)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + TZ


def dur(m):
    m = round(m)
    return f"{m} мин" if m < 60 else f"{m // 60} ч {m % 60:02d} мин"


def poisson(lam):
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= random.random()
        if p <= l:
            return k
        k += 1


# ---------- the month model ----------
SEG, SHIFTS = [], []
tpl_now = "№12"
day = START
while day < END:
    if day.weekday() == 6:
        SEG.append(dict(t=day, end=day + timedelta(days=1), state="Выходной", tpl="Выходной", reason="", group="", d=0,
                        cards=0, lost=0))
        day += timedelta(days=1)
        continue
    for si, (sname, h0) in enumerate([("день", 8), ("ночь", 20)]):
        t0 = day.replace(hour=h0)
        d = day.day
        servo = 3.5 if 12 <= d <= 17 else 0.3 if d >= 19 else 1.0
        unspec = 1.6 - d / 31
        night = 1.15 if si else 1.0
        kinds = [
            ("Авария привода", "Авария сервопривода каретки 2", "Аварии", 0.5 * servo, (10, 35)),
            ("Стоп", "Причина не указана", "Причина не указана", 1.4 * unspec * night, (5, 20)),
            ("Стоп", "Замена бунта", "Материал", 0.7, (8, 18)),
            ("Стоп", "Заедание прутка", "Оборудование", 0.5 * night, (4, 12)),
            ("Стоп", "Брак сварки / ручная правка", "Качество", 0.3, (5, 15)),
            ("Стоп", "Логистика", "Материал", 0.35 * night, (8, 20)),
            ("Пауза", "Нет поперечной заготовки", "Материал", 0.7, (3, 10)),
            ("Ожидание материала", "Нет заготовки дольше 20 с", "Материал", 0.8, (3, 8)),
            ("Тепловая защита", "Перегрев контактора К4", "Предупреждения", 0.25 * (1.6 if servo > 1 else 1), (5, 12)),
            ("Нет данных", "Обрыв связи с ПЛК", "Не простой", 0.15, (6, 18)),
        ]
        evs = []
        for st, rs, gr, lam, (a, b) in kinds:
            for _ in range(poisson(lam)):
                evs.append([st, rs, gr, random.randint(a, b)])
        for _ in range(random.choice([0, 1, 1, 2, 2, 3])):
            evs.append(["Переналадка", "Смена шаблона", "Плановое", max(10, round(random.gauss(23, 7) * night))])
        random.shuffle(evs)
        work = SHIFT - sum(e[3] for e in evs)
        w = [random.random() + 0.3 for _ in range(len(evs) + 1)]
        gaps = [work * x / sum(w) for x in w]
        perf = random.uniform(0.9, 0.95) if servo > 1 else random.uniform(0.94, 0.99)
        t, sh = t0, dict(t=t0, end=t0 + timedelta(minutes=SHIFT), label=f"{d} {MON[9]} · {sname}", done=0, lost=0,
                         work=0, avail=SHIFT, setups=0, over=0, down=0, by={})
        for i in range(len(evs) + 1):
            g = gaps[i]
            if g > 0.5:
                c = g / 60 * TPL[tpl_now] * perf
                SEG.append(dict(t=t, end=t + timedelta(minutes=g), state="Работа", tpl=tpl_now, reason="", group="",
                                d=g, cards=c, lost=0))
                sh["done"] += c; sh["work"] += g
                t += timedelta(minutes=g)
            if i == len(evs):
                break
            st, rs, gr, dd = evs[i]
            rate = TPL[tpl_now]
            if st == "Переналадка":
                nxt = random.choice([x for x in TPL if x != tpl_now])
                rs = f"Смена шаблона {tpl_now} → {nxt}"
                lost = max(0, dd - SETUP_NORM) / 60 * rate
                sh["setups"] += 1; sh["over"] += max(0, dd - SETUP_NORM)
                SEG.append(dict(t=t, end=t + timedelta(minutes=dd), state=st, tpl="переналадка", reason=rs, group=gr,
                                d=dd, cards=0, lost=lost, norm=min(dd, SETUP_NORM), over=max(0, dd - SETUP_NORM)))
                tpl_now = nxt
            else:
                lost = 0 if st == "Нет данных" else dd / 60 * rate
                SEG.append(dict(t=t, end=t + timedelta(minutes=dd), state=st, tpl=tpl_now, reason=rs, group=gr, d=dd,
                                cards=0, lost=lost))
            if st == "Нет данных":
                sh["avail"] -= dd
            else:
                sh["down"] += dd
                key = "Переналадка сверх нормы" if st == "Переналадка" else rs
                sh["by"][key] = sh["by"].get(key, 0) + lost
            sh["lost"] += lost
            t += timedelta(minutes=dd)
        SHIFTS.append(sh)
    day += timedelta(days=1)
SEG.append(dict(t=END, end=END + timedelta(hours=1), state="Выходной", tpl="Выходной", reason="", group="", d=0, cards=0, lost=0))


def csv(header, rows):
    out = [",".join(header)]
    for r in rows:
        out.append(",".join(str(x).replace(",", " ") for x in r))
    return "\n".join(out)


def r1(x):
    return round(x, 1)


# segments: timeline, reasons, templates, header
SEG_CSV = csv(["time", "Конец", "Состояние", "Шаблон", "Причина", "Группа", "Мин", "Карт", "Потеря"],
              [[iso(s["t"]), ms(s["end"]), s["state"], s["tpl"], "Смена шаблона" if s["state"] == "Переналадка" else s["reason"], s["group"], r1(s["d"]), r1(s["cards"]),
                r1(s["lost"])] for s in SEG])

# shifts: KPIs and header
SHIFT_CSV = csv(["time", "Конец", "Смена", "План", "Сделано", "Работа", "Доступно", "Потеря", "Переналадки", "Сверх",
                 "Простой", "Главная"],
                [[iso(s["t"]), ms(s["end"]), s["label"], PLAN_SHIFT, round(s["done"]), r1(s["work"]), r1(s["avail"]),
                  r1(s["lost"]), s["setups"], r1(s["over"]), r1(s["down"]),
                  max(s["by"].items(), key=lambda kv: kv[1])[0] if s["by"] else "—"] for s in SHIFTS])


# output buckets: hourly (shift scale) and daily (days, month)
def spread(t0, t1, field):
    tot = 0
    for s in SEG:
        a, b = max(s["t"], t0), min(s["end"], t1)
        if b > a and s["d"]:
            tot += s[field] * (b - a).total_seconds() / 60 / s["d"]
    return tot


OUT = []
for sh in SHIFTS:
    for h in range(12):
        a = sh["t"] + timedelta(hours=h)
        OUT.append([iso(a + timedelta(minutes=30)), ms(a + timedelta(hours=1)), "shift", r1(spread(a, a + timedelta(hours=1), "cards")),
                    r1(spread(a, a + timedelta(hours=1), "lost")), r1(PLAN_SHIFT / 12)])
d = START
while d < END:
    if d.weekday() != 6:
        e = d + timedelta(days=1)
        OUT.append([iso(d + timedelta(hours=4)), ms(e), "days|month", round(spread(d, e, "cards")), round(spread(d, e, "lost")),
                    2 * PLAN_SHIFT])
    d += timedelta(days=1)
OUT.sort(key=lambda r: r[0])
OUT_CSV = csv(["time", "Конец", "Масштаб", "Сделано", "Не сделано из-за простоев", "План"], OUT)

# changeovers: each one (shift), per day (days), per week (month)
CH = []
setups = [s for s in SEG if s["state"] == "Переналадка"]
for s in setups:
    CH.append([iso(s["t"]), ms(s["end"]), "shift", f"{s['reason'].replace('Смена шаблона ', '')} · {s['t']:%H:%M}", s["norm"], s["over"]])
d = START
while d < END:
    e = d + timedelta(days=1)
    xs = [s for s in setups if d <= s["t"] < e]
    if xs:
        CH.append([iso(d), ms(e), "days", f"{d.day} {MON[9]} ({len(xs)} шт.)", sum(s["norm"] for s in xs), sum(s["over"] for s in xs)])
    d = e
for a, b in [(1, 3), (5, 10), (12, 17), (19, 24), (26, 31)]:
    t0, t1 = datetime(2026, 10, a, 8), datetime(2026, 10, b, 8) + timedelta(days=1)
    xs = [s for s in setups if t0 <= s["t"] < t1]
    CH.append([iso(t0), ms(t1), "month", f"{a}–{b} {MON[9]} ({len(xs)} шт.)", sum(s["norm"] for s in xs), sum(s["over"] for s in xs)])
CH.sort(key=lambda r: r[0])
CH_CSV = csv(["time", "Конец", "Масштаб", "Переналадка", "В норме", "Сверх нормы"], CH)

# journal: stops and events (shift scale) or shifts (days, month)
JR = []
for s in SEG:
    if s["state"] in ("Работа", "Выходной"):
        continue
    if s["state"] == "Нет данных":
        loss = "не простой"
    elif s["state"] == "Переналадка":
        loss = f"плановое, +{round(s['over'])} мин сверх нормы" if s["over"] else "плановое, в норме"
    else:
        loss = f"≈ {round(s['lost'])}"
    JR.append([iso(s["t"]), ms(s["end"]), "shift", f"{s['t']:%d.%m} {s['t']:%H:%M}–{s['end']:%H:%M}", s["state"], s["reason"],
               dur(s["d"]), loss])
for sh in SHIFTS:
    p = sh["done"] / PLAN_SHIFT
    JR.append([iso(sh["t"]), ms(sh["end"]), "days|month", sh["label"], f"{p:.0%} плана · {round(sh['done'])} из {PLAN_SHIFT}",
               max(sh["by"].items(), key=lambda kv: kv[1])[0] if sh["by"] else "—", dur(sh["down"]), f"≈ {round(sh['lost'])}"])
JR.sort(key=lambda r: r[0])
JR_CSV = csv(["time", "Конец", "Масштаб", "Когда", "Что", "Причина", "Длительность", "Не сделано карт"], JR)

# ---------- panels ----------
DS = {"type": "grafana-testdata-datasource", "uid": "demo"}


def q(c, ref="A"):
    return {"refId": ref, "datasource": DS, "scenarioId": "csv_content", "csvContent": c}


RANGE = {"id": "filterByValue", "options": {"type": "include", "match": "all", "filters": [
    {"fieldName": "Конец", "config": {"id": "greater", "options": {"value": "${__from}"}}},
    {"fieldName": "time", "config": {"id": "lower", "options": {"value": "${__to}"}}}]}}
SCALE = {"id": "filterByValue", "options": {"type": "include", "match": "all", "filters": [
    {"fieldName": "Масштаб", "config": {"id": "regex", "options": {"value": "${scale}"}}}]}}


def hide(*names):
    return {"id": "organize", "options": {"excludeByName": {n: True for n in names}, "renameByName": {}, "indexByName": {}}}


def calc(left, op, right, alias):
    r = {"fixed": str(right)} if isinstance(right, (int, float)) else {"matcher": {"id": "byName", "options": right}}
    return {"id": "calculateField", "options": {"mode": "binary", "alias": alias, "replaceFields": False,
                                                "binary": {"left": {"matcher": {"id": "byName", "options": left}}, "operator": op, "right": r}}}


def fixed(c):
    return {"mode": "fixed", "fixedColor": c}


def by_name(name, *props):
    return {"matcher": {"id": "byName", "options": name}, "properties": list(props)}


def by_regex(rx, *props):
    return {"matcher": {"id": "byRegexp", "options": rx}, "properties": list(props)}


def mapping(colors):
    return [{"type": "value", "options": {k: {"color": v, "index": i} for i, (k, v) in enumerate(colors.items())}}]


TU = [by_regex(".*, мин$", {"id": "unit", "value": "suffix: мин"}, {"id": "decimals", "value": 0}),
      by_regex(".*, ч$", {"id": "unit", "value": "suffix: ч"}, {"id": "decimals", "value": 1})]


def only(pattern):
    return {"id": "filterFieldsByName", "options": {"include": {"pattern": pattern}}}


# --- header: period field + verdict (HTML graphics) ---
HEAD_HTML = '<div id="h"></div>'
HEAD_CSS = r"""
:host{all:initial}
#h{font-family:Inter,"Helvetica Neue",Arial,sans-serif;color:#121519;display:flex;flex-direction:column;gap:16px;padding:8px 4px 0}
.card{display:flex;align-items:center;gap:24px;background:#fff;border:1px solid #E2E6E8;border-radius:8px;padding:16px 24px}
.logo{font:800 40px/40px "Arial Narrow","Helvetica Neue",Arial,sans-serif;color:#1B4F9C;letter-spacing:-1px;white-space:nowrap}
.logo sup{font-size:12px;vertical-align:top;margin-left:2px}
.ti{font-size:20px;line-height:28px;font-weight:600}.st{font-size:13px;line-height:20px;color:#5F5E5A}
.sp{flex:1}.demo{font-size:12px;line-height:16px;color:#5F5E5A;background:#EEF1F2;border-radius:16px;padding:4px 12px;white-space:nowrap}
.clk{display:flex;flex-direction:column;align-items:flex-end}.clk b{font-size:24px;line-height:32px;font-weight:600}.clk span{font-size:12px;line-height:16px;color:#5F5E5A}
.bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.fld{display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 16px;border:1px solid #CCD3D6;border-radius:8px;background:#fff;font:600 16px/24px inherit;font-family:inherit;color:#121519;cursor:pointer}
.fld:hover{border-color:#8C969B}.fld .ic{width:16px;height:16px;flex:none}.fld .car{color:#5F5E5A;font-weight:400}
.ar{width:40px;height:40px;border:1px solid #CCD3D6;border-radius:8px;background:#fff;font-size:16px;color:#121519;cursor:pointer;font-family:inherit}
.ar:hover{border-color:#8C969B}
.chips{display:inline-flex;gap:4px;margin-left:8px;padding:4px;background:#EEF1F2;border-radius:8px}
.chip{height:32px;padding:0 16px;border:0;border-radius:6px;background:transparent;font:500 14px/20px inherit;font-family:inherit;color:#3B4247;cursor:pointer}
.chip:hover{background:#E2E6E8}.chip.on{background:#121519;color:#fff}
.v{display:flex;flex-direction:column;gap:4px}
.v .h1{font-size:24px;line-height:32px;font-weight:600}
.v .t{font-size:16px;line-height:24px}.v .m{color:#5F5E5A}
.v b{font-weight:600}.v .bad{color:#C8372D}
"""
HEAD_JS = r"""
const H = htmlGraphics, root = htmlNode.getElementById('h');
const LS = H.locationService, TS = getTemplateSrv();
const DAY = 864e5, HR = 36e5, OFF = 8 * HR;                       // production day: 08:00 -> 08:00
const MON = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
const MONF = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
const DATA_END = new Date(2026, 10, 1, 8).getTime();              // demo data end: 1 Nov 08:00
const from = H.props.timeRange.from.valueOf(), to = H.props.timeRange.to.valueOf(), span = to - from;
const scale = span <= DAY + HR ? 'shift' : span <= 10 * DAY ? 'days' : 'month', tu = scale === 'shift' ? 'мин' : 'ч';
if (TS.replace('${scale}') !== scale || TS.replace('${tu}') !== tu) { LS.partial({ 'var-scale': scale, 'var-tu': tu }, true); }
const go = (f, t) => LS.partial({ from: f, to: t, 'var-scale': null, 'var-tu': null });
const dayStart = ms => { const d = new Date(ms - OFF); return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 8).getTime(); };
const fmtD = ms => { const d = new Date(ms); return d.getDate() + ' ' + MON[d.getMonth()]; };
const num = n => Math.round(n).toLocaleString('ru-RU');
const dur = m => { m = Math.round(m); return m < 60 ? m + ' мин' : Math.floor(m / 60) + ' ч ' + String(m % 60).padStart(2, '0') + ' мин'; };
const pl = (n, a, b, c) => { n = Math.abs(Math.round(n)) % 100; const k = n % 10; return n > 10 && n < 20 ? c : k === 1 ? a : k > 1 && k < 5 ? b : c; };

// label of the field
function label() {
  const a = new Date(from), lastDay = new Date(to - OFF - 1), yr = ' ' + lastDay.getFullYear();
  if (span === 12 * HR && (a.getHours() === 8 || a.getHours() === 20)) return fmtD(from) + ', ' + (a.getHours() === 8 ? 'дневная смена 08–20' : 'ночная смена 20–08');
  if (a.getHours() === 8 && span % DAY === 0) {
    if (span === DAY) return fmtD(from) + yr + ', 08:00–08:00';
    const sameM = a.getMonth() === lastDay.getMonth();
    return (sameM ? a.getDate() : fmtD(from)) + ' – ' + fmtD(lastDay.getTime()) + yr;
  }
  const f = ms => new Date(ms).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  return f(from) + ' – ' + f(to);
}
const PRE = [['Смена', DATA_END - 12 * HR, DATA_END], ['Сутки', DATA_END - DAY, DATA_END],
             ['Неделя', DATA_END - 7 * DAY, DATA_END], ['Месяц', new Date(2026, 9, 1, 8).getTime(), DATA_END]];

// verdict from the data (already the full month; filtered here by the range)
function frame(name) { return (data.series || []).find(s => s.refId === name); }
function rows(f) {
  if (!f) return [];
  const n = f.fields[0].values.length, out = [];
  for (let i = 0; i < n; i++) { const r = {}; f.fields.forEach(x => r[x.name] = x.values.get ? x.values.get(i) : x.values[i]); out.push(r); }
  return out;
}
const inR = r => r['Конец'] > from && r.time < to;
const sh = rows(frame('S')).filter(inR), sg = rows(frame('G')).filter(inR);
let html;
if (!sh.length) {
  html = '<div class="v"><div class="h1">Нет данных за выбранный период</div><div class="t m">Демо-данные есть с 1 по 31 октября 2026.</div></div>';
} else {
  const S = k => sh.reduce((a, r) => a + (+r[k] || 0), 0);
  const done = S('Сделано'), plan = S('План'), lost = S('Потеря'), work = S('Работа'), avail = S('Доступно'), over = S('Сверх'), nset = S('Переналадки');
  const pct = Math.round(done / plan * 100), gap = Math.round(done - plan);
  const by = {};
  sg.forEach(r => { if (r['Состояние'] === 'Работа' || r['Состояние'] === 'Выходной' || r['Состояние'] === 'Нет данных') return;
    const k = r['Состояние'] === 'Переналадка' ? 'переналадки сверх нормы' : r['Причина'];
    by[k] = by[k] || { m: 0, c: 0 }; by[k].m += r['Состояние'] === 'Переналадка' ? Math.max(0, r['Мин'] - 20) : +r['Мин']; by[k].c += +r['Потеря']; });
  const top = Object.entries(by).sort((a, b) => b[1].c - a[1].c)[0];
  const who = span === 12 * HR ? 'За смену' : span === DAY ? 'За сутки' : 'За период';
  html = '<div class="v"><div class="h1">' + who + ' сделано ' + num(done) + ' ' + pl(done, 'карта', 'карты', 'карт') + ' при плане ' + num(plan) +
    ' — <span class="' + (pct < 90 ? 'bad' : '') + '">' + pct + '%</span>' + (gap < 0 ? ' (−' + num(-gap) + ')' : '') + '</div>' +
    '<div class="t">Из‑за простоев не сделано <b>≈ ' + num(lost) + ' ' + pl(lost, 'карта', 'карты', 'карт') + '</b>.' +
    (top ? ' Больше всего потеряли на «' + top[0] + '»: ' + dur(top[1].m) + ', ≈ ' + num(top[1].c) + ' ' + pl(top[1].c, 'карта', 'карты', 'карт') + '.' : '') + '</div>' +
    '<div class="t m">Линия в работе ' + Math.round(work / avail * 100) + '% времени. Переналадок ' + nset + (over > 0 ? ', сверх нормы ' + dur(over) : ', все в норме') + '.</div></div>';
}

const cal = '<svg class="ic" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="3" width="12" height="11" rx="2"/><path d="M2 7h12M5 1.5v3M11 1.5v3"/></svg>';
const card = '<div class="card"><div class="logo">ЦеСИС<sup>®</sup></div><div><div class="ti">Линия Цесис 2</div>' +
  '<div class="st">Итоги работы линии · план‑факт · простои · переналадки</div></div><div class="sp"></div>' +
  '<div class="demo">Предложение Нейропрома · демо‑данные, октябрь 2026</div><div class="clk"><b id="ck"></b><span id="cd"></span></div></div>';
root.innerHTML = card + '<div class="bar"><button class="ar" id="pv" title="Предыдущий такой же период">‹</button>' +
  '<button class="fld" id="fld">' + cal + '<span>' + label() + '</span><span class="car">▾</span></button>' +
  '<button class="ar" id="nx" title="Следующий такой же период">›</button><div class="chips">' +
  PRE.map((p, i) => '<button class="chip' + (p[1] === from && p[2] === to ? ' on' : '') + '" data-i="' + i + '">' + p[0] + '</button>').join('') +
  '</div></div>' + html;
const tick = () => { const d = new Date(), ck = root.querySelector('#ck'), cd = root.querySelector('#cd'); if (!ck) return;
  ck.textContent = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }); cd.textContent = d.toLocaleDateString('ru-RU'); };
tick(); clearInterval(window.__nprClock); window.__nprClock = setInterval(tick, 15000);
root.querySelectorAll('.chip').forEach(b => b.onclick = () => { const p = PRE[+b.dataset.i]; go(p[1], p[2]); });
root.querySelector('#pv').onclick = () => go(from - span, to - span);
root.querySelector('#nx').onclick = () => go(from + span, to + span);

// calendar popover: click the first day, click the last day -> applied at once
root.querySelector('#fld').onclick = (ev) => {
  ev.stopPropagation();
  let pop = document.getElementById('npr-cal');
  if (pop) { pop.remove(); return; }
  pop = document.createElement('div'); pop.id = 'npr-cal';
  const r = ev.currentTarget.getBoundingClientRect();
  pop.style.cssText = 'position:fixed;z-index:9999;left:' + r.left + 'px;top:' + (r.bottom + 8) + 'px';
  document.body.appendChild(pop);
  const sr = pop.attachShadow({ mode: 'open' });
  let view = new Date(dayStart(from)); view = new Date(view.getFullYear(), view.getMonth(), 1);
  let a = null, hov = null;
  const close = () => { pop.remove(); document.removeEventListener('mousedown', out); document.removeEventListener('keydown', esc); };
  const out = e => { if (!e.composedPath().includes(pop)) close(); };
  const esc = e => { if (e.key === 'Escape') close(); };
  setTimeout(() => { document.addEventListener('mousedown', out); document.addEventListener('keydown', esc); });
  const selA = dayStart(from), selB = dayStart(to - 1);
  function draw() {
    const y = view.getFullYear(), m = view.getMonth(), first = (new Date(y, m, 1).getDay() + 6) % 7, n = new Date(y, m + 1, 0).getDate();
    let cells = '';
    for (let i = 0; i < first; i++) cells += '<span></span>';
    for (let d = 1; d <= n; d++) {
      const t = new Date(y, m, d, 8).getTime(), wd = new Date(y, m, d).getDay();
      const cls = (wd === 0 ? 'off ' : '') + (t >= DATA_END || t < new Date(2026, 9, 1, 8).getTime() ? 'nod' : '');
      cells += '<button data-t="' + t + '" class="' + cls + '">' + d + '</button>';
    }
    sr.innerHTML = '<style>' +
      '.p{font-family:Inter,"Helvetica Neue",Arial,sans-serif;background:#fff;border:1px solid #CCD3D6;border-radius:12px;box-shadow:0 8px 24px rgba(18,21,25,.12);padding:16px;width:312px;color:#121519}' +
      '.hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font:600 16px/24px inherit}' +
      '.hd button{width:40px;height:40px;border:0;border-radius:8px;background:transparent;font-size:18px;cursor:pointer}.hd button:hover{background:#EEF1F2}' +
      '.wk,.g{display:grid;grid-template-columns:repeat(7,40px);gap:4px 4px}.wk span{font-size:12px;line-height:24px;text-align:center;color:#5F5E5A}' +
      '.g button{height:40px;border:0;border-radius:8px;background:transparent;font:14px/20px inherit;cursor:pointer;color:#121519}' +
      '.g button:hover{background:#E2E6E8}.g .off{color:#9AA1A5}.g .nod{color:#C2C7CA}.g .in{background:#E7EEF0}.g .end{background:#121519;color:#fff}' +
      '.ht{margin-top:12px;font-size:12px;line-height:16px;color:#5F5E5A}</style>' +
      '<div class="p"><div class="hd"><button id="pm">‹</button><span>' + MONF[m] + ' ' + y + '</span><button id="nm">›</button></div>' +
      '<div class="wk">' + ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map(x => '<span>' + x + '</span>').join('') + '</div>' +
      '<div class="g">' + cells + '</div><div class="ht" id="ht"></div></div>';
    sr.getElementById('pm').onclick = () => { view = new Date(y, m - 1, 1); draw(); };
    sr.getElementById('nm').onclick = () => { view = new Date(y, m + 1, 1); draw(); };
    sr.querySelectorAll('.g button').forEach(b => {
      b.onmouseenter = () => { if (a !== null) { hov = +b.dataset.t; paint(); } };
      b.onclick = () => { const t = +b.dataset.t; if (a === null) { a = t; hov = t; paint(); } else { close(); go(Math.min(a, t), Math.max(a, t) + DAY); } };
    });
    paint();
  }
  // only classes change on hover: rebuilding the buttons would swallow the second click
  function paint() {
    let lo, hi;
    if (a !== null) { const b = hov === null ? a : hov; lo = Math.min(a, b); hi = Math.max(a, b); } else { lo = selA; hi = selB; }
    sr.querySelectorAll('.g button').forEach(b => { const t = +b.dataset.t;
      b.classList.toggle('end', t === lo || t === hi); b.classList.toggle('in', t > lo && t < hi); });
    sr.getElementById('ht').textContent = a === null ? 'Нажмите на первый день периода. Сутки считаются с 08:00 до 08:00.' : 'Теперь — на последний день. Тот же день ещё раз — одни сутки.';
  }
  draw();
};
"""


def header():
    return {"type": "gapit-htmlgraphics-panel", "title": "", "transparent": True, "gridPos": {"x": 0, "y": 0, "w": 24, "h": 7},
            "targets": [q(SHIFT_CSV, "S"), q(SEG_CSV, "G")],
            "options": {"html": HEAD_HTML, "css": HEAD_CSS, "onRender": HEAD_JS, "onInit": "", "rootCSS": "",
                        "renderOnMount": True, "panelupdateOnMount": True, "dynamicData": False, "dynamicFieldDisplayValues": False,
                        "dynamicHtmlGraphics": False, "dynamicProps": False, "centerAlignContent": False, "overflow": "visible",
                        "useGrafanaScrollbar": False, "SVGBaseFix": True, "codeData": "{}", "calcsMutation": "standard",
                        "onInitOnResize": False, "add100Percentage": True}}


def timeline():
    return {"type": "state-timeline", "title": "Состояние линии и шаблон",
            "description": "Каждый цвет — состояние линии. Наведите на участок — покажу время и длительность. Работа — спокойный светлый, цвет только у отклонений.",
            "gridPos": {"x": 0, "y": 5, "w": 24, "h": 6}, "targets": [q(SEG_CSV)],
            "transformations": [hide("Конец", "Причина", "Группа", "Мин", "Карт", "Потеря")],
            "fieldConfig": {"defaults": {"custom": {"fillOpacity": 100, "lineWidth": 0}, "color": {"mode": "fixed", "fixedColor": "#C9DCD0"},
                                         "mappings": mapping({**STATE_C, **TPL_C})}, "overrides": []},
            "options": {"mergeValues": True, "showValue": "never", "alignValue": "left", "rowHeight": 0.8,
                        "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "single", "sort": "none"}}}


def kpis():
    base = [RANGE, {"id": "reduce", "options": {"mode": "reduceFields", "reducers": ["sum"], "includeTimeField": False}},
            calc("Сделано", "/", "План", "Выполнение"), calc("Работа", "/", "Доступно", "В работе"),
            calc("Сверх", "/", 60, "Сверх, ч"), calc("Сверх", "*", 1, "Сверх, мин")]

    def st(title, x, field, unit, color, desc, extra=None):
        fc = {"defaults": {"unit": unit, "decimals": 0, "color": fixed(color)}, "overrides": TU}
        if extra:
            fc["defaults"].update(extra)
        return {"type": "stat", "title": title, "description": desc, "gridPos": {"x": x, "y": 11, "w": 6, "h": 4},
                "targets": [q(SHIFT_CSV)], "transformations": base + ([only(field)] if "$" in field else []), "fieldConfig": fc,
                "options": {"colorMode": "value", "graphMode": "none", "textMode": "value", "justifyMode": "auto", "wideLayout": True,
                            "showPercentChange": False, "text": {"valueSize": 40},
                            "reduceOptions": {"calcs": ["lastNotNull"], "fields": field if "$" not in field else "", "values": False}}}

    red_below = {"color": {"mode": "thresholds"}, "thresholds": {"mode": "absolute", "steps": [{"color": BAD, "value": None}, {"color": INK, "value": 0.9}]}}
    return [st("Выполнение плана", 0, "/^Выполнение$/", "percentunit", INK, "Сделано карт ÷ план за выбранный период. Красное — ниже 90%.", red_below),
            st("Не сделано из‑за простоев, карт", 6, "/^Потеря$/", "locale", BAD,
               "Минуты остановок × темп шаблона, который работал. Переналадка — только время сверх нормы."),
            st("Время в работе", 12, "/^В работе$/", "percentunit", INK, "Минуты работы ÷ время смен. Обрыв связи с ПЛК не считаем."),
            st("Переналадки сверх нормы", 18, "^Сверх, ${tu}$", "none", BAD, f"Сумма превышений нормы {SETUP_NORM} мин на переналадку.")]


def templates():
    return {"type": "table", "title": "Выпуск по шаблонам", "description": "Какой шаблон работал и сколько карт на нём сделано. Названия шаблонов задаёт начальник производства.",
            "gridPos": {"x": 0, "y": 15, "w": 9, "h": 8}, "targets": [q(SEG_CSV)],
            "transformations": [RANGE,
                                {"id": "filterByValue", "options": {"type": "include", "match": "any", "filters": [
                                    {"fieldName": "Состояние", "config": {"id": "equal", "options": {"value": "Работа"}}}]}},
                                {"id": "groupBy", "options": {"fields": {"Шаблон": {"operation": "groupby", "aggregations": []},
                                                                          "Карт": {"operation": "aggregate", "aggregations": ["sum"]},
                                                                          "Мин": {"operation": "aggregate", "aggregations": ["sum"]}}}},
                                calc("Карт (sum)", "/", "Мин (sum)", "r"), calc("r", "*", 60, "Темп, карт/ч"),
                                {"id": "sortBy", "options": {"sort": [{"field": "Карт (sum)", "desc": True}]}},
                                {"id": "organize", "options": {"excludeByName": {"Мин (sum)": True, "r": True}, "indexByName": {},
                                                               "renameByName": {"Карт (sum)": "Сделано карт"}}}],
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}, "decimals": 0, "unit": "locale"},
                            "overrides": [by_name("Сделано карт", {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic", "valueDisplayMode": "text"}},
                                                  {"id": "color", "value": fixed(INK)}),
                                          by_name("Шаблон", {"id": "custom.width", "value": 96},
                                                  {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                                                  {"id": "mappings", "value": mapping(TPL_C)}),
                                          by_name("Темп, карт/ч", {"id": "custom.width", "value": 120})]},
            "options": {"showHeader": True, "cellHeight": "md", "footer": {"show": False}}}


def changeovers():
    return {"type": "barchart", "title": "Переналадки против нормы",
            "description": f"Светлое — время в норме ({SETUP_NORM} мин на переналадку), красное — сверх нормы. За смену — каждая переналадка, за несколько дней — по дням, за месяц — по неделям.",
            "gridPos": {"x": 9, "y": 15, "w": 15, "h": 8}, "targets": [q(CH_CSV)],
            "transformations": [RANGE, SCALE, hide("time", "Конец", "Масштаб")],
            "fieldConfig": {"defaults": {"custom": {"fillOpacity": 100, "lineWidth": 0, "axisSoftMin": 0}, "unit": "suffix: мин"},
                            "overrides": [by_name("В норме", {"id": "color", "value": fixed("#CFC9EE")}),
                                          by_name("Сверх нормы", {"id": "color", "value": fixed(BAD)})]},
            "options": {"orientation": "horizontal", "stacking": "normal", "xField": "Переналадка", "showValue": "never",
                        "barWidth": 0.7, "groupWidth": 0.7, "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi", "sort": "none"}, "xTickLabelMaxLength": 30}}


def reasons():
    return {"type": "table", "title": "Куда ушло время",
            "description": "Остановки за период: сколько времени и сколько карт не сделали. Переналадка — плановая, в карты идёт только время сверх нормы. Обрыв связи с ПЛК — не простой, здесь его нет.",
            "gridPos": {"x": 0, "y": 23, "w": 12, "h": 10}, "targets": [q(SEG_CSV)],
            "transformations": [RANGE,
                                {"id": "filterByValue", "options": {"type": "exclude", "match": "any", "filters": [
                                    {"fieldName": "Состояние", "config": {"id": "equal", "options": {"value": v}}}
                                    for v in ("Работа", "Выходной", "Нет данных")]}},
                                {"id": "groupBy", "options": {"fields": {"Причина": {"operation": "groupby", "aggregations": []},
                                                                          "Состояние": {"operation": "groupby", "aggregations": []},
                                                                          "Мин": {"operation": "aggregate", "aggregations": ["sum"]},
                                                                          "Потеря": {"operation": "aggregate", "aggregations": ["sum"]}}}},
                                {"id": "sortBy", "options": {"sort": [{"field": "Потеря (sum)", "desc": True}]}},
                                calc("Мин (sum)", "/", 60, "Время, ч"), calc("Мин (sum)", "*", 1, "Время, мин"),
                                {"id": "organize", "options": {"excludeByName": {"Мин (sum)": True}, "indexByName": {},
                                                               "renameByName": {"Потеря (sum)": "Не сделано карт"}}},
                                only("^(Состояние|Причина|Время, ${tu}|Не сделано карт)$")],
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                            "overrides": TU + [
                                by_regex("^Время", {"id": "custom.width", "value": 120}),
                                by_name("Состояние", {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                                        {"id": "mappings", "value": mapping(STATE_C)}, {"id": "custom.width", "value": 170}),
                                by_name("Не сделано карт", {"id": "decimals", "value": 0}, {"id": "unit", "value": "locale"}, {"id": "color", "value": fixed(LOSS)},
                                        {"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic", "valueDisplayMode": "text"}})]},
            "options": {"showHeader": True, "cellHeight": "md", "footer": {"show": False}}}


def output():
    return {"type": "timeseries", "title": "Выпуск карт",
            "description": "Тёмное — сделано, светлое — не сделано из‑за простоев, пунктир — план. За смену и сутки — по часам, за период — по дням.",
            "gridPos": {"x": 12, "y": 23, "w": 12, "h": 10}, "targets": [q(OUT_CSV)],
            "transformations": [RANGE, SCALE, hide("Конец", "Масштаб")],
            "fieldConfig": {"defaults": {"custom": {"drawStyle": "bars", "fillOpacity": 100, "lineWidth": 0, "barAlignment": 0,
                                                    "stacking": {"mode": "normal", "group": "A"}, "axisSoftMin": 0, "barWidthFactor": 0.8,
                                                    "showPoints": "never"}, "unit": "none", "decimals": 0},
                            "overrides": [by_name("Сделано", {"id": "color", "value": fixed(INK)}),
                                          by_name("Не сделано из-за простоев", {"id": "color", "value": fixed(LOSS)}),
                                          by_name("План", {"id": "color", "value": fixed(PLANC)}, {"id": "custom.drawStyle", "value": "line"},
                                                  {"id": "custom.lineWidth", "value": 2}, {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [8, 6]}},
                                                  {"id": "custom.lineInterpolation", "value": "stepAfter"}, {"id": "custom.spanNulls", "value": False},
                                                  {"id": "custom.stacking", "value": {"mode": "none", "group": "B"}}, {"id": "custom.fillOpacity", "value": 0})]},
            "options": {"legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi", "sort": "none"}}}


def journal():
    return {"type": "table", "title": "${scale:text}",
            "description": "За смену и сутки — каждая остановка и событие. За период — смены, главная причина каждой.",
            "gridPos": {"x": 0, "y": 33, "w": 24, "h": 11}, "targets": [q(JR_CSV)],
            "transformations": [RANGE, SCALE, hide("time", "Конец", "Масштаб")],
            "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                            "overrides": [by_name("Когда", {"id": "custom.width", "value": 170}),
                                          by_name("Что", {"id": "custom.width", "value": 230}, {"id": "color", "value": fixed("#FFFFFF")},
                                                  {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "basic"}},
                                                  {"id": "mappings", "value": mapping(STATE_C) + [
                                                      {"type": "regex", "options": {"pattern": "^([0-8]?\\d)% .*", "result": {"color": "#F6D5D1", "index": 20}}}]}),
                                          by_name("Длительность", {"id": "custom.width", "value": 130}),
                                          by_name("Не сделано карт", {"id": "custom.width", "value": 220})]},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}}


def build():
    p = [header(), timeline()] + kpis() + [templates(), changeovers(), reasons(), output(), journal()]
    for i, x in enumerate(p, 1):
        x["id"] = i
        if i > 1:
            x["gridPos"]["y"] += 2
        x.setdefault("datasource", DS)
    hidden = lambda name, opts, cur: {"type": "custom", "name": name, "hide": 2, "skipUrlSync": False,
                                       "query": ",".join(f"{t} : {v}" for t, v in opts),
                                       "current": {"text": dict((v, t) for t, v in opts)[cur], "value": cur},
                                       "options": [{"text": t, "value": v, "selected": v == cur} for t, v in opts]}
    return {"uid": "neuroprom-line", "title": "Линия Цесис 2", "schemaVersion": 41, "editable": True,
            "graphTooltip": 1, "refresh": "", "tags": ["демо", "нейропром"], "timezone": "browser",
            "time": {"from": iso(END - timedelta(days=1)), "to": iso(END)},
            "timepicker": {"hidden": True, "refresh_intervals": []},
            "templating": {"list": [
                {"type": "custom", "name": "line", "label": "Линия", "query": "Линия Цесис 2", "hide": 0,
                 "current": {"text": "Линия Цесис 2", "value": "Линия Цесис 2"},
                 "options": [{"text": "Линия Цесис 2", "value": "Линия Цесис 2", "selected": True}]},
                hidden("scale", [("Остановки и события", "shift"), ("Смены за период", "days"), ("Смены за месяц", "month")], "shift"),
                hidden("tu", [("минуты", "мин"), ("часы", "ч")], "мин")]},
            "panels": p}


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "dashboard" / "line.json"
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=1))
    done = sum(s["done"] for s in SHIFTS); plan = PLAN_SHIFT * len(SHIFTS)
    print("written", out, f"{out.stat().st_size // 1024} KB | shifts", len(SHIFTS), "done", round(done), "plan", plan,
          f"{done / plan:.0%}", "lost", round(sum(s["lost"] for s in SHIFTS)), "segments", len(SEG))
    for a, b in [(1, 11), (12, 17), (19, 31)]:
        xs = [s for s in SHIFTS if a <= s["t"].day <= b]
        print(f"  {a}-{b} Oct: {sum(s['done'] for s in xs) / (PLAN_SHIFT * len(xs)):.0%}")
