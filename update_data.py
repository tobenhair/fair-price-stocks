#!/usr/bin/env python3
"""
update_data.py — refresh the Buffett dashboard with live market data.

Fetches latest prices (and, best-effort, trailing P/E and dividend yield)
from Yahoo Finance via yfinance, then updates:
  1. portfolio_data.csv   (price, pe, div_yield columns)
  2. watchlist_data.csv   (pe, div_yield columns; price not stored there)
  3. buffett_dashboard.html (the embedded DATA and WATCH arrays: px, pe, dy)

Usage:
  pip install yfinance
  python update_data.py                 # fetch live and update everything
  python update_data.py --dry-run      # fetch and show changes, write nothing
  python update_data.py --mock FILE    # use a JSON {ticker: price} instead of the network (for testing)

Notes:
  - TRATON (8TRA) trades in EUR on Xetra; the script converts to SEK using EURSEK=X.
  - If a field can't be fetched, the existing value is kept — the dashboard never breaks.
  - Your `shares` column in portfolio_data.csv is preserved untouched.
"""
import argparse, csv, json, re, sys
from pathlib import Path

# ---- ticker mapping: dashboard ticker -> Yahoo symbol -------------------
PORTFOLIO_YAHOO = {
    "NDA-SE": "NDA-SE.ST", "AXFO": "AXFO.ST", "8TRA": "8TRA.DE",  # EUR!
    "INVE-B": "INVE-B.ST", "SCA-B": "SCA-B.ST", "SKA-B": "SKA-B.ST",
    "SECT-B": "SECT-B.ST", "FLAT-B": "FLAT-B.ST", "ACCON": "ACCON.ST",
    "MIDS": "MIDS.ST", "ERIC-B": "ERIC-B.ST", "AZN": "AZN.ST",
}
WATCHLIST_YAHOO = {
    "ATCO-A": "ATCO-A.ST", "EPI-A": "EPI-A.ST", "SAND": "SAND.ST",
    "VOLV-B": "VOLV-B.ST", "ASSA-B": "ASSA-B.ST", "ALFA": "ALFA.ST",
    "HEXA-B": "HEXA-B.ST", "EVO": "EVO.ST", "HEM": "HEM.ST", "AZA": "AZA.ST",
    "SWED-A": "SWED-A.ST", "SHB-A": "SHB-A.ST", "SEB-A": "SEB-A.ST",
    "EQT": "EQT.ST", "HM-B": "HM-B.ST", "ESSITY-B": "ESSITY-B.ST",
    "AAK": "AAK.ST", "THULE": "THULE.ST", "TELIA": "TELIA.ST",
    "TEL2-B": "TEL2-B.ST", "SAAB-B": "SAAB-B.ST", "BOL": "BOL.ST",
    "HOLM-B": "HOLM-B.ST", "SECU-B": "SECU-B.ST",
    "ABB": "ABB.ST", "ADDT-B": "ADDT-B.ST", "INDU-C": "INDU-C.ST",
    "LIFCO-B": "LIFCO-B.ST", "NIBE-B": "NIBE-B.ST", "SKF-B": "SKF-B.ST",
}
EUR_TICKERS = {"8TRA"}

HERE = Path(__file__).parent
PORTFOLIO_CSV = HERE / "portfolio_data.csv"
WATCHLIST_CSV = HERE / "watchlist_data.csv"
DASHBOARD_HTML = HERE / "buffett_dashboard.html"


def fetch_live(tickers_yahoo):
    """Return {dashboard_ticker: {"price":..,"pe":..,"dy":..}} from Yahoo."""
    import yfinance as yf  # imported here so --mock works without it
    out = {}
    eursek = None
    if any(t in EUR_TICKERS for t in tickers_yahoo):
        try:
            eursek = yf.Ticker("EURSEK=X").fast_info["last_price"]
            print(f"  EUR/SEK = {eursek:.3f}")
        except Exception as e:
            print(f"  ! EURSEK fetch failed ({e}); EUR tickers will be skipped")
    for tick, ysym in tickers_yahoo.items():
        try:
            t = yf.Ticker(ysym)
            px = t.fast_info["last_price"]
            if tick in EUR_TICKERS:
                if not eursek:
                    print(f"  ! {tick}: skipped (no FX rate)")
                    continue
                px *= eursek
            rec = {"price": round(float(px), 2)}
            # best-effort fundamentals (info is slow/flaky — never fatal)
            try:
                info = t.info
                if info.get("trailingPE"):
                    rec["pe"] = round(float(info["trailingPE"]), 1)
                if info.get("dividendYield"):
                    y = float(info["dividendYield"])
                    rec["dy"] = round(y * 100 if y < 1 else y, 1)
            except Exception:
                pass
            out[tick] = rec
            print(f"  {tick:9s} -> {rec}")
        except Exception as e:
            print(f"  ! {tick}: fetch failed ({e}); keeping old values")
    return out


