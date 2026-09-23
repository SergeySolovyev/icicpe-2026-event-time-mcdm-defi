"""Standalone animated allocation-flow page + compact data blob.

Pipeline -- run in this order; both steps are deterministic:
  1. python scripts/make_allocation_widget_curves.py
       -> results/figures/allocation_widget_curves.json  (T2, greedy, 6 passive holds)
  2. python scripts/make_allocation_widget.py [--fragment PATH]
       -> results/figures/allocation_flow.html          (self-contained page)
       -> results/figures/allocation_widget_data.js     (compact `const D=...` blob: T1 + hold-Aave)

Inputs: results/figures/allocation_flow.json (real T1 replay segments, APRs and
hold-Aave equity, written by make_allocation_viz.py), the curves JSON above, and
results/tables/equity/equity_t1_threshold.parquet (block numbers).

The page shows our $1M portfolio hopping between the six venue lanes exactly
when the real replay switched (321 switches, Jan-Apr 2026), live APRs, and the
value race of T1 (our portfolio) against T2, the greedy router and every
passive hold, with play / speed / scrub controls. English copy; responsive from
phone to desktop, sharp on HiDPI screens, follows the viewer's light/dark theme
and respects prefers-reduced-motion (opens on the finished replay).

--fragment PATH also writes the same page without the <!doctype>/<html>/<head>/
<body> skeleton, for hosting as a Claude Artifact (the host supplies it).
--site PATH writes the sergeisolovev.com variant (site fonts, palette, meta tags and
back-links), deployed at /research/defi-allocator-replay.html.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "results/figures"
EQ_T1 = ROOT / "results/tables/equity/equity_t1_threshold.parquet"
PROTO = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]
EN_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


HEAD = r"""<title>DeFi-Vega Allocation Flow</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Unbounded:wght@500&display=swap">
<style>
:root{
  --ground:#f3f5f8;--surface:#ffffff;--ink:#121922;--muted:#566272;--faint:#8b96a4;
  --rule:#e1e6ec;--rule-strong:#c8d0da;--t2:#b0158f;--focus:#2d5be3;
  --display:"Unbounded","Golos Text",system-ui,sans-serif;
  --body:"Golos Text",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0b1016;--surface:#121821;--ink:#e6edf3;--muted:#93a1b1;--faint:#65758a;
    --rule:#202b38;--rule-strong:#2e3b4c;--t2:#e27bd6;--focus:#7fa6ff;color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --ground:#0b1016;--surface:#121821;--ink:#e6edf3;--muted:#93a1b1;--faint:#65758a;
  --rule:#202b38;--rule-strong:#2e3b4c;--t2:#e27bd6;--focus:#7fa6ff;color-scheme:dark;
}
*,*::before,*::after{box-sizing:border-box}
html,body{background:var(--ground)}
body{margin:0;color:var(--ink);font:15px/1.55 var(--body);-webkit-font-smoothing:antialiased}
.page{max-width:860px;margin:0 auto;padding:clamp(20px,5vw,44px) clamp(14px,4vw,28px) 48px;display:grid;grid-template-columns:minmax(0,1fr);gap:20px}
.page>*{min-width:0}
.head{display:grid;gap:10px}
.eyebrow{margin:0;font:500 11.5px/1.4 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
h1{margin:0;font:500 clamp(23px,4.6vw,34px)/1.14 var(--display);letter-spacing:-.015em;text-wrap:balance}
.lede{margin:0;max-width:64ch;color:var(--muted);text-wrap:pretty}
.lede b{color:var(--ink);font-weight:600;font-variant-numeric:tabular-nums}
.hud{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:var(--surface);border:1px solid var(--rule);border-radius:12px}
.stat{display:grid;gap:3px;align-content:start;min-width:0;padding:13px 16px 14px}
.stat+.stat{border-left:1px solid var(--rule)}
.k{font:500 11px/1.3 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.v{display:flex;align-items:center;gap:8px;min-width:0;font:500 20px/1.25 var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.v>span{min-width:0;overflow:hidden;text-overflow:ellipsis}
.v.name{font-family:var(--body);font-weight:600}
.s{font:400 12px/1.35 var(--mono);color:var(--muted);font-variant-numeric:tabular-nums}
.chip{flex:none;width:10px;height:10px;border-radius:3px;background:var(--faint)}
.instrument{margin:0;background:var(--surface);border:1px solid var(--rule);border-radius:14px;overflow:hidden}
#cv{display:block;width:100%;max-width:100%;height:552px}
.transport{display:flex;align-items:center;gap:12px;padding:10px 14px;border-top:1px solid var(--rule)}
.play{flex:none;display:grid;place-items:center;width:40px;height:40px;padding:0;border:0;border-radius:50%;background:var(--ink);color:var(--surface);cursor:pointer}
.play svg{width:15px;height:15px;fill:currentColor}
.speed{flex:none;display:inline-flex;border:1px solid var(--rule-strong);border-radius:9px;overflow:hidden}
.speed button{min-width:36px;padding:8px 0;border:0;background:transparent;color:var(--muted);font:500 12px/1 var(--mono);cursor:pointer}
.speed button+button{border-left:1px solid var(--rule-strong)}
.speed button[aria-pressed="true"]{background:var(--ink);color:var(--surface)}
.scrub{flex:1;min-width:0;margin:0;accent-color:var(--ink);cursor:pointer}
.dayread{flex:none;min-width:64px;text-align:right;font:500 12px/1 var(--mono);color:var(--muted);font-variant-numeric:tabular-nums}
.notes{display:grid;gap:8px;margin:0;padding:0 2px;list-style:none;max-width:72ch;font-size:13px;line-height:1.5;color:var(--muted)}
.notes b{color:var(--ink);font-weight:600}
.notes code{font:12px/1 var(--mono);color:var(--ink)}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
@media (max-width:640px){
  .hud{grid-template-columns:repeat(2,minmax(0,1fr))}
  .stat:nth-child(3){border-left:0}
  .stat:nth-child(n+3){border-top:1px solid var(--rule)}
  .v{font-size:18px}
  #cv{height:482px}
  .dayread{display:none}
}
</style>
"""

BODY = r"""<main class="page">
<header class="head">
  <p class="eyebrow">DeFi-Vega · T1 strategy backtest · @@SPAN@@</p>
  <h1>$1M across six lending protocols</h1>
  <p class="lede">A block-by-block backtest on recorded on-chain rates: a simulated <b>$1M</b>, <b>@@N_BLOCKS_K@@</b> Ethereum blocks, <b>@@N_SW@@</b>&nbsp;@@SW_WORD@@ and <b>$@@GAS@@</b> of gas over the whole period. The dot on the lanes shows where our portfolio sits at every moment; the lower panel tracks its value against the alternative strategies and passive holds.</p>
</header>
<section class="hud" aria-label="Replay state at the current moment">
  <div class="stat"><span class="k">Date</span><span class="v"><span id="hud-date">@@START_LABEL@@</span></span><span class="s" id="hud-block">block @@B_FIRST@@</span></div>
  <div class="stat"><span class="k">Portfolio is in</span><span class="v name"><span class="chip" id="hud-chip"></span><span id="hud-venue">—</span></span><span class="s" id="hud-apr">—</span></div>
  <div class="stat"><span class="k">Portfolio value</span><span class="v"><span id="hud-eq">$1,000,000</span></span><span class="s" id="hud-delta">+$0 vs Aave hold</span></div>
  <div class="stat"><span class="k">Switches</span><span class="v"><span id="hud-sw">0</span></span><span class="s">of @@N_SW@@</span></div>
</section>
<figure class="instrument">
  <canvas id="cv" role="img" aria-label="Replay animation. Top: six venue lanes showing where our portfolio sits over time. Bottom: our portfolio's value (T1) against T2, the greedy router and a passive hold in each venue."></canvas>
  <div class="transport">
    <button class="play" id="pp" type="button" aria-label="Pause"></button>
    <div class="speed" role="group" aria-label="Playback speed"><button type="button" data-s="1" aria-pressed="false">1×</button><button type="button" data-s="2" aria-pressed="true">2×</button><button type="button" data-s="4" aria-pressed="false">4×</button><button type="button" data-s="8" aria-pressed="false">8×</button></div>
    <input class="scrub" id="scrub" type="range" min="0" max="120" step="0.05" value="0" aria-label="Scrub through the replay">
    <span class="dayread" id="dayread">day 0</span>
  </div>
</figure>
<ul class="notes">
  <li><b>Our portfolio</b> follows T1, a gas-aware threshold rule: it moves to another venue only when the expected extra yield over the expected holding time beats the gas cost. T2 is Ornstein–Uhlenbeck optimal stopping; the greedy router always jumps to the best spot rate; a passive hold keeps $1M in one venue for the whole period.</li>
  <li>Source: <code>equity_t1_threshold.parquet</code>, the simulated position state in each of @@N_BLOCKS@@ blocks, #@@B_FIRST@@ to #@@B_LAST@@, replayed on recorded per-block rates. No real funds were deployed. Passive holds are recomputed block by block from the same rates, with compounding.</li>
  <li>T3 (Cox hazard model) is identical to T1 in this replay because it fell back to T1, so it has no separate line. Its honest out-of-sample test is a separate experiment: −5.97&nbsp;bp, 0 of 5 windows.</li>
</ul>
</main>
<script>@@DATA@@</script>
<script>@@JS@@</script>
"""

JS = r"""(()=>{
'use strict';
const $=id=>document.getElementById(id), TAU=Math.PI*2;
const cv=$('cv'), ctx=cv.getContext('2d');
const N=D.segs.length, T=D.segs[N-1][1];
const T0=Date.parse(D.meta.start+'T00:00:00Z');
const MONTHS=[];
{const s=new Date(T0);for(let k=0;;k++){const m=Date.UTC(s.getUTCFullYear(),s.getUTCMonth()+k,1),d=(m-T0)/864e5;if(d>T-1)break;if(d>=0)MONTHS.push([d,new Date(m).toLocaleDateString('en-US',{month:'short',timeZone:'UTC'})]);}}
const segD0=new Array(N), segE0=new Array(N);
for(let i=0;i<N;i++){segD0[i]=i?D.segs[i-1][1]:0;segE0[i]=i?D.segs[i-1][2]:1e6;}
function segAt(d){let lo=0,hi=N-1;while(lo<hi){const m=(lo+hi)>>1;if(D.segs[m][1]<d)lo=m+1;else hi=m;}return lo;}
function idxLE(a,d){let lo=0,hi=a.length-1;while(lo<hi){const m=(lo+hi+1)>>1;if(a[m]<=d)lo=m;else hi=m-1;}return lo;}
function lerpAt(grid,arr,d){const k=idxLE(grid,d),k2=Math.min(k+1,arr.length-1),d0=grid[k],d1=grid[k2];const f=d1>d0?Math.min(1,Math.max(0,(d-d0)/(d1-d0))):0;return arr[k]+(arr[k2]-arr[k])*f;}
function eqT1(d){const i=segAt(d),d0=segD0[i],d1=D.segs[i][1];const f=d1>d0?Math.min(1,Math.max(0,(d-d0)/(d1-d0))):1;return segE0[i]+(D.segs[i][2]-segE0[i])*f;}
function aprAt(p,d){const v=D.apr[p][idxLE(D.aprD,d)];return v==null?null:v;}

const Y0=1e6;let yMax=Y0;
for(const s of D.segs)yMax=Math.max(yMax,s[2]);
for(const a of [D.eqT2,D.eqGreedy,D.eqA,...D.eqHolds])for(const v of a)yMax=Math.max(yMax,v);
const Y1=yMax+(yMax-Y0)*.07;
const STEP=[1000,2000,2500,5000,10000,20000,25000,50000,100000].find(s=>(yMax-Y0)/s<=5)||250000;
const TICKS=[];for(let v=Y0;v<=yMax;v+=STEP)TICKS.push(v);

// strategy key, drawn in the left gutter of the value panel
const KEY=[
  {name:'Our portfolio',sub:'T1 threshold rule',subN:'T1 rule',kind:'t1'},
  {name:'T2',sub:'OU optimal stopping',subN:'OU stopping',kind:'t2'},
  {name:'Greedy router',sub:'best spot rate',subN:'best spot rate',kind:'greedy'},
  {name:'Passive hold',sub:'one line per venue',subN:'per venue',kind:'hold'},
];

let C={};
function readTokens(){const cs=getComputedStyle(document.documentElement),g=n=>cs.getPropertyValue(n).trim();
  C={ink:g('--ink'),muted:g('--muted'),faint:g('--faint'),rule:g('--rule'),ruleS:g('--rule-strong'),surface:g('--surface'),t2:g('--t2'),body:g('--body'),mono:g('--mono')};}

let W=0,H=0,L=null,lastW=-1;
function layout(){
  const w=Math.round(cv.getBoundingClientRect().width)||cv.parentElement.clientWidth||720;
  if(w===lastW&&L)return false;
  lastW=w;
  const n=w<600, GL=n?118:156, GR=n?12:20, laneTop=n?34:40, laneH=n?38:42, gap=n?40:44, eqH=n?150:186, axis=30;
  const eqTop=laneTop+6*laneH+gap, h=eqTop+eqH+axis, dpr=Math.min(window.devicePixelRatio||1,3);
  W=w;H=h;cv.style.height=h+'px';cv.width=Math.round(w*dpr);cv.height=Math.round(h*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  L={n,GL,GR,laneTop,laneH,eqTop,eqH};
  return true;
}
const x=d=>L.GL+d/T*(W-L.GL-L.GR);
const laneY=i=>L.laneTop+i*L.laneH+L.laneH/2;
const eqY=v=>L.eqTop+L.eqH-(v-Y0)/(Y1-Y0)*L.eqH;
const px=v=>Math.round(v)+.5;

function curve(arr,tEnd){
  ctx.beginPath();ctx.moveTo(x(D.eqAD[0]),eqY(arr[0]));
  const n=D.eqAD.length;let k=1;
  for(;k<n&&D.eqAD[k]<=tEnd;k++)ctx.lineTo(x(D.eqAD[k]),eqY(arr[k]));
  if(k<n&&tEnd>D.eqAD[k-1])ctx.lineTo(x(tEnd),eqY(lerpAt(D.eqAD,arr,tEnd)));
  ctx.stroke();
}
function t1Path(tEnd,ci){
  ctx.beginPath();ctx.moveTo(x(0),eqY(Y0));
  for(let i=0;i<=ci;i++){const done=D.segs[i][1]<=tEnd;ctx.lineTo(x(Math.min(D.segs[i][1],tEnd)),eqY(done?D.segs[i][2]:eqT1(tEnd)));}
  ctx.stroke();
}
function lanePaths(tEnd,ci,width){
  ctx.lineWidth=width;
  for(let p=0;p<6;p++){
    ctx.strokeStyle=D.colors[p];ctx.beginPath();let any=false;
    for(let i=0;i<=ci;i++){if(D.segs[i][0]!==p)continue;const a=segD0[i],b=Math.min(D.segs[i][1],tEnd);if(b<a)continue;ctx.moveTo(x(a),laneY(p));ctx.lineTo(x(b),laneY(p));any=true;}
    if(any)ctx.stroke();
  }
}
function drawKey(){
  const step=L.n?36:40, y0=L.eqTop+14, s0=8, s1=20;
  for(let j=0;j<KEY.length;j++){
    const it=KEY[j], y=y0+j*step, sy=y-4.5;
    ctx.setLineDash([]);
    if(it.kind==='t1'){ctx.strokeStyle=C.ink;ctx.lineWidth=3;ctx.beginPath();ctx.moveTo(s0,sy);ctx.lineTo(s1,sy);ctx.stroke();ctx.beginPath();ctx.arc(s1,sy,3,0,TAU);ctx.fillStyle=C.ink;ctx.fill();}
    else if(it.kind==='t2'){ctx.strokeStyle=C.t2;ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(s0,sy);ctx.lineTo(s1,sy);ctx.stroke();}
    else if(it.kind==='greedy'){ctx.strokeStyle=C.faint;ctx.lineWidth=1.6;ctx.setLineDash([3,2]);ctx.beginPath();ctx.moveTo(s0,sy);ctx.lineTo(s1+1,sy);ctx.stroke();ctx.setLineDash([]);}
    else{for(let q=0;q<6;q++){ctx.fillStyle=D.colors[q];ctx.fillRect(s0+q*2.2,sy-3,2.2,6);}}
    ctx.textAlign='left';
    ctx.fillStyle=C.ink;ctx.font=(j===0?'600 ':'500 ')+(L.n?'12px ':'13px ')+C.body;ctx.fillText(it.name,26,y);
    ctx.fillStyle=C.muted;ctx.font='400 '+(L.n?'10.5px ':'11px ')+C.body;ctx.fillText(L.n?it.subN:it.sub,26,y+14);
  }
}

let t=0,playing=true,speed=2,last=0,dirty=true;
function draw(){
  const ci=segAt(t), cp=D.segs[ci][0], top=L.laneTop, bottom=L.eqTop+L.eqH, hx=x(t);
  ctx.clearRect(0,0,W,H);
  ctx.lineCap='butt';ctx.lineJoin='round';ctx.textBaseline='alphabetic';ctx.globalAlpha=1;ctx.setLineDash([]);

  // panel titles
  ctx.font='600 12px '+C.body;ctx.fillStyle=C.muted;ctx.textAlign='left';
  ctx.fillText('Where our portfolio sits',L.GL,L.laneTop-14);
  ctx.fillText('Portfolio value',L.GL,L.eqTop-14);

  // month grid, labelled at each month start
  ctx.lineWidth=1;ctx.strokeStyle=C.rule;ctx.beginPath();
  for(const[md]of MONTHS){ctx.moveTo(px(x(md)),top);ctx.lineTo(px(x(md)),bottom);}
  ctx.moveTo(px(x(T)),top);ctx.lineTo(px(x(T)),bottom);ctx.stroke();
  ctx.font='500 11px '+C.mono;ctx.fillStyle=C.muted;ctx.textAlign='left';
  for(const[md,ml]of MONTHS)ctx.fillText(ml,x(md)+5,bottom+19);

  // venue lanes: rule, swatch, name, live APR
  ctx.strokeStyle=C.rule;ctx.beginPath();
  for(let i=0;i<6;i++){const ly=px(laneY(i));ctx.moveTo(L.GL,ly);ctx.lineTo(W-L.GR,ly);}
  ctx.stroke();
  for(let i=0;i<6;i++){
    const ly=laneY(i),a=aprAt(i,t);
    ctx.fillStyle=D.colors[i];ctx.beginPath();ctx.arc(14,ly-4.5,4.5,0,TAU);ctx.fill();
    ctx.textAlign='left';ctx.fillStyle=C.ink;ctx.font='500 '+(L.n?'12px ':'13px ')+C.body;ctx.fillText(D.names[i],26,ly);
    ctx.font='400 11px '+C.mono;ctx.fillStyle=C.muted;ctx.fillText(a==null?'no data':a.toFixed(2)+'% APR',26,ly+14);
  }

  // the whole route as a faint ghost, then the travelled part on top
  const lw=L.n?3:4;
  ctx.globalAlpha=.17;lanePaths(T,N-1,lw);ctx.globalAlpha=1;
  ctx.lineWidth=1;ctx.strokeStyle=C.ruleS;ctx.beginPath();
  for(let i=0;i<ci;i++){const sx=px(x(D.segs[i][1]));ctx.moveTo(sx,laneY(D.segs[i][0]));ctx.lineTo(sx,laneY(D.segs[i+1][0]));}
  ctx.stroke();
  lanePaths(t,ci,lw);

  // playhead through both panels
  ctx.globalAlpha=.45;ctx.strokeStyle=C.faint;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(px(hx),top);ctx.lineTo(px(hx),bottom);ctx.stroke();ctx.globalAlpha=1;

  // value panel: gridlines with $ labels inside the plot, strategy key in the gutter
  ctx.strokeStyle=C.rule;ctx.lineWidth=1;ctx.beginPath();
  for(const v of TICKS){const yy=px(eqY(v));ctx.moveTo(L.GL,yy);ctx.lineTo(W-L.GR,yy);}
  ctx.stroke();
  ctx.font='400 10.5px '+C.mono;ctx.fillStyle=C.muted;ctx.textAlign='left';
  for(const v of TICKS){if(v===Y0)continue;ctx.fillText('$'+(v/1e6).toFixed(3)+'M',L.GL+5,eqY(v)-5);}
  drawKey();

  // ghosts of the full period
  ctx.globalAlpha=.16;ctx.lineWidth=1.2;
  for(let i=0;i<6;i++){ctx.strokeStyle=D.colors[i];curve(D.eqHolds[i],T);}
  ctx.strokeStyle=C.t2;curve(D.eqT2,T);
  ctx.strokeStyle=C.ink;ctx.lineWidth=2;t1Path(T,N-1);
  ctx.globalAlpha=1;

  // travelled curves
  ctx.lineWidth=1.3;ctx.globalAlpha=.8;
  for(let i=0;i<6;i++){ctx.strokeStyle=D.colors[i];curve(D.eqHolds[i],t);}
  ctx.globalAlpha=1;
  ctx.setLineDash([4,3]);ctx.strokeStyle=C.faint;ctx.lineWidth=1.3;curve(D.eqGreedy,t);ctx.setLineDash([]);
  ctx.strokeStyle=C.t2;ctx.lineWidth=1.7;curve(D.eqT2,t);
  ctx.strokeStyle=C.ink;ctx.lineWidth=2.6;t1Path(t,ci);
  const e1=eqT1(t);
  ctx.beginPath();ctx.arc(hx,eqY(e1),4.5,0,TAU);ctx.fillStyle=C.ink;ctx.fill();ctx.lineWidth=2;ctx.strokeStyle=C.surface;ctx.stroke();

  // our portfolio right now: venue-coloured ring, portfolio-coloured core
  const my=laneY(cp);
  ctx.beginPath();ctx.arc(hx,my,8.5,0,TAU);ctx.fillStyle=D.colors[cp];ctx.fill();ctx.lineWidth=2.5;ctx.strokeStyle=C.surface;ctx.stroke();
  ctx.beginPath();ctx.arc(hx,my,3.6,0,TAU);ctx.fillStyle=C.ink;ctx.fill();
  return {ci,cp,e1};
}

const fmtUsd=v=>'$'+Math.round(v).toLocaleString('en-US');
const shown={};
function set(id,val){if(shown[id]!==val){shown[id]=val;$(id).textContent=val;}}
function hud(s){
  const dt=new Date(T0+Math.min(t,T-1e-3)*864e5);
  set('hud-date',dt.toLocaleDateString('en-US',{month:'short',day:'numeric',timeZone:'UTC'}));
  const bx=t<=0?D.bFirst:t>=T?D.bLast:null;
  set('hud-block',bx!=null?'block '+bx.toLocaleString('en-US'):'≈ block '+Math.round(lerpAt(D.aprD,D.blk,t)).toLocaleString('en-US'));
  set('hud-venue',D.names[s.cp]);
  const chip=$('hud-chip');if(chip.dataset.p!==String(s.cp)){chip.dataset.p=String(s.cp);chip.style.background=D.colors[s.cp];}
  const a=aprAt(s.cp,t);set('hud-apr',a==null?'rate: no data':a.toFixed(2)+'% APR');
  set('hud-eq',fmtUsd(s.e1));
  const dA=s.e1-lerpAt(D.eqAD,D.eqA,t);set('hud-delta',(dA<0?'−':'+')+fmtUsd(Math.abs(dA))+' vs Aave hold');
  set('hud-sw',String(s.ci));
  set('dayread','day '+Math.floor(t));
}

const ICON={
  play:'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 2.6v10.8L13 8z"/></svg>',
  pause:'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.6 2.5h3.1v11H3.6zm5.7 0h3.1v11H9.3z"/></svg>',
  replay:'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3V.8L4.6 3.9 8 7V4.6a3.9 3.9 0 1 1-3.9 3.9H2.5A5.5 5.5 0 1 0 8 3z"/></svg>'
};
const pp=$('pp'), scrub=$('scrub');
scrub.max=String(T);
if(matchMedia('(prefers-reduced-motion: reduce)').matches){t=T;playing=false;}
function setPlaying(v){
  playing=v;last=performance.now();
  const end=!v&&t>=T, k=v?'pause':end?'replay':'play';
  if(pp.dataset.k!==k){pp.dataset.k=k;pp.innerHTML=ICON[k];pp.setAttribute('aria-label',v?'Pause':end?'Replay from the start':'Play');}
}
pp.addEventListener('click',()=>{if(!playing&&t>=T)t=0;setPlaying(!playing);dirty=true;});
const speedBtns=document.querySelectorAll('.speed button');
for(const b of speedBtns)b.addEventListener('click',()=>{speed=+b.dataset.s;for(const o of speedBtns)o.setAttribute('aria-pressed',String(o===b));});
scrub.addEventListener('input',()=>{t=+scrub.value;setPlaying(false);dirty=true;});
document.addEventListener('keydown',e=>{
  if(e.target.closest&&e.target.closest('input,button,select,textarea,a'))return;
  if(e.code==='Space'){e.preventDefault();pp.click();}
  else if(e.key==='ArrowRight'||e.key==='ArrowLeft'){t=Math.max(0,Math.min(T,t+(e.key==='ArrowRight'?2:-2)));setPlaying(false);dirty=true;}
});

function render(){const s=draw();hud(s);if(document.activeElement!==scrub)scrub.value=String(t);}
function frame(now){
  const dt=Math.min(100,now-last);last=now;
  if(playing){t+=dt/1000*6*speed;if(t>=T){t=T;setPlaying(false);}dirty=true;}
  if(dirty){dirty=false;render();}
  requestAnimationFrame(frame);
}
const retheme=()=>{readTokens();dirty=true;};
const mq=matchMedia('(prefers-color-scheme: dark)');
if(mq.addEventListener)mq.addEventListener('change',retheme);else if(mq.addListener)mq.addListener(retheme);
new MutationObserver(retheme).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme','class']});
if(document.fonts&&document.fonts.ready)document.fonts.ready.then(()=>{dirty=true;});
readTokens();layout();setPlaying(playing);render();
new ResizeObserver(()=>{if(layout())dirty=true;}).observe(cv);
last=performance.now();requestAnimationFrame(frame);
})();
"""


# sergeisolovev.com variant: same page, site typography and palette, site meta and back-links
SITE_URL = "https://sergeisolovev.com/research/defi-allocator-replay.html"
SITE_DESC = ("Block-by-block backtest of a gas-aware USDC allocator across six Ethereum lending "
             "protocols, Jan-Apr 2026: where a simulated $1M sat and how its value compared with "
             "T2, a greedy router and passive holds.")
SITE_SUBS = [
    ("<title>DeFi-Vega Allocation Flow</title>",
     "<title>DeFi allocator replay | Sergei Solovev</title>\n"
     f'<meta name="description" content="{SITE_DESC}">\n'
     '<meta name="author" content="Sergei Solovev">\n'
     f'<link rel="canonical" href="{SITE_URL}">\n'
     '<meta property="og:type" content="article">\n'
     '<meta property="og:site_name" content="Sergei Solovev">\n'
     '<meta property="og:title" content="DeFi allocator replay">\n'
     f'<meta property="og:description" content="{SITE_DESC}">\n'
     f'<meta property="og:url" content="{SITE_URL}">\n'
     '<meta property="og:image" content="https://sergeisolovev.com/portrait.jpg">\n'
     '<meta name="twitter:card" content="summary">'),
    ("family=Golos+Text:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Unbounded:wght@500",
     "family=Instrument+Serif&family=JetBrains+Mono:wght@400;500&family=Manrope:wght@400;500;600;700"),
    ('--display:"Unbounded","Golos Text",system-ui,sans-serif;',
     '--display:"Instrument Serif",Georgia,"Times New Roman",serif;'),
    ('--body:"Golos Text",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;',
     '--body:"Manrope",system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;'),
    ("--ground:#f3f5f8;--surface:#ffffff;--ink:#121922;--muted:#566272;--faint:#8b96a4;",
     "--ground:#f4f3ef;--surface:#ffffff;--ink:#111827;--muted:#6b7280;--faint:#9ca3af;"),
    ("--rule:#e1e6ec;--rule-strong:#c8d0da;--t2:#b0158f;--focus:#2d5be3;",
     "--rule:#e6e3db;--rule-strong:#d3cfc4;--t2:#b0158f;--focus:#b38a5a;"),
    ("h1{margin:0;font:500 clamp(23px,4.6vw,34px)/1.14 var(--display);letter-spacing:-.015em;text-wrap:balance}",
     "h1{margin:0;font:400 clamp(32px,6.4vw,48px)/1.04 var(--display);letter-spacing:-.005em;text-wrap:balance}"),
    ("</style>",
     ".sitenav{display:flex;flex-wrap:wrap;gap:8px 22px;padding-top:18px;border-top:1px solid var(--rule);font-size:14px}\n"
     ".sitenav a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--rule-strong)}\n"
     ".sitenav a:hover{border-bottom-color:var(--ink)}\n</style>"),
    ('<p class="eyebrow">DeFi-Vega · ', '<p class="eyebrow">DeFi allocator · '),
    ("</main>",
     '<nav class="sitenav" aria-label="Site"><a href="/">&larr; Home</a><a href="/#research">Research</a>'
     '<a href="https://github.com/SergeySolovyev/defi-allocator-agent" rel="noopener">Agent code on GitHub</a></nav>\n</main>'),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build results/figures/allocation_flow.html")
    ap.add_argument("--fragment", type=Path,
                    help="also write the page without the HTML skeleton (Artifact hosting)")
    ap.add_argument("--site", type=Path,
                    help="also write the sergeisolovev.com page (site fonts, palette, meta, back-links)")
    args = ap.parse_args()

    src = json.loads((FIG / "allocation_flow.json").read_text(encoding="utf-8"))
    curves = json.loads((FIG / "allocation_widget_curves.json").read_text(encoding="utf-8"))

    # compact: segments as [p, d1, eq1] (d0/eq0 chain from the previous row)
    segs = [[s["p"], s["d1"], int(s["eq1"])] for s in src["segments"]]
    apr = [[(None if v is None else round(v, 2)) for v in src["apr"][p]] for p in PROTO]
    aprD = [round(d, 2) for d in src["apr_days"]]
    eqAD = [round(d, 2) for d in src["eq_days"][::2]]
    eqA = [int(v) for v in src["eq_aave"][::2]]
    meta = src["meta"]

    base = {"names": src["protocols"], "colors": src["colors"], "segs": segs,
            "aprD": aprD, "apr": apr, "eqAD": eqAD, "eqA": eqA, "meta": meta}
    blob = "const D=" + json.dumps(base, separators=(",", ":")) + ";"
    (FIG / "allocation_widget_data.js").write_text(blob, encoding="utf-8")
    print(f"[ok] allocation_widget_data.js ({len(blob)/1024:.0f} KB)")

    for key in ("eqT2", "eqGreedy"):
        if len(curves[key]) != len(eqAD):
            raise SystemExit(f"{key}: {len(curves[key])} points vs eqAD grid {len(eqAD)} "
                             "-- rerun scripts/make_allocation_widget_curves.py")
    if len(curves["eqHolds"]) != 6 or any(len(h) != len(eqAD) for h in curves["eqHolds"]):
        raise SystemExit("eqHolds misaligned with the eqAD grid "
                         "-- rerun scripts/make_allocation_widget_curves.py")

    # block height on the APR day grid, from the replay's own timestamps
    eq = pd.read_parquet(EQ_T1, columns=["block_number", "block_timestamp"])
    ts = pd.to_datetime(eq["block_timestamp"], utc=True)
    day = ((ts - ts.iloc[0]).dt.total_seconds() / 86400.0).to_numpy()
    idx = np.clip(np.searchsorted(day, np.asarray(aprD), side="right") - 1, 0, len(eq) - 1)
    blk = [int(b) for b in eq["block_number"].to_numpy()[idx]]
    b_first, b_last = int(eq["block_number"].iloc[0]), int(eq["block_number"].iloc[-1])

    page = dict(base, eqT2=curves["eqT2"], eqGreedy=curves["eqGreedy"],
                eqHolds=curves["eqHolds"], blk=blk, bFirst=b_first, bLast=b_last)
    data = "const D=" + json.dumps(page, separators=(",", ":")).replace("</", "<\\/") + ";"

    d0, d1 = date.fromisoformat(meta["start"]), date.fromisoformat(meta["end"])
    n_sw = int(meta["n_switches"])
    subs = {
        "@@SPAN@@": f"{EN_MON[d0.month-1]} {d0.day} – {EN_MON[d1.month-1]} {d1.day}, {d1.year}",
        "@@START_LABEL@@": f"{EN_MON[d0.month-1]} {d0.day}",
        "@@N_BLOCKS_K@@": f"{round(meta['n_blocks'] / 1000)}k",
        "@@N_BLOCKS@@": f"{int(meta['n_blocks']):,}",
        "@@N_SW@@": str(n_sw),
        "@@SW_WORD@@": "switch" if n_sw == 1 else "switches",
        "@@GAS@@": f"{meta['gas_usd']:.2f}",
        "@@B_FIRST@@": f"{b_first:,}",
        "@@B_LAST@@": f"{b_last:,}",
    }
    body = BODY
    for k, v in subs.items():
        body = body.replace(k, v)
    body = body.replace("@@DATA@@", data).replace("@@JS@@", JS)
    if "@@" in body:
        raise SystemExit("unfilled placeholder left in the page template")

    standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                  '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
                  + HEAD + "</head>\n<body>\n" + body + "</body>\n</html>\n")
    (FIG / "allocation_flow.html").write_text(standalone, encoding="utf-8")
    print(f"[ok] allocation_flow.html ({len(standalone)/1024:.0f} KB)")
    if args.fragment:
        args.fragment.write_text(HEAD + body, encoding="utf-8")
        print(f"[ok] fragment -> {args.fragment}")
    if args.site:
        site = standalone
        for old, new in SITE_SUBS:
            if site.count(old) != 1:
                raise SystemExit(f"site variant: expected one {old[:40]!r}, found {site.count(old)}")
            site = site.replace(old, new, 1)
        args.site.parent.mkdir(parents=True, exist_ok=True)
        args.site.write_text(site, encoding="utf-8", newline=chr(10))
        print(f"[ok] site page -> {args.site}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
