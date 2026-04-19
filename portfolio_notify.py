import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
SHEET_ID = "1DtrlL1XfcPpxo7WLdZLkFJgKfJrnWliozeUD5gjF0Rc"
GID = "1915868845"

TRY_USD = 44.8  # fallback, asıl değer TCMB'den çekilir


def get_usd_try():
    try:
        r = requests.get(
            "https://api.exchangerate-api.com/v4/latest/USD", timeout=5
        )
        data = r.json()
        return data["rates"]["TRY"]
    except Exception:
        return TRY_USD


def get_portfolio():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    lines = r.text.strip().split("\n")

    header = [h.strip() for h in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        ticker = parts[0].strip().strip('"')
        if ticker in ("TOPLAM", "-*", ""):
            continue
        # Market Değeri TL = index 7
        try:
            val_tl = parts[7].strip().strip('"').replace("TRY", "").replace(".", "").replace("\xa0", "").strip()
            val_tl = float(val_tl.replace(",", ".")) if val_tl else 0
        except Exception:
            val_tl = 0
        # Kar% = index 9
        try:
            karpct = parts[9].strip().strip('"').replace("%", "").replace("\xa0", "").strip()
            karpct = float(karpct.replace(",", ".")) if karpct else 0
        except Exception:
            karpct = 0
        # Upside = index 10
        try:
            upside = parts[10].strip().strip('"').replace("%", "").replace("\xa0", "").strip()
            upside = float(upside.replace(",", ".")) if upside else 0
        except Exception:
            upside = 0
        # Sektör = index 14
        try:
            sektor = parts[14].strip().strip('"') if len(parts) > 14 else ""
        except Exception:
            sektor = ""

        rows.append({
            "ticker": ticker,
            "val_tl": val_tl,
            "kar_pct": karpct,
            "upside": upside,
            "sektor": sektor,
        })
    return rows


def build_message(rows, usd_try):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    toplam = sum(r["val_tl"] for r in rows)

    hisse = [r for r in rows if r["sektor"] not in ("Kripto", "")]
    kripto = [r for r in rows if r["sektor"] == "Kripto"]

    toplam_hisse = sum(r["val_tl"] for r in hisse)
    toplam_kripto = sum(r["val_tl"] for r in kripto)

    # En iyi ve en kötü 3 pozisyon
    sorted_rows = sorted(rows, key=lambda x: x["kar_pct"], reverse=True)
    en_iyi = sorted_rows[:3]
    en_kotu = sorted_rows[-3:]

    msg = f"""📊 *PORTFOLYO RAPORU*
🕘 {now} | 💱 1 USD = {usd_try:.1f} TRY

━━━━━━━━━━━━━━━━
💼 *TOPLAM DEĞER*
`{toplam:,.0f} TRY`

🏦 Hisse:  `{toplam_hisse:,.0f} TRY` (%{100*toplam_hisse/toplam:.1f})
🪙 Kripto: `{toplam_kripto:,.0f} TRY` (%{100*toplam_kripto/toplam:.1f})

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

    msg += "\n━━━━━━━━━━━━━━━━\n"
    msg += "📌 *HEDEF FİYAT DURUMU* (Upside > %50)\n"
    yuksek_upside = [r for r in rows if r["upside"] > 50]
    if yuksek_upside:
        for r in sorted(yuksek_upside, key=lambda x: x["upside"], reverse=True):
            msg += f"⭐ {r['ticker']}: %{r['upside']:.1f} potansiyel\n"
    else:
        msg += "Yok\n"

    return msg


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    usd_try = get_usd_try()
    rows = get_portfolio()
    message = build_message(rows, usd_try)
    send_telegram(message)
    print("Bildirim gönderildi.")


if __name__ == "__main__":
    main()
