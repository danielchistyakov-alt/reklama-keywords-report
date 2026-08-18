"""Собирает отчёт по спецпроекту reklama-keywords.ru целиком: тянет обе Метрики,
считает производные и рендерит dashboard.html из template.html.

Счётчики:
  111451917 — сам спецпроект (игра + клики на Авито Рекламу)
  101840084 — Авито Реклама, цель 513361195 «Успешная регистрация»

Токен: METRIKA_TOKEN в окружении или .env рядом со скриптом.
Запуск: python3 build.py
"""
import json, os, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date

try:
    import certifi
    SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL = None

HERE = os.path.dirname(os.path.abspath(__file__))
SITE, ADS = "111451917", "101840084"
REG_GOAL = "513361195"
DATE1, DATE2 = "2026-08-10", "2026-08-31"

SUF = "[reklama-keywords.ru] - Any - Any - B2B - Perf"
GAME = [f"YM - ClickButton [{n}] {SUF}" for n in (
    "Играть", "Готово на 1-м уровне мини-игры", "Дальше на 1-м уровне мини-игры",
    "Готово на 2-м уровне мини-игры", "Дальше на 2-м уровне мини-игры",
    "Готово на 3-м уровне мини-игры", "Дальше на 3-м уровне мини-игры")]
GAME_LBL = ["Нажали «Играть»", "Готово · уровень 1", "Дальше · уровень 1",
            "Готово · уровень 2", "Дальше · уровень 2", "Готово · уровень 3",
            "Дальше · уровень 3"]
INTEREST = [f"YM - ClickButton [{n}] {SUF}" for n in (
    "Узнать больше о ключевых словах", "Как работают ключевые слова на 1-м экране",
    "Как работают ключевые слова на 3-м экране")]
INTENT = [f"YM - ClickButton [{n}] {SUF}" for n in (
    "Попробовать", "Перейти в личный кабинет",
    "Перейти в кабинет после завершения мини-игры")]

TRAFFIC_RU = {
    "Ad traffic": "Переходы по рекламе",
    "Direct traffic": "Прямые заходы",
    "Link traffic": "Переходы по ссылкам на сайтах",
    "Mailing traffic": "Переходы из почтовых рассылок",
    "Search engine traffic": "Переходы из поисковых систем",
    "Messenger traffic": "Переходы из мессенджеров",
    "Recommendation system traffic": "Переходы из рекомендательных систем",
    "Recommendation systems traffic": "Переходы из рекомендательных систем",
    "Social network traffic": "Переходы из социальных сетей",
    "Internal traffic": "Внутренние переходы",
    "Saved page traffic": "Переходы с сохранённых страниц",
    "Cached page traffic": "Переходы из кэша поисковых систем",
    "Email traffic": "Переходы из почтовых рассылок",
}
DEVICE_RU = {"Smartphones": "Смартфоны", "PC": "Десктоп",
             "Tablets": "Планшеты", "TV": "Телевизоры"}
MONTHS = ("января февраля марта апреля мая июня июля августа сентября "
          "октября ноября декабря").split()


def token():
    t = os.environ.get("METRIKA_TOKEN")
    if t:
        return t.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith("METRIKA_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit("Нет METRIKA_TOKEN: задайте переменную окружения или положите .env рядом")


TOKEN = token()


def api(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params, doseq=True),
                                 headers={"Authorization": f"OAuth {TOKEN}"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=120, context=SSL) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            if e.code in (429, 503) and attempt < 4:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"HTTP {e.code} на {url}: {body}")
        except urllib.error.URLError as e:
            if attempt < 4:
                time.sleep(2 ** attempt)
                continue
            sys.exit(f"Сеть недоступна: {e}")


