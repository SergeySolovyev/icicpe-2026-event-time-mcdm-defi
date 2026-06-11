"""Standalone animated allocation-flow HTML + compact data blob.

Reads results/figures/allocation_flow.json (real T1 replay segments) and
emits:
  results/figures/allocation_widget_data.js  (compact `const D=...` blob)
  results/figures/allocation_flow.html       (self-contained animation)

The animation shows the $1M position hopping between the six venue lanes
exactly when the real replay switched (321 switches, Jan-Apr 2026), with
live APRs, the equity race vs hold-Aave, and play/scrub controls.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results/figures"

src = json.loads((FIG / "allocation_flow.json").read_text(encoding="utf-8"))

# compact: segments as [p, d1, eq1] (d0/eq0 chain from previous row)
segs = [[s["p"], s["d1"], int(s["eq1"])] for s in src["segments"]]
apr = [[(None if v is None else round(v, 2)) for v in src["apr"][p]]
       for p in ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]]
aprD = [round(d, 2) for d in src["apr_days"]]
eqAD = [round(d, 2) for d in src["eq_days"][::2]]
eqA = [int(v) for v in src["eq_aave"][::2]]

D = {"names": src["protocols"], "colors": src["colors"],
     "segs": segs, "aprD": aprD, "apr": apr, "eqAD": eqAD, "eqA": eqA,
     "meta": src["meta"]}
blob = "const D=" + json.dumps(D, separators=(",", ":")) + ";"
(FIG / "allocation_widget_data.js").write_text(blob, encoding="utf-8")
print(f"[ok] allocation_widget_data.js ({len(blob)/1024:.0f} KB)")

JS = r"""
const T=120.0, MONTHS=[[0,'Jan 1'],[31,'Feb 1'],[59,'Mar 1'],[90,'Apr 1'],[120,'Apr 30']];
const cv=document.getElementById('cv'), ctx=cv.getContext('2d');
const dark=false;
const TXT=dark?'#ddd':'#222', MUT=dark?'#999':'#777', GRID=dark?'#333':'#e5e2da';
let t=0, playing=true, speed=2, last=performance.now();
const segD0=[], segE0=[];
for(let i=0;i<D.segs.length;i++){segD0.push(i?D.segs[i-1][1]:0);segE0.push(i?D.segs[i-1][2]:1e6);}
function segAt(d){let lo=0,hi=D.segs.length-1;while(lo<hi){const m=(lo+hi)>>1;if(D.segs[m][1]<d)lo=m+1;else hi=m;}return lo;}
function eqT1(d){const i=segAt(d),d0=segD0[i],d1=D.segs[i][1];const f=d1>d0?Math.min(1,Math.max(0,(d-d0)/(d1-d0))):1;return segE0[i]+(D.segs[i][2]-segE0[i])*f;}
function eqAave(d){let k=0;while(k<D.eqAD.length-1&&D.eqAD[k+1]<=d)k++;return D.eqA[k];}
function aprAt(p,d){let k=0;while(k<D.aprD.length-1&&D.aprD[k+1]<=d)k++;const v=D.apr[p][k];return v==null?null:v;}
const GL=128, GR=12, W=cv.width, H=cv.height, laneH=40, laneTop=10;
const eqTop=laneTop+6*laneH+30, eqH=H-eqTop-26;
const x=d=>GL+d/T*(W-GL-GR);
const laneY=i=>laneTop+i*laneH+laneH/2;
const eqY=v=>eqTop+eqH-(v-1e6)/(1.0178e6-1e6)*eqH;
function draw(){
 ctx.clearRect(0,0,W,H);
 ctx.font='11px sans-serif';
 for(const[md,ml]of MONTHS){const mx=x(md);ctx.strokeStyle=GRID;ctx.beginPath();ctx.moveTo(mx,laneTop);ctx.lineTo(mx,eqTop+eqH);ctx.stroke();ctx.fillStyle=MUT;ctx.textAlign='center';ctx.fillText(ml,mx,eqTop+eqH+16);}
 for(let i=0;i<6;i++){
  const ly=laneY(i);
  ctx.strokeStyle=GRID;ctx.beginPath();ctx.moveTo(GL,ly);ctx.lineTo(W-GR,ly);ctx.stroke();
  ctx.textAlign='left';ctx.fillStyle=TXT;ctx.font='500 12px sans-serif';ctx.fillText(D.names[i],8,ly-2);
  const a=aprAt(i,t);ctx.font='11px sans-serif';ctx.fillStyle=D.colors[i];ctx.fillText(a==null?'нет данных':a.toFixed(2)+'%',8,ly+12);
 }
 const ci=segAt(t);
 for(let i=0;i<=ci;i++){
  const d0=segD0[i],d1=Math.min(D.segs[i][1],t),p=D.segs[i][0];
  ctx.strokeStyle=D.colors[p];ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(x(d0),laneY(p));ctx.lineTo(x(d1),laneY(p));ctx.stroke();
  if(i<ci){const np=D.segs[i+1][0];ctx.strokeStyle=dark?'#555':'#bbb';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x(D.segs[i][1]),laneY(p));ctx.lineTo(x(D.segs[i][1]),laneY(np));ctx.stroke();}
 }
 const cp=D.segs[ci][0];
 ctx.beginPath();ctx.arc(x(t),laneY(cp),7,0,7);ctx.fillStyle=D.colors[cp];ctx.fill();ctx.lineWidth=2;ctx.strokeStyle=dark?'#111':'#fff';ctx.stroke();
 ctx.strokeStyle=GRID;ctx.strokeRect(GL,eqTop,W-GL-GR,eqH);
 ctx.fillStyle=MUT;ctx.font='11px sans-serif';ctx.textAlign='left';ctx.fillText('equity, $1M start',GL+6,eqTop+14);
 ctx.strokeStyle='#7c5cff';ctx.setLineDash([4,3]);ctx.lineWidth=1.3;ctx.beginPath();let st=false;
 for(let k=0;k<D.eqAD.length&&D.eqAD[k]<=t;k++){const px=x(D.eqAD[k]),py=eqY(D.eqA[k]);st?ctx.lineTo(px,py):ctx.moveTo(px,py);st=true;}
 ctx.stroke();ctx.setLineDash([]);
 ctx.strokeStyle=TXT;ctx.lineWidth=1.8;ctx.beginPath();ctx.moveTo(x(0),eqY(1e6));
 for(let i=0;i<=ci;i++){ctx.lineTo(x(Math.min(D.segs[i][1],t)),eqY(i<ci?D.segs[i][2]:eqT1(t)));}
 ctx.stroke();
 const e1=eqT1(t),eA=eqAave(t);
 ctx.fillStyle=TXT;ctx.beginPath();ctx.arc(x(t),eqY(e1),3.5,0,7);ctx.fill();
 ctx.fillStyle='#7c5cff';ctx.beginPath();ctx.arc(x(t),eqY(eA),3,0,7);ctx.fill();
 document.getElementById('hud-date').textContent=new Date(Date.UTC(2026,0,1)+t*864e5).toLocaleDateString('ru-RU',{day:'numeric',month:'short'});
 document.getElementById('hud-eq').textContent='$'+Math.round(e1).toLocaleString('en-US');
 document.getElementById('hud-delta').textContent='+$'+Math.round(e1-eA).toLocaleString('en-US');
 document.getElementById('hud-sw').textContent=ci;
 document.getElementById('scrub').value=t;
}
function tick(now){if(playing){t+=(now-last)/1000*6*speed;if(t>=T){t=T;playing=false;updBtn();}}last=now;draw();requestAnimationFrame(tick);}
function updBtn(){document.getElementById('pp').textContent=playing?'❚❚':'▶';}
document.getElementById('pp').onclick=()=>{if(!playing&&t>=T)t=0;playing=!playing;updBtn();};
document.getElementById('speed').onchange=e=>{speed=+e.target.value;};
document.getElementById('scrub').oninput=e=>{t=+e.target.value;playing=false;updBtn();draw();};
updBtn();requestAnimationFrame(tick);
"""

HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>T1 event-time allocation — real replay Jan–Apr 2026</title>
<style>
body{font-family:system-ui,sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#222;background:#fdfcf9}
h1{font-size:19px;font-weight:600}
p{font-size:13px;color:#666;line-height:1.5}
.cards{display:flex;gap:10px;margin:14px 0}
.card{flex:1;background:#f2f0e9;border-radius:8px;padding:10px 14px}
.card .l{font-size:11px;color:#777}.card .v{font-size:19px;font-weight:600;margin-top:2px}
.controls{display:flex;gap:10px;align-items:center;margin:10px 0}
button{font-size:14px;padding:4px 14px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer}
select{font-size:13px;padding:3px}input[type=range]{flex:1}
canvas{width:100%;height:auto;border:1px solid #e5e2da;border-radius:8px;background:#fff}
</style></head><body>
<h1>Как $1M переходит между 6 протоколами — реальный replay (T1, Jan–Apr 2026)</h1>
<p>864 тыс. блоков Ethereum, 321 реальное переключение, $68 реального газа.
Источник: <code>equity_t1_threshold.parquet</code> — каждая точка пути соответствует
фактическому состоянию позиции в этом блоке. Пунктир — пассивный холд Aave.</p>
<div class="cards">
<div class="card"><div class="l">Дата</div><div class="v" id="hud-date">1 янв.</div></div>
<div class="card"><div class="l">Позиция T1</div><div class="v" id="hud-eq">$1,000,000</div></div>
<div class="card"><div class="l">vs hold Aave</div><div class="v" id="hud-delta">+$0</div></div>
<div class="card"><div class="l">Переключений</div><div class="v" id="hud-sw">0</div></div>
</div>
<canvas id="cv" width="730" height="430"></canvas>
<div class="controls">
<button id="pp">❚❚</button>
<select id="speed"><option value="1">1×</option><option value="2" selected>2×</option><option value="4">4×</option><option value="8">8×</option></select>
<input type="range" id="scrub" min="0" max="120" step="0.05" value="0">
</div>
<script>@@DATA@@</script>
<script>@@JS@@</script>
</body></html>"""

html = HTML.replace("@@DATA@@", blob).replace("@@JS@@", JS)
(FIG / "allocation_flow.html").write_text(html, encoding="utf-8")
print(f"[ok] allocation_flow.html ({len(html)/1024:.0f} KB)")
