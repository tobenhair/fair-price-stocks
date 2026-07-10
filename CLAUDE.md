# CLAUDE.md — Buffett Portfolio Dashboard ("The Portfolio Ledger")

## What this project is

A single-file, Warren Buffett-inspired analytics dashboard for a Swedish (OMX Stockholm)
stock portfolio, plus a Python pipeline that refreshes it with live market data.
The owner uses it monthly to decide the best value purchase among 12 holdings and a
30-name watchlist covering the full OMXS30 index.

**Investment philosophy encoded here:** quality first (ROE, ROIC, margins, earnings
consistency, moat), price second (margin of safety vs. estimated fair value). Pre-profit
companies are honestly flagged "outside criteria" rather than scored.

## Files

| File | Role |
|---|---|
| `buffett_dashboard.html` | The entire app. Single file: CSS + HTML + vanilla JS. No build step, no frameworks, no external JS deps. Google Fonts only. |
| `portfolio_data.csv` | Source of truth for the 12 holdings (metrics, moat text, descriptions, DCF base case, 10y EPS history, `shares`). |
| `watchlist_data.csv` | 30 screened companies (24 OMXS30 constituents not held + 6 mid-caps). |
| `update_data.py` | Fetches live prices/PE/yield via yfinance and patches BOTH the CSVs and the JS arrays inside the HTML, in place. |

**Important:** the HTML does NOT read the CSVs at runtime (must work from `file://` and
in sandboxed viewers — no fetch, no localStorage). Data is duplicated in embedded JS
arrays (`DATA`, `WATCH`, `EXTRA`, `SHARES`). Any hand-edit to company data must be made
in BOTH the CSV and the HTML, or made only via `update_data.py`, which keeps them in sync
for price/pe/dy.

## The 12 holdings

Nordea (NDA-SE), Axfood (AXFO), TRATON (8TRA, EUR-listed), Investor (INVE-B), SCA (SCA-B),
Skanska (SKA-B), Sectra (SECT-B), Flat Capital (FLAT-B), Acconeer (ACCON), Midsummer (MIDS),
Ericsson (ERIC-B), AstraZeneca (AZN). Flat Capital, Acconeer and Midsummer are
`circle:false` (outside Buffett criteria) — keep it that way unless they become profitable.

## Architecture of buffett_dashboard.html

One `<style>` block, one `<script>` block. Sections in page order:

1. `#verdict` — top-3 monthly buy ranking (rank = 0.6·quality + 0.4·MoS, circle+moat≥2.5 only)
2. `#hold-sec` — My Holdings: editable share counts, allocation vs. conviction-weight bars,
   portfolio stats, 10 000 kr buy simulator, positions CSV export (data-URI download)
3. `#map-sec` — "Buffett Map" SVG scatter: quality (y) vs margin of safety (x), quadrants
4. `#sandbox-sec` — DCF sandbox: 3 sliders (growth, discount, terminal P/E), 5×5 sensitivity grid
5. `#buyzone-sec` — buy-below tracker: required-MoS slider, price-dot on zone track per holding
6. `#bars-sec` — single-metric comparison bars with metric `<select>`
7. `#table-sec` — sortable full-ledger table
8. `#income-sec` — dividend projector: reinvest vs cash toggle, 10y line chart + cumulative bars
9. `#watch-sec` — OMXS30 watchlist screener: sector chips, sort select, candidates-only toggle
10. `#cards-sec` — 12 company cards: description, products/customers, moat summary + tags,
    moat gauge (signature SVG element), 10y sparklines, 6-point Buffett checklist

JS layout: `DATA` array → `EXTRA` merge (hist/dcf/divG) → `SHARES` merge → derived scores
(IIFE per section, top to bottom) → `WATCH` + screener → motion engine (last IIFE).

### Derived metrics (computed in JS, don't store)

- `q` (quality 0–100): ROE 25p + ROIC 15p + net margin 10p + consistency 20p + moat 25p + debt 5p.
  Banks/invcos get fallbacks where ROIC/D-E don't apply.
- `mos` = (fv − px)/fv. `fv` is the ledger fair value from CSV; the sandbox computes its own.
- Watchlist: `qs` = ROE 40p + consistency 30p + moat 30p; candidate if `qs≥52 && (pe≤18 || dy≥4.5)`.

### Design system

- Palette (CSS vars): paper `#F2F3EF`, panel `#FBFBF8`, ink `#16211B`, green `#1C5A41`,
  deep `#0C2C21`, brass `#A47C2C`, red `#A2402C`. Ledger/annual-report aesthetic — keep it.