def report(counter, metrics, dimensions=None, filters=None):
    p = {"ids": counter, "date1": DATE1, "date2": DATE2, "metrics": ",".join(metrics),
         "accuracy": "full", "attribution": "lastsign", "limit": 5000}
    if dimensions:
        p["dimensions"] = ",".join(dimensions)
    if filters:
        p["filters"] = filters
    r = api("https://api-metrika.yandex.net/stat/v1/data", p)
    return {"rows": [{"dims": [d.get("name") for d in x["dimensions"]], "vals": x["metrics"]}
                     for x in r.get("data", [])],
            "totals": r.get("totals") or []}


def pct(a, b):
    return round(a / b * 100, 2) if b else 0.0


# ---------------------------------------------------------------- спецпроект
def build_site():
    goals = api(f"https://api-metrika.yandex.net/management/v1/counter/{SITE}/goals",
                {"useDirect": "false"}).get("goals", [])
    gid = {g["name"]: g["id"] for g in goals}
    missing = [n for n in GAME + INTEREST + INTENT if n not in gid]
    if missing:
        print("ВНИМАНИЕ, цели не найдены в счётчике:")
        for m in missing:
            print("   -", m)

    base = ["ym:s:visits", "ym:s:users", "ym:s:bounceRate", "ym:s:avgVisitDurationSeconds"]
    used = [n for n in GAME + INTEREST + INTENT if n in gid]
    gm = [f"ym:s:goal{gid[n]}visits" for n in used]

    def pull(dims=None):
        acc, tot = {}, {}
        for i in range(0, len(gm), 14):
            part = base + gm[i:i + 14]
            r = report(SITE, part, dims)
            for row in r["rows"]:
                k = tuple(row["dims"])
                acc.setdefault(k, {"dims": list(k), "vals": {}})
                acc[k]["vals"].update(dict(zip(part, row["vals"])))
            tot.update(dict(zip(part, r["totals"])))
        return {"rows": list(acc.values()), "totals": tot}

    overall = pull()
    by_day = pull(["ym:s:date"])
    by_utm = pull(["ym:s:UTMSource"])
    by_camp = pull(["ym:s:UTMSource", "ym:s:UTMMedium", "ym:s:UTMCampaign"])
    by_traf = pull(["ym:s:lastsignTrafficSource"])

    def orf(names):
        return " OR ".join(f"ym:s:goal{gid[n]}IsReached=='Yes'" for n in names if n in gid)

    f_any, f_int, f_itn = orf(INTEREST + INTENT), orf(INTEREST), orf(INTENT)
    g_start, g_end = gid.get(GAME[1]), gid.get(GAME[6])
    seg = lambda f, d=None: report(SITE, ["ym:s:visits"], d, f)

    T, G = overall["totals"], lambda n: f"ym:s:goal{gid[n]}visits"
    V = T["ym:s:visits"]
    any_tot = seg(f_any)["totals"][0]
    d = {
        "period": {"from": f"{int(DATE1[8:])} {MONTHS[int(DATE1[5:7]) - 1]}",
                   "to": "", "full_to": f"{int(DATE2[8:])} {MONTHS[int(DATE2[5:7]) - 1]}"},
        "kpi": {"visits": V, "users": T["ym:s:users"], "bounce": T["ym:s:bounceRate"],
                "dur": T["ym:s:avgVisitDurationSeconds"]},
        "funnel": [{"label": l, "v": T[G(n)]} for l, n in zip(GAME_LBL, GAME) if n in gid],
        "clicks": {"any": any_tot,
                   "interest": seg(f_int)["totals"][0],
                   "intent": seg(f_itn)["totals"][0],
                   "after_game": seg(f"({f_any}) AND ym:s:goal{g_start}IsReached=='Yes'")["totals"][0],
                   "no_game": seg(f"({f_any}) AND ym:s:goal{g_start}IsReached=='No'")["totals"][0]},
        "game_started": T[G(GAME[1])], "game_finished": T[G(GAME[6])],
    }

    seg_day = {r["dims"][0]: r["vals"][0] for r in seg(f_any, ["ym:s:date"])["rows"]}
    d["days"] = [{"d": r["dims"][0], "visits": r["vals"]["ym:s:visits"],
                  "start": r["vals"][G(GAME[1])], "clicks": seg_day.get(r["dims"][0], 0)}
                 for r in sorted(by_day["rows"], key=lambda r: r["dims"][0])]
    d["period"]["to"] = f"{int(d['days'][-1]['d'][8:])} {MONTHS[int(d['days'][-1]['d'][5:7]) - 1]}"

    def tbl(src, dim_filter=None, ru=None):
        segmap = {" / ".join(map(str, r["dims"])): r["vals"][0]
                  for r in seg(f_any, dim_filter)["rows"]}
        out = []
        for r in src["rows"]:
            nm = " / ".join(map(str, r["dims"]))
            if re.fullmatch(r"test[a-z0-9]*", nm or "", re.I):
                continue
            v = r["vals"]
            row = {"name": ru.get(nm, nm) if ru else nm, "visits": v["ym:s:visits"],
                   "bounce": v["ym:s:bounceRate"], "dur": v["ym:s:avgVisitDurationSeconds"],
                   "play": v[G(GAME[0])], "start": v[G(GAME[1])], "fin": v[G(GAME[6])],
                   "clicks": segmap.get(nm, 0)}
            row["cr"] = pct(row["clicks"], row["visits"])
            row["engage"] = pct(row["start"], row["visits"])
            out.append(row)
        return sorted(out, key=lambda x: -x["visits"])

    def verdict(r):
        if r["visits"] >= 500 and r["bounce"] >= 70 and r["dur"] <= 15:
            return "waste"
        if r["visits"] >= 500 and r["start"] == 0 and r["cr"] >= 10:
            return "anomaly"
        return "strong" if r["cr"] >= 10 else "mid" if r["cr"] >= 3 else "weak"

    d["by_utm"] = tbl(by_utm, ["ym:s:UTMSource"])
    for r in d["by_utm"]:
        r["v"] = verdict(r)
    d["by_traffic"] = tbl(by_traf, ["ym:s:lastsignTrafficSource"], TRAFFIC_RU)
    for r in d["by_traffic"]:
        r["v"] = "strong" if r["cr"] >= 10 else "mid" if r["cr"] >= 3 else "weak"
    d["campaigns"] = [{"name": " / ".join(map(str, r["dims"])),
                       "visits": r["vals"]["ym:s:visits"], "bounce": r["vals"]["ym:s:bounceRate"],
                       "dur": r["vals"]["ym:s:avgVisitDurationSeconds"], "start": r["vals"][G(GAME[1])]}
                      for r in sorted(by_camp["rows"], key=lambda r: -r["vals"]["ym:s:visits"])
                      if not re.fullmatch(r"test[a-z0-9]*", str(r["dims"][0] or ""), re.I)][:14]
    return d


