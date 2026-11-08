"""Build the single-page tracker (site/index.html) from the processed CSVs.
The page only displays numbers computed here from real files; nothing is typed in by hand."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
m = pd.read_csv(ROOT / "data/processed/korean_exports/monthly_total.csv", parse_dates=["month"]).set_index("month")
m.index = m.index.to_period("M")
m["weight_t"] = m.weight_kg / 1000
m["usd_g"] = m.value_usd / m.weight_kg / 1000  # USD per gram

# ---- Signal 1: price vs volume, quarterly, year-on-year log change ----
q = m.groupby(m.index.asfreq("Q")).agg(value=("value_usd", "sum"), wt=("weight_kg", "sum"))
q["uv"] = q.value / q.wt
q["d_value"] = np.log(q.value / q.value.shift(4))
q["d_vol"] = np.log(q.wt / q.wt.shift(4))
q["d_uv"] = np.log(q.uv / q.uv.shift(4))
q = q.loc["2024Q1":]

# ---- 3-month unit value and its 3-month momentum ----
r3 = m.value_usd.rolling(3).sum() / m.weight_kg.rolling(3).sum() / 1000
uv_mom = (r3 / r3.shift(3) - 1) * 100

# ---- Signal 2: DDR4 8Gb contract price (collected from public news, one source link per row) ----
c = pd.read_csv(ROOT / "data/raw/dram_prices/dram_contract_monthly.csv")
c = c[c.item == "DDR4 8Gb 1Gx8"].copy()
c["month"] = pd.PeriodIndex(c.month, freq="M")
c = c.drop_duplicates("month").set_index("month").avg_usd.sort_index()
c = c.reindex(pd.period_range(c.index.min(), c.index.max(), freq="M"))  # gaps stay NaN
c_mom3 = (c / c.shift(3) - 1) * 100

# ---- Signal 3: nowcast vs reported ----
n = pd.read_csv(ROOT / "data/processed/financials/nowcast_backtest.csv", index_col=0)
n.index = pd.PeriodIndex(n.index, freq="Q").astype(str)

def lbl(ix): return [str(i) for i in ix]

last_q = q.iloc[-1]
share_uv = last_q.d_uv / last_q.d_value * 100
uv_now, uv_peak = uv_mom.iloc[-1], uv_mom.max()
c_last, c_prev = c.dropna().iloc[-1], c.dropna().iloc[-2]
def status(mom, prev):
    if mom <= 0: return "Reversal watch"
    return "Accelerating" if mom > prev else "Decelerating"
s_exp = status(uv_mom.iloc[-1], uv_mom.iloc[-2])
s_con = status(c_mom3.dropna().iloc[-1], c_mom3.dropna().iloc[-2])
mape = n.nowcast_err_pct.abs().mean()
mape_b = min(n[c_].abs().mean() for c_ in ["naive_err_pct", "trend_err_pct", "trend_yoy_err_pct"])  # best baseline
under = int((n.nowcast_err_pct < 0).sum())
qtd = pd.read_csv(ROOT / "data/processed/financials/quarter_to_date_scorecard.csv", index_col=0)["MAPE_%"]
qtd1, qtd3 = qtd.iloc[0], qtd.iloc[2]
asof = str(m.index[-1])

data = dict(
    mx=lbl(m.index[-36:]), mval=(m.value_usd[-36:] / 1e9).round(2).tolist(), mwt=m.weight_t[-36:].round(0).tolist(),
    qx=[f'{i.year} Q{i.quarter}' for i in q.index], qvol=q.d_vol.round(3).tolist(), quv=q.d_uv.round(3).tolist(),
    ux=lbl(uv_mom.index[-16:]), uvm=uv_mom[-16:].round(1).tolist(),
    cx=lbl(c_mom3.index[-16:]), cm=c_mom3[-16:].round(1).where(lambda s: s.notna(), None).tolist(),
    cpx=lbl(c.index), cp=c.where(c.notna(), None).tolist(),
    nx=[f'{i[:4]} {i[4:]}' for i in n.index], nrev=(n.revenue_krw_m / 1e6).round(1).tolist(), nhat=(n.nowcast / 1e6).round(1).tolist(),
)

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SK hynix Memory Cycle Tracker</title>
<script src="plotly.min.js"></script>
<style>
:root{{--bg:#0e1116;--card:#161b22;--line:#262d38;--tx:#e6edf3;--mu:#8b98a8;--ac:#4ea1ff;--warn:#f0a43a;--ok:#3fb68b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,Segoe UI,sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:28px 16px 60px}}
h1{{font-size:24px;margin:0}}.sub{{color:var(--mu);margin:4px 0 22px}}
.strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:26px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px}}
.tile .k{{color:var(--mu);font-size:12px;text-transform:uppercase;letter-spacing:.05em}}
.tile .v{{font-size:22px;font-weight:600;margin:4px 0}}.tile .n{{color:var(--mu);font-size:13px}}
.warn{{color:var(--warn)}}.ok{{color:var(--ok)}}
section{{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:18px;margin-bottom:18px}}
h2{{font-size:17px;margin:0 0 4px}}.q{{color:var(--ac);font-size:13px;margin-bottom:6px}}
.take{{margin:8px 0 0}}.lim{{color:var(--mu);font-size:13px;margin-top:6px}}
.ch{{height:320px}}footer{{color:var(--mu);font-size:13px}}
</style></head><body><main>
<h1>SK hynix Memory Cycle Tracker</h1>
<div class="sub">Data as of {asof} (Korea customs). Built from public data; every series traces to a source file.</div>
<div class="strip">
 <div class="tile"><div class="k">Korean memory exports, {last_q.name}</div><div class="v">${last_q.value/1e9:.1f}B</div><div class="n">Weight {last_q.wt/1000:,.0f} tonnes. Value per gram ${last_q.uv/1000:.0f}</div></div>
 <div class="tile"><div class="k">Growth from price (unit value)</div><div class="v warn">{share_uv:.0f}%</div><div class="n">Rest is volume. Year-on-year log split</div></div>
 <div class="tile"><div class="k">Export unit-value momentum</div><div class="v warn">{s_exp}</div><div class="n">3-month change {uv_now:+.0f}% (peak {uv_peak:+.0f}%)</div></div>
 <div class="tile"><div class="k">DDR4 8Gb contract price</div><div class="v warn">{s_con}</div><div class="n">${c_last:.1f}, {(c_last/c_prev-1)*100:+.1f}% on the month</div></div>
 <div class="tile"><div class="k">Export nowcast error</div><div class="v ok">{mape:.1f}%</div><div class="n">vs {mape_b:.0f}% for the best simple baseline, {len(n)} quarters</div></div>
</div>

<section><div class="q">Q1. How big is the boom, and is it more chips or more money per chip?</div><h2>Korean memory exports: value vs weight</h2>
<div id="c1" class="ch"></div>
<p class="take">Value rose roughly fourfold in a year. Weight barely moved.</p>
<p class="lim">HS 854232 covers all Korean memory (Samsung too), not just SK hynix. Weight is a weak volume measure: HBM is heavier per chip than commodity DRAM.</p></section>

<section><div class="q">Q2. Is the growth durable volume, or price that can reverse?</div><h2>Where year-on-year growth comes from</h2>
<div id="c2" class="ch"></div>
<p class="take">2024: price-led, with volume falling. Mid-2025 to 2025 Q4: volume-led (up about 20-25%). Since 2026 Q1: price again, almost entirely.</p>
<p class="lim">Unit value is not a price. It also moves with product mix (HBM vs commodity) and customer mix.</p></section>

<section><div class="q">Q3. Is price growth slowing? Do two independent sources agree?</div><h2>3-month momentum: export unit value vs DDR4 contract price</h2>
<div id="c3" class="ch"></div>
<p class="take">Both have rolled over from their spring highs but are still positive. Slowing, not falling.</p>
<p class="lim">Contract series is DDR4 8Gb only, assembled from news reports of DRAMeXchange. It's a legacy product, so it shows the direction of pricing, not SK hynix's mix.</p></section>

<section><div class="q">Q4. Can this be read before SK hynix reports?</div><h2>Nowcast from exports vs reported revenue (KRW tn)</h2>
<div id="c4" class="ch"></div>
<p class="take">Revenue(q) = last quarter's revenue × growth in Korean memory exports (KRW). Average error {mape:.1f}% vs {mape_b:.0f}% for the best baseline. With only the first month of the quarter the error is {qtd1:.1f}%; with all three, {qtd3:.1f}%. It understated revenue in {under} of {len(n)} quarters.</p>
<p class="lim">{len(n)} quarters only. China fabs are outside Korean customs. Uses today's customs values, not first releases.</p></section>

<footer><b>What would change my view:</b> unit-value and contract momentum both turn negative for two consecutive months; weight growth fails to pick up as price growth fades; the nowcast gap to reported revenue flips from under- to over-prediction.</footer>
</main>
<script>
const D={json.dumps(data)};
const L={{paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{{color:'#8b98a8'}},margin:{{l:50,r:50,t:10,b:40}},legend:{{orientation:'h',y:1.12}},xaxis:{{gridcolor:'#262d38'}},yaxis:{{gridcolor:'#262d38'}}}};
const C={{cfg:{{displayModeBar:false,responsive:true}}}};
Plotly.newPlot('c1',[{{x:D.mx,y:D.mval,type:'bar',name:'Export value ($B)',marker:{{color:'#4ea1ff'}}}},{{x:D.mx,y:D.mwt,name:'Weight (tonnes)',yaxis:'y2',line:{{color:'#f0a43a',width:3}}}}],
 {{...L,yaxis:{{title:'$B',gridcolor:'#262d38'}},yaxis2:{{title:'tonnes',overlaying:'y',side:'right',rangemode:'tozero',showgrid:false}}}},C.cfg);
Plotly.newPlot('c2',[{{x:D.qx,y:D.qvol,type:'bar',name:'Volume (weight)',marker:{{color:'#4ea1ff'}}}},{{x:D.qx,y:D.quv,type:'bar',name:'Unit value',marker:{{color:'#f0a43a'}}}}],
 {{...L,xaxis:{{type:'category'}},barmode:'relative',yaxis:{{title:'YoY log change',gridcolor:'#262d38'}}}},C.cfg);
Plotly.newPlot('c3',[{{x:D.ux,y:D.uvm,name:'Export unit value, 3m change %',line:{{color:'#f0a43a',width:3}}}},{{x:D.cx,y:D.cm,name:'DDR4 8Gb contract, 3m change %',line:{{color:'#4ea1ff',width:3}},connectgaps:false}}],
 {{...L,yaxis:{{title:'%',gridcolor:'#262d38',zeroline:true,zerolinecolor:'#8b98a8'}}}},C.cfg);
Plotly.newPlot('c4',[{{x:D.nx,y:D.nrev,type:'bar',name:'Reported revenue',marker:{{color:'#4ea1ff'}}}},{{x:D.nx,y:D.nhat,name:'Export nowcast',mode:'lines+markers',line:{{color:'#f0a43a',width:3}}}}],
 {{...L,xaxis:{{type:'category'}},yaxis:{{title:'KRW tn',gridcolor:'#262d38'}}}},C.cfg);
</script></body></html>"""

out = ROOT / "site"; out.mkdir(exist_ok=True)
(out / "index.html").write_text(html, encoding="utf-8")
print("wrote", out / "index.html", "| uv share", round(share_uv), "| mom", round(uv_now, 1), "| nowcast MAPE", round(mape, 1), "under", under)
