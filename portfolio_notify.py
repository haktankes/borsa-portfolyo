import requests
import os
import csv
import io
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
SHEET_ID = "1DtrlL1XfcPpxo7WLdZLkFJgKfJrnWliozeUD5gjF0Rc"
GID = "1915868845"


def get_usd_try():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        return r.json()["rates"]["TRY"]
    except Exception:
        return 44.8


def parse_number(s):
    """Türk formatındaki sayıyı float'a çevirir: '30.794 TRY' → 30794.0, '118,5%' → 118.5"""
    s = str(s).strip().strip('"')
    for sym in ["TRY", "$", "%", "\xa0", " "]:
        s = s.replace(sym, "")
    s = s.strip()
    if not s or s == "-":
        return 0.0
    # Nokta binlik ayraç, virgül ondalık ayraç (TR formatı)
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def get_portfolio():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()

    content = r.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(content))

    rows = []
    header = None
    for row in reader:
        if not row or not row[0].strip():
            continue

        ticker = row[0].strip().strip('"')

        # Header satırını bul
        if ticker in ("-*",) or "Güncel" in row[1] if len(row) > 1 else False:
            header = row
            continue

        # Sadece geçerli ticker satırlarını al
        if ticker in ("TOPLAM", "") or len(row) < 10:
            continue

        # Sütun sırası: 0=ticker, 1=alış, 2=güncel, 3=lot, 4=ağırlık,
        # 5=yatırım maliyeti, 6=market değeri, 7=market değeri TL,
        # 8=kar, 9=kar%, 10=upside, 14=sektör, 15=tür
        try:
            val_tl  = parse_number(row[7]) if len(row) > 7 else 0
            kar_pct = parse_number(row[9]) if len(row) > 9 else 0
            upside  = parse_number(row[10]) if len(row) > 10 else 0
            sektor  = row[14].strip() if len(row) > 14 else ""
            tur     = row[15].strip() if len(row) > 15 else ""
        except Exception:
            continue

        rows.append({
            "ticker": ticker,
            "val_tl": val_tl,
            "kar_pct": kar_pct,
            "upside": upside,
            "sektor": sektor,
            "tur": tur,
        })

    return rows


def build_message(rows, usd_try):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    toplam = sum(r["val_tl"] for r in rows)

    hisse = [r for r in rows if r["sektor"] != "Kripto"]
    kripto = [r for r in rows if r["sektor"] == "Kripto"]
    toplam_hisse = sum(r["val_tl"] for r in hisse)
    toplam_kripto = sum(r["val_tl"] for r in kripto)

    sorted_rows = sorted([r for r in rows if r["val_tl"] > 0], key=lambda x: x["kar_pct"], reverse=True)
    en_iyi = sorted_rows[:3]
    en_kotu = sorted_rows[-3:]

    pct_h = 100 * toplam_hisse / toplam if toplam else 0
    pct_k = 100 * toplam_kripto / toplam if toplam else 0

    msg = f"""📊 *PORTFOLYO RAPORU*
🕘 {now} | 💱 1 USD = {usd_try:.1f} TRY

━━━━━━━━━━━━━━━━
💼 *TOPLAM DEĞER*
`{toplam:,.0f} TRY`

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

    yuksek_upside = [r for r in rows if r["upside"] > 50 and r["val_tl"] > 0]
    msg += "\n━━━━━━━━━━━━━━━━\n"
    msg += "📌 *HEDEF FİYAT DURUMU* (Upside > %50)\n"
    if yuksek_upside:
        for r in sorted(yuksek_upside, key=lambda x: x["upside"], reverse=True):
            msg += f"⭐ {r['ticker']}: %{r['upside']:.1f} potansiyel\n"
    else:
        msg += "Yok\n"

    return msg


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}, timeout=10)
    r.raise_for_status()


def main():
    usd_try = get_usd_try()
    rows = get_portfolio()
    print(f"Parse edilen satır sayısı: {len(rows)}")
    for r in rows:
        print(r)
    message = build_message(rows, usd_try)
    send_telegram(message)
    print("Bildirim gönderildi.")


if __name__ == "__main__":
    main()
