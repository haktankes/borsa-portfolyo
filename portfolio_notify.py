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


def fetch_csv():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"
    r = requests.get(url, timeout=15, allow_redirects=True)
    r.raise_for_status()
    return r.content.decode("utf-8-sig")


def parse_number(s):
    """TR formatı: '30.794 TRY' → 30794.0 | '118,5%' → 118.5 | '-19,1%' → -19.1"""
    s = str(s).strip().strip('"').strip()
    for sym in ["TRY", "$", "%", "\xa0", "\u202f", "\u00a0"]:
        s = s.replace(sym, "")
    s = s.strip()
    if not s or s in ("-", ""):
        return 0.0
    negative = s.startswith("-")
    s = s.lstrip("-").strip()
    # Nokta = binlik ayraç, virgül = ondalık
    if "," in s and "." in s:
        # Örnek: 1.881,3 → 1881.3
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        # Sadece nokta varsa: 30.794 → binlik → 30794
        # Ama 0.2 gibi ondalık da olabilir
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) != 3:
            pass  # gerçek ondalık, bırak
        else:
            s = s.replace(".", "")  # binlik ayraç
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return 0.0


def get_portfolio():
    content = fetch_csv()
    reader = csv.reader(io.StringIO(content))
    all_rows = list(reader)

    print(f"=== CSV TOPLAM SATIR: {len(all_rows)} ===")
    for i, row in enumerate(all_rows):
        print(f"ROW {i}: {row}")

    # Header satırını bul (Market Değeri TL içeren)
    header_idx = None
    col_map = {}
    for i, row in enumerate(all_rows):
        joined = ",".join(row)
        if "Market Değeri TL" in joined or "Market De" in joined:
            header_idx = i
            for j, h in enumerate(row):
                col_map[h.strip()] = j
            break

    print(f"Header index: {header_idx}")
    print(f"Col map: {col_map}")

    if header_idx is None:
        print("HATA: Header bulunamadı!")
        return []

    # Sütun indekslerini bul
    idx_val_tl = None
    idx_kar_pct = None
    idx_upside = None
    idx_sektor = None

    for key, idx in col_map.items():
        k = key.strip()
        if k == "Market Değeri TL":
            idx_val_tl = idx
        elif k == "Kar%":
            idx_kar_pct = idx
        elif k == "Upside":
            idx_upside = idx
        elif k == "Sektör":
            idx_sektor = idx

    print(f"val_tl col: {idx_val_tl}, kar_pct col: {idx_kar_pct}, upside col: {idx_upside}, sektor col: {idx_sektor}")

    skip_tickers = {"TOPLAM", "", "-*", "-"}
    rows = []
    for row in all_rows[header_idx + 1:]:
        if not row or not row[0].strip():
            continue
        ticker = row[0].strip().strip('"')
        if ticker in skip_tickers:
            continue
        if not ticker.replace(" ", "").isalnum():
            continue

        try:
            val_tl  = parse_number(row[idx_val_tl])  if idx_val_tl  is not None and len(row) > idx_val_tl  else 0
            kar_pct = parse_number(row[idx_kar_pct]) if idx_kar_pct is not None and len(row) > idx_kar_pct else 0
            upside  = parse_number(row[idx_upside])  if idx_upside  is not None and len(row) > idx_upside  else 0
            sektor  = row[idx_sektor].strip()         if idx_sektor  is not None and len(row) > idx_sektor  else ""
        except Exception as e:
            print(f"Parse hatası {ticker}: {e}")
            continue

        print(f"  {ticker}: val_tl={val_tl}, kar={kar_pct}, upside={upside}, sektor={sektor}")
        rows.append({"ticker": ticker, "val_tl": val_tl, "kar_pct": kar_pct, "upside": upside, "sektor": sektor})

    return rows


def build_message(rows, usd_try):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    valid = [r for r in rows if r["val_tl"] > 10]
    toplam = sum(r["val_tl"] for r in valid)

    hisse = [r for r in valid if r["sektor"] != "Kripto"]
    kripto = [r for r in valid if r["sektor"] == "Kripto"]
    toplam_hisse = sum(r["val_tl"] for r in hisse)
    toplam_kripto = sum(r["val_tl"] for r in kripto)

    sorted_valid = sorted(valid, key=lambda x: x["kar_pct"], reverse=True)
    en_iyi = sorted_valid[:3]
    en_kotu = sorted_valid[-3:]

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

    yuksek = [r for r in valid if r["upside"] > 50]
    msg += "\n━━━━━━━━━━━━━━━━\n"
    msg += "📌 *HEDEF FİYAT DURUMU* (Upside > %50)\n"
    if yuksek:
        for r in sorted(yuksek, key=lambda x: x["upside"], reverse=True):
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
    message = build_message(rows, usd_try)
    send_telegram(message)
    print("Bildirim gönderildi.")


if __name__ == "__main__":
    main()