def update_csv(path, data, price_col, pe_col, dy_col):
    rows = list(csv.reader(path.open(encoding="utf-8")))
    head = rows[0]
    idx = {c: head.index(c) for c in head}
    changed = 0
    for r in rows[1:]:
        rec = data.get(r[idx["ticker"]])
        if not rec:
            continue
        touched = False
        if price_col and "price" in rec and price_col in idx:
            r[idx[price_col]] = str(rec["price"]); touched = True
        if "pe" in rec and pe_col in idx and r[idx[pe_col]] != "":
            r[idx[pe_col]] = str(rec["pe"]); touched = True
        if "dy" in rec and dy_col in idx and r[idx[dy_col]] != "":
            r[idx[dy_col]] = str(rec["dy"]); touched = True
        changed += touched
    return rows, changed


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def patch_html(html, data, array_name):
    """Patch px/pe/dy inside the JS object literal for each ticker in DATA or WATCH."""
    changed = 0
    for tick, rec in data.items():
        # locate this ticker's object: from its t:"TICK" key to the next t:" key
        start = html.find(f't:"{tick}"')
        if start == -1:
            continue
        ends = [i for i in (html.find('t:"', start + 4), html.find("];", start)) if i != -1]
        end = min(ends) if ends else len(html)
        chunk = html[start:end]
        orig = chunk
        if "price" in rec:
            chunk = re.sub(r"px:\s*[\d.]+", f"px:{rec['price']}", chunk, count=1)
        if "pe" in rec:
            chunk = re.sub(r"\bpe:\s*[\d.]+", f"pe:{rec['pe']}", chunk, count=1)
        if "dy" in rec:
            chunk = re.sub(r"\bdy:\s*[\d.]+", f"dy:{rec['dy']}", chunk, count=1)
        if chunk != orig:
            html = html[:start] + chunk + html[end:]
            changed += 1
    return html, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--mock", help="JSON file {ticker:{price,pe,dy}} instead of live fetch")
    args = ap.parse_args()

    if args.mock:
        raw = json.loads(Path(args.mock).read_text())
        live = {k: (v if isinstance(v, dict) else {"price": v}) for k, v in raw.items()}
        print(f"Mock data: {len(live)} tickers")
    else:
        print("Fetching portfolio prices…")
        live = fetch_live(PORTFOLIO_YAHOO)
        print("Fetching watchlist prices…")
        live.update(fetch_live(WATCHLIST_YAHOO))

    if not live:
        sys.exit("No data fetched — nothing to update.")

    # CSVs
    p_rows, p_ch = update_csv(PORTFOLIO_CSV, live, "price", "pe", "div_yield")
    w_rows, w_ch = update_csv(WATCHLIST_CSV, live, None, "pe", "div_yield")
    # HTML
    html = DASHBOARD_HTML.read_text(encoding="utf-8")
    html, h1 = patch_html(html, live, "const DATA")
    html, h2 = patch_html(html, live, "const WATCH")
    # stamp the as-of date in the header
    from datetime import date
    html = re.sub(r"As of <b>[^<]*</b>",
                  f"As of <b>{date.today():%d %b %Y} (live via yfinance)</b>", html, count=1)

    print(f"\nportfolio_data.csv: {p_ch} prices updated")
    print(f"watchlist_data.csv: {w_ch} rows touched")
    print(f"dashboard HTML:     {h1 + h2} companies patched")

    if args.dry_run:
        print("Dry run — nothing written.")
        return
    write_csv(PORTFOLIO_CSV, p_rows)
    write_csv(WATCHLIST_CSV, w_rows)
    DASHBOARD_HTML.write_text(html, encoding="utf-8")
    print("Done. Open buffett_dashboard.html — every score, verdict and buy zone now uses live prices.")


if __name__ == "__main__":
    main()