# ------------------------------------------------------- сторона Авито Рекламы
F_UTM = "ym:s:UTMSource=='landing_ads'"
F_FROM = "ym:s:startURL=@'ads_special_keywords'"
F_ALL = f"{F_UTM} OR {F_FROM}"
AM = ["ym:s:visits", "ym:s:users", f"ym:s:goal{REG_GOAL}visits",
      "ym:s:bounceRate", "ym:s:avgVisitDurationSeconds"]


def norm_url(u):
    """Схлопывает адрес входа до уникальной страницы: без query, хэш — только имя экрана."""
    u = (u or "").replace("https://", "").replace("http://", "")
    frag = ""
    if "#" in u:
        u, h = u.split("#", 1)
        frag = "#" + re.split(r"[?&]", h)[0]
    return u.split("?", 1)[0].rstrip("/") + frag


def build_ads():
    V, G = 0, 2
    allt = report(ADS, AM, None, F_ALL)["totals"]
    itr = report(ADS, AM, None, F_UTM)["totals"]
    itn = report(ADS, AM, None, F_FROM)["totals"]
    land = report(ADS, AM, ["ym:s:startURL"], F_ALL)["rows"]

    agg = {}
    for r in land:
        k = norm_url(r["dims"][0])
        s = agg.setdefault(k, {"visits": 0, "regs": 0, "raw": 0})
        s["visits"] += r["vals"][V]
        s["regs"] += r["vals"][G]
        s["raw"] += 1
    pages = sorted(({"url": k, "visits": v["visits"], "regs": v["regs"], "raw": v["raw"],
                     "cr": pct(v["regs"], v["visits"])} for k, v in agg.items()),
                   key=lambda x: -x["visits"])

    def kind(u):
        if "ads.avito.com" in u:
            return "Страница продукта"
        if "#signin" in u or "#login" in u:
            return "Экран входа или логина"
        return "Кабинет напрямую"

    gag = {}
    for p in pages:
        s = gag.setdefault(kind(p["url"]), {"visits": 0, "regs": 0, "urls": 0})
        s["visits"] += p["visits"]
        s["regs"] += p["regs"]
        s["urls"] += p["raw"]
    groups = sorted(({"name": k, "visits": v["visits"], "regs": v["regs"], "urls": v["urls"],
                      "cr": pct(v["regs"], v["visits"])} for k, v in gag.items()),
                    key=lambda x: -x["visits"])

    return {"totals": {"visits": allt[V], "users": allt[1], "regs": allt[G],
                       "bounce": allt[3], "dur": allt[4], "cr": pct(allt[G], allt[V])},
            "interest": {"visits": itr[V], "regs": itr[G], "cr": pct(itr[G], itr[V])},
            "intent": {"visits": itn[V], "regs": itn[G], "cr": pct(itn[G], itn[V])},
            "groups": groups, "pages": pages,
            "devices": [{"name": DEVICE_RU.get(str(r["dims"][0]), str(r["dims"][0])),
                         "visits": r["vals"][V], "regs": r["vals"][G],
                         "cr": pct(r["vals"][G], r["vals"][V])}
                        for r in sorted(report(ADS, AM, ["ym:s:deviceCategory"], F_ALL)["rows"],
                                        key=lambda r: -r["vals"][V])],
            "days": [{"d": r["dims"][0], "visits": r["vals"][V], "regs": r["vals"][G]}
                     for r in sorted(report(ADS, AM, ["ym:s:date"], F_ALL)["rows"],
                                     key=lambda r: r["dims"][0])]}


