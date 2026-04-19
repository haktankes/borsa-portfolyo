import requests
import os
import csv
import io
import re
import json
from datetime import datetime

LAST_VALUE_FILE = "last_value.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
SHEET_ID = "1DtrlL1XfcPpxo7WLdZLkFJgKfJrnWliozeUD5gjF0Rc"
GID = "1915868845"

# Sütun indeksleri (debug logdan doğrulandı)
COL_VAL_TL  = 7   # Market Değeri TL
COL_KAR_PCT = 9   # Kar%
COL_UPSIDE  = 10  # Upside
COL_SEKTOR  = 14  # Sektör

VALID_TICKER = re.compile(r'^[A-Z0-9]{2,10}$')
SKIP_TICKERS = {"TOPLAM"}


def get_usd_try():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        return r.json()["rates"]["TRY"]
    except Exception:
        return 44.8


def parse_number(s):
    """TR formatı: '67.284 TRY' → 67284.0 | '118,5%' → 118.5 | '-19,1%' → -19.1"""
    s = str(s).strip().strip('"').replace("TRY", "").replace("$", "").replace("%", "")
    s = s.replace("\xa0", "").replace("\u202f", "").replace("\u00a0", "").strip()
    if not s or s == "-":
        return 0.0
    negative = s.startswith("-")
    s = s.lstrip("-").strip()
    if "," in s and "." in s:
        # 1.881,3 → virgül ondalık, nokta binlik
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        # 118,5 → virgül ondalık
        s = s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            # 67.284 → binlik ayraç
            s = s.replace(".", "")
        # else: gerçek ondalık (0.2 gibi), bırak
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return 0.0


def get_portfolio():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
    r = requests.get(url, timeout=15, allow_redirects=True)
    r.raise_for_status()
    content = r.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))

    rows = []
    for i, row in enumerate(reader):
        if i == 0:
            continue  # header satırını atla
        if not row or not row[0].strip():
            continue
        ticker = row[0].strip().strip('"')
        if ticker in SKIP_TICKERS or not VALID_TICKER.match(ticker):
            continue
        if len(row) <= COL_SEKTOR:
            continue

        val_tl  = parse_number(row[COL_VAL_TL])
        kar_pct = parse_number(row[COL_KAR_PCT])
        upside  = parse_number(row[COL_UPSIDE])
        sektor  = row[COL_SEKTOR].strip()

        rows.append({"ticker": ticker, "val_tl": val_tl, "kar_pct": kar_pct,
                     "upside": upside, "sektor": sektor})

    return rows


def load_last_value():
    try:
        with open(LAST_VALUE_FILE, "r") as f:
            return json.load(f).get("toplam", None)
    except Exception:
        return None


def save_last_value(toplam):
    with open(LAST_VALUE_FILE, "w") as f:
        json.dump({"toplam": toplam, "tarih": datetime.now().strftime("%Y-%m-%d")}, f)


def build_message(rows, usd_try, dun_toplam=None):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    valid = [r for r in rows if r["val_tl"] > 5]
    toplam = sum(r["val_tl"] for r in valid)

    hisse = [r for r in valid if r["sektor"] != "Kripto"]
    kripto = [r for r in valid if r["sektor"] == "Kripto"]
    toplam_hisse  = sum(r["val_tl"] for r in hisse)
    toplam_kripto = sum(r["val_tl"] for r in kripto)
    pct_h = 100 * toplam_hisse  / toplam if toplam else 0
    pct_k = 100 * toplam_kripto / toplam if toplam else 0

    sorted_hisse = sorted(hisse, key=lambda x: x["kar_pct"], reverse=True)
    en_iyi  = sorted_hisse[:3]
    en_kotu = sorted_hisse[-3:]

    if dun_toplam and dun_toplam > 0:
        fark = toplam - dun_toplam
        fark_pct = 100 * fark / dun_toplam
        fark_emoji = "🟢" if fark >= 0 else "🔴"
        gunluk_str = f"\n{fark_emoji} Günlük: `{fark:+,.0f} TRY` (%{fark_pct:+.2f})"
    else:
        gunluk_str = ""

    msg = f"""📊 *PORTFOLYO RAPORU*
🕘 {now} | 💱 1 USD = {usd_try:.1f} TRY

━━━━━━━━━━━━━━━━
💼 *TOPLAM DEĞER*
`{toplam:,.0f} TRY`{gunluk_str}

🏦 Hisse:  `{toplam_hisse:,.0f} TRY` (%{pct_h:.1f})
🪙 Kripto: `{toplam_kripto:,.0f} TRY` (%{pct_k:.1f})

━━━━━━━━━━━━━━━━
🚀 *EN İYİ 3 POZİSYON*
"""
    for r in en_iyi:
        emoji = "🟢" if r["kar_pct"] >= 0 else "🔴"
        msg += f"{emoji} {r['ticker']}: %{r['kar_pct']:+.1f} kar | ⬆ %{r['upside']:.1f} upside\n"

    msg += "\n📉 *EN KÖTÜ 3 POZİSYON*\n"
    for r in en_kotu:
        emoji = "🟢" if r["kar_pct"] >= 0 else "🔴"
        msg += f"{emoji} {r['ticker']}: %{r['kar_pct']:+.1f} kar | ⬆ %{r['upside']:.1f} upside\n"

    return msg


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    r.raise_for_status()


def main():
    usd_try = get_usd_try()
    rows = get_portfolio()
    dun_toplam = load_last_value()
    message = build_message(rows, usd_try, dun_toplam)
    valid = [r for r in rows if r["val_tl"] > 5]
    toplam = sum(r["val_tl"] for r in valid)
    save_last_value(toplam)
    print(message)
    send_telegram(message)
    print("Bildirim gönderildi.")


if __name__ == "__main__":
    main()
