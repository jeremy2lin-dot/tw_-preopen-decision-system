# -*- coding: utf-8 -*-
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime

import requests
import yfinance as yf
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "last_sent_state_preopen.json"
ENV_FILE = BASE_DIR / ".env"

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

RETRY_TIMES = 3
RETRY_SLEEP_SEC = 15

US_INDEX_MAP = {
    "道瓊": "^DJI",
    "那斯達克": "^IXIC",
    "S&P500": "^GSPC",
    "費城半導體": "^SOX",
}

USER_AGENT = {
    "User-Agent": "Mozilla/5.0"
}


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少環境變數：{name}")
    return value


def today_taipei_str() -> str:
    return datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d")


def is_weekday_taipei() -> bool:
    return datetime.now(TAIPEI_TZ).weekday() < 5


def already_sent(today_str: str) -> bool:
    if not STATE_FILE.exists():
        return False
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data.get("last_sent_date") == today_str
    except Exception:
        return False


def save_sent_state(today_str: str) -> None:
    payload = {
        "last_sent_date": today_str,
        "saved_at_taipei": datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    }
    STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_latest_two_rows(hist):
    if hist is None or hist.empty or len(hist) < 2:
        raise RuntimeError("歷史資料不足")
    latest = hist.iloc[-1]
    prev = hist.iloc[-2]
    latest_date = hist.index[-1].strftime("%Y-%m-%d")
    return latest, prev, latest_date


def fetch_us_index_data(symbol: str) -> dict:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="10d", auto_adjust=False)

    latest, prev, latest_date = get_latest_two_rows(hist)

    close_price = float(latest["Close"])
    prev_close = float(prev["Close"])
    high_price = float(latest["High"])
    low_price = float(latest["Low"])

    change = close_price - prev_close
    change_pct = (change / prev_close) * 100 if prev_close else 0.0
    amplitude = high_price - low_price
    amplitude_pct = (amplitude / prev_close) * 100 if prev_close else 0.0

    return {
        "source": "yfinance",
        "date": latest_date,
        "close": round(close_price, 2),
        "prev_close": round(prev_close, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "amplitude": round(amplitude, 2),
        "amplitude_pct": round(amplitude_pct, 2),
    }


def _to_float(text: str) -> float:
    return float(text.replace(",", "").replace("%", "").strip())


def fetch_asia_from_stooq(symbol: str, label: str) -> dict:
    url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
    r = requests.get(url, headers=USER_AGENT, timeout=20)
    r.raise_for_status()
    lines = [x.strip() for x in r.text.strip().splitlines() if x.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"{label} stooq 無資料")

    header = lines[0].split(",")
    row = lines[1].split(",")
    data = dict(zip(header, row))

    yf_symbol = "^N225" if "日經" in label else "^KS11"
    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period="10d", auto_adjust=False)
    if hist is None or hist.empty or len(hist) < 2:
        raise RuntimeError(f"{label} 前一日資料不足")

    prev_close = float(hist.iloc[-2]["Close"])
    close_price = _to_float(data["Close"])
    high_price = _to_float(data["High"])
    low_price = _to_float(data["Low"])
    latest_date = data["Date"]

    change = close_price - prev_close
    change_pct = (change / prev_close) * 100 if prev_close else 0.0
    amplitude = high_price - low_price
    amplitude_pct = (amplitude / prev_close) * 100 if prev_close else 0.0

    return {
        "source": "stooq",
        "date": latest_date,
        "close": round(close_price, 2),
        "prev_close": round(prev_close, 2),
        "high": round(high_price, 2),
        "low": round(low_price, 2),
        "change": round(change, 2),
        "change_pct": round(change_pct, 2),
        "amplitude": round(amplitude, 2),
        "amplitude_pct": round(amplitude_pct, 2),
    }


def fetch_asia_index_data() -> dict:
    data = {}
    data["日本日經225"] = fetch_asia_from_stooq("^nkx", "日本日經225")
    data["韓國KOSPI"] = fetch_asia_from_stooq("^kospi", "韓國KOSPI")
    return data