- Fonts: Spectral (display serif), IBM Plex Sans (body), IBM Plex Mono (all numbers).
- Signature element: the **moat gauge** — 5 concentric semicircle rings + castle keep,
  drawn per card, animated with `pathLength="100"` stroke-dash.
- Pills: `.pill.buy/.watch/.hold/.out` = green/brass/gray/red verdict language used everywhere.
- New sections follow the pattern: `<section id="x-sec"><div class="sec-head">…` + nav link
  + id added to the `secObs` array in the motion engine + `reveal` class on panels.

### Motion engine (bottom IIFE) — known gotchas

- **IntersectionObserver thresholds:** tall elements (card grid) NEVER reach a 15% threshold.
  Use `threshold: 0` with a negative `rootMargin`. This bug already bit once ("second half
  of page empty"). Don't regress it.
- Reduced motion: every animation has a `prefers-reduced-motion` override. Maintain when adding.
- No-IO fallback at top of motion engine reveals everything and returns.
- Bars animate via `--w` custom property + `.in` class; income/watchlist bars set inline
  `width:var(--w)!important` to bypass the animation gate.

### Hard constraints

- **No localStorage/sessionStorage** — breaks in sandboxed artifact viewers. Positions
  persist via CSV export + the `shares` column instead.
- No HTML `<form>` tags; plain event handlers.
- Keep it a single file. No bundlers, no npm deps for the frontend.

## update_data.py

- Yahoo maps: `PORTFOLIO_YAHOO` / `WATCHLIST_YAHOO` (mostly `TICKER.ST`).
  **TRATON is `8TRA.DE` in EUR** — converted with live `EURSEK=X`.
- `patch_html()` finds each ticker's JS object by locating `t:"TICK"` (NOT `{t:` — WATCH
  objects start with `n:`), bounded by the next `t:"` or `];`, then regex-replaces
  `px:` / `pe:` / `dy:` once each. If you rename those keys in the HTML, update this.
- CSVs: updates `price`, `pe`, `div_yield` where present; preserves `shares` and all text.
- Flags: `--dry-run`, `--mock file.json` (`{"TICK":{"price":..,"pe":..,"dy":..}}`) for
  offline testing. Failed fetches keep old values — never crash the dashboard.
- Also stamps the header "As of …" date.

## Testing (no browser needed)

Verified via jsdom with stubbed observers — reuse this harness after any change:

```js
const {JSDOM}=require('jsdom');
const dom=new JSDOM(fs.readFileSync('buffett_dashboard.html','utf8'),{runScripts:'outside-only',pretendToBeVisual:true});
const w=dom.window;
w.IntersectionObserver=class{constructor(cb){this.cb=cb}observe(el){this.cb([{isIntersecting:true,target:el}])}unobserve(){}};
w.matchMedia=()=>({matches:false});
w.eval([...w.document.querySelectorAll('script')].map(s=>s.textContent).join(';'));
// then assert: #cards .card ==12, #wRows .w-row ==30, #hRows .h-row ==12, etc.
```

Pipeline test: copy files to a temp dir, run `python3 update_data.py --mock m.json`,
grep the HTML for patched values, re-run the jsdom harness on the patched file.

## Data honesty rules (do not break)

- All fundamentals are currently **illustrative estimates** — the header and methodology
  footer say so. Only prices/pe/dy become real after running the pipeline. If adding
  real reported fundamentals, remove the caveats where they no longer apply.
- Fair values are simple anchors (owner-earnings DCF, NAV discount, cyclically adjusted
  multiples) — method named per company in `fair_value_method`. Never present them as predictions.
- Not investment advice; keep the disclaimer in the methodology footer.

## Backlog (agreed ideas, not yet built)

1. Decision journal — log each buy with score + rationale at time of purchase (needs a
   persistence strategy; consider a JSON file the Python script round-trips).
2. Sell-discipline / thesis tracker — 2–3 "must stay true" facts per holding with red flags.
3. Risk lens — currency exposure (AZN, TRATON, AstraZeneca are non-SEK earners), sector
   concentration, cyclicality tags.
4. Monthly snapshot history — pipeline appends a dated scores/verdicts row for trend view.
5. Börsdata API integration for real Nordic fundamentals (yfinance fundamentals are flaky
   for .ST tickers) — key goes in env var, never committed.