def main():
    print(f"Период {DATE1} — {DATE2}")
    d = build_site()
    print(f"  спецпроект {SITE}: визиты={d['kpi']['visits']:,.0f} "
          f"переходы={d['clicks']['any']:,.0f}")
    d["cabinet"] = build_ads()
    print(f"  Авито Реклама {ADS}: доехало={d['cabinet']['totals']['visits']:,.0f} "
          f"регистрации={d['cabinet']['totals']['regs']:,.0f}")

    d["e2e"] = [{"l": "Визиты на спецпроекте", "v": d["kpi"]["visits"]},
                {"l": "Кликнули на сайт Авито Рекламы", "v": d["clicks"]["any"]},
                {"l": "Доехали до сайта", "v": d["cabinet"]["totals"]["visits"]},
                {"l": "Зарегистрировали кабинет", "v": d["cabinet"]["totals"]["regs"]}]
    d["built"] = date.today().isoformat()

    json.dump(d, open(os.path.join(HERE, "dashboard_data.json"), "w", encoding="utf-8"),
              ensure_ascii=False)
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    payload = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("__DATA__", payload)
    if "__DATA__" in tpl and payload not in html:
        sys.exit("Не удалось вставить данные в шаблон")
    open(os.path.join(HERE, "dashboard.html"), "w", encoding="utf-8").write(html)
    print(f"Готово: dashboard.html ({len(html) // 1024} КБ)")


if __name__ == "__main__":
    main()