def build_decision(us_data: dict, asia_data: dict):
    score = 0
    score += 1 if us_data["道瓊"]["change_pct"] > 0 else -1
    score += 2 if us_data["那斯達克"]["change_pct"] > 0 else -2
    score += 2 if us_data["S&P500"]["change_pct"] > 0 else -2
    score += 3 if us_data["費城半導體"]["change_pct"] > 0 else -3
    score += 2 if asia_data["日本日經225"]["change_pct"] > 0 else -2
    score += 2 if asia_data["韓國KOSPI"]["change_pct"] > 0 else -2

    sox = us_data["費城半導體"]["change_pct"]
    nasdaq = us_data["那斯達克"]["change_pct"]
    nikkei = asia_data["日本日經225"]["change_pct"]
    kospi = asia_data["韓國KOSPI"]["change_pct"]

    if score >= 7:
        bias = "偏多"
        action = "美股與日韓同步偏強，台指傾向高盤開出，策略以拉回找多為主。"
    elif score >= 3:
        bias = "偏多震盪"
        action = "外圍偏正面，但不算全面強，多方有利，避免一開盤追價。"
    elif score <= -7:
        bias = "偏空"
        action = "美股與日韓同步轉弱，台指偏向壓力開盤，策略以反彈找空為主。"
    elif score <= -3:
        bias = "偏空震盪"
        action = "外圍偏弱但未全面崩，先看開盤反彈力道，弱則偏空操作。"
    else:
        bias = "震盪"
        action = "多空分歧，台指較可能區間震盪，等假突破或回測再動手。"

    extras = []
    if sox <= -1.5:
        extras.append("費半明顯走弱，電子權值承壓。")
    elif sox >= 1.5:
        extras.append("費半明顯走強，電子權值有助攻。")

    if nasdaq * sox > 0 and abs(nasdaq) > 1 and abs(sox) > 1:
        extras.append("科技股方向一致，開盤參考價值高。")

    if nikkei * kospi < 0:
        extras.append("日韓分歧，亞洲情緒不一致，追價宜保守。")

    if extras:
        action += " " + " ".join(extras)

    return bias, action


def format_signed(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}"


def get_emoji(value: float) -> str:
    if value > 0:
        return "🟥"
    elif value < 0:
        return "🟩"
    return "⬜"


def build_report(us_data: dict, asia_data: dict, bias: str, action: str) -> str:
    now_taipei = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")
    us_date = list(us_data.values())[0]["date"]
    asia_date = list(asia_data.values())[0]["date"]

    lines = [
        "📌 台股 08:10 盤前決策整理",
        f"發送時間：{now_taipei}",
        f"美股資料日：{us_date}",
        f"日韓資料日：{asia_date}",
        "--------------------------------",
        "【美股收盤】",
    ]

    for name in ["道瓊", "那斯達克", "S&P500", "費城半導體"]:
        item = us_data[name]
        emoji = get_emoji(item["change"])
        lines.append(f"{name}：{item['close']} {emoji} {format_signed(item['change'])} 點 ({format_signed(item['change_pct'])}%)")

    lines.extend(["", "【日韓早盤】"])

    for name in ["日本日經225", "韓國KOSPI"]:
        item = asia_data[name]
        emoji = get_emoji(item["change"])
        direction = "上漲" if item["change"] > 0 else ("下跌" if item["change"] < 0 else "平盤")
        lines.append(f"{name}：{item['close']} {emoji} {format_signed(item['change'])} 點 ({format_signed(item['change_pct'])}%) / {direction}")
        lines.append(f"高低：{item['high']} / {item['low']}；振幅：{item['amplitude']} 點（{item['amplitude_pct']}%）")

    bias_emoji = "🟥" if "偏多" in bias else ("🟩" if "偏空" in bias else "⬜")
    lines.extend(["", "【台指判斷】", f"方向：{bias_emoji} {bias}", f"策略：{action}"])
    return "\n".join(lines)


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, data=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram 發送失敗：{data}")


def main() -> int:
    try:
        load_env(ENV_FILE)
        token = get_required_env("TELEGRAM_BOT_TOKEN")
        chat_id = get_required_env("TELEGRAM_CHAT_ID")

        today_str = today_taipei_str()

        if not is_weekday_taipei():
            print("今天是台北時間週末，略過。")
            return 0

        if already_sent(today_str):
            print(f"{today_str} 已發送過，略過。")
            return 0

        us_data = {name: fetch_us_index_data(symbol) for name, symbol in US_INDEX_MAP.items()}
        asia_data = fetch_asia_index_data()

        bias, action = build_decision(us_data, asia_data)
        report = build_report(us_data, asia_data, bias, action)

        last_error = None
        for i in range(1, RETRY_TIMES + 1):
            try:
                send_telegram_message(token, chat_id, report)
                save_sent_state(today_str)
                print("Telegram 發送成功")
                return 0
            except Exception as e:
                last_error = e
                print(f"第 {i} 次發送失敗：{e}")
                if i < RETRY_TIMES:
                    time.sleep(RETRY_SLEEP_SEC)

        raise RuntimeError(f"重試 {RETRY_TIMES} 次後仍失敗：{last_error}")

    except Exception as e:
        print(f"程式執行失敗：{e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
