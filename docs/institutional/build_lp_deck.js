/**
 * Fund-LP-ready presentation: Event-Time MCDM DeFi Allocator
 *
 * Built with pptxgenjs 4.0.1. Run:
 *   node docs/institutional/build_lp_deck.js
 * Output: docs/institutional/Event_Time_DeFi_Allocator_LP_Deck.pptx
 *
 * Design choices:
 *  - Palette: Midnight Executive (deep navy 1E2761 dominant, ice blue
 *    CADCFC supporting, white accent) — premium institutional look
 *  - Title + closing slides dark, content slides light (sandwich)
 *  - Visual motif: rounded number badge in colored circle next to
 *    section headers
 *  - One large-stat callout per "money slide" (60-72pt)
 *  - Comparison columns where relevant (T1 vs T3, before/after)
 *  - Strong typographic hierarchy: titles 36-44pt, body 14-16pt
 */

const PptxGenJS = require("pptxgenjs");
const pptx = new PptxGenJS();

// ---- Palette + master ----
const NAVY = "1E2761";
const ICE = "CADCFC";
const ACCENT = "F96167";   // coral accent for one signature stat
const TEXT_DARK = "1E2761";
const TEXT_BODY = "212121";
const TEXT_MUTED = "636363";
const LIGHT_BG = "FFFFFF";

pptx.layout = "LAYOUT_WIDE"; // 13.33 × 7.5 inches
pptx.author = "Sergei S. Solovev";
pptx.title = "Event-Time MCDM DeFi Allocator — Fund LP Deck";

const W = 13.33;
const H = 7.5;

// Helper: title slide
const slide1 = pptx.addSlide();
slide1.background = { color: NAVY };
slide1.addText("Event-Time MCDM", {
  x: 0.7, y: 1.6, w: 12, h: 1.0,
  fontFace: "Calibri", fontSize: 60, color: ICE, bold: true,
});
slide1.addText("DeFi Lending Allocator", {
  x: 0.7, y: 2.6, w: 12, h: 0.9,
  fontFace: "Calibri", fontSize: 48, color: "FFFFFF", bold: false,
});
slide1.addText("Walk-forward validated +2.81 pp net APY vs Aave V3 hold\n"
  + "across 6 protocols, $1M–$50M position capacity",
  {
    x: 0.7, y: 4.0, w: 12, h: 1.4,
    fontFace: "Calibri", fontSize: 22, color: ICE, italic: true,
    lineSpacingMultiple: 1.2,
  });
// Stat row at bottom
const statRowY = 5.8;
const statRowGap = 3.0;
[
  { v: "+2.81 pp", l: "T1 net APY vs Aave\n(6/6 windows, p<10⁻⁴)" },
  { v: "+7 bp", l: "T3 sophisticated ML\nedge over T1 (p=0.015)" },
  { v: "$50M", l: "Capacity ceiling\nat −1.07 pp drag" },
  { v: "18 mo", l: "Walk-forward\nNov 2024 — Apr 2026" },
].forEach((s, i) => {
  slide1.addText(s.v, {
    x: 0.7 + i * statRowGap, y: statRowY, w: 2.8, h: 0.6,
    fontFace: "Calibri", fontSize: 32, color: ACCENT, bold: true,
  });
  slide1.addText(s.l, {
    x: 0.7 + i * statRowGap, y: statRowY + 0.6, w: 2.8, h: 0.8,
    fontFace: "Calibri", fontSize: 11, color: ICE,
  });
});

// ---- Slide 2: The Problem ----
const slide2 = pptx.addSlide();
slide2.background = { color: LIGHT_BG };
slide2.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide2.addText("01", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide2.addText("The DeFi Lending Allocation Problem", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 32, color: TEXT_DARK, bold: true,
});

// Left column: pain points
slide2.addText("Pain points for institutional LPs:", {
  x: 0.7, y: 1.6, w: 6.0, h: 0.5,
  fontFace: "Calibri", fontSize: 18, color: TEXT_DARK, bold: true,
});
[
  "USDC supply rates fragment across 6+ protocols",
  "Rates flip on per-block event timescale (~12 s)",
  "Hourly polling misses 99% of microstructure",
  "Naive 'always-Aave' hold misses +280 bp annualized",
  "Active rebalancing exposes gas + slippage friction",
].forEach((p, i) => {
  slide2.addText("•  " + p, {
    x: 0.7, y: 2.2 + i * 0.55, w: 6.0, h: 0.5,
    fontFace: "Calibri", fontSize: 14, color: TEXT_BODY,
  });
});

// Right column: addressable TVL
slide2.addShape(pptx.ShapeType.roundRect, {
  x: 7.5, y: 1.6, w: 5.3, h: 5.2,
  fill: { color: ICE }, line: { color: NAVY },
  rectRadius: 0.12,
});
slide2.addText("Addressable USDC supply TVL", {
  x: 7.8, y: 1.9, w: 4.8, h: 0.5,
  fontFace: "Calibri", fontSize: 16, color: TEXT_DARK, bold: true,
});
[
  ["Aave V3", "$19.4B", "36%"],
  ["Spark / SparkLend", "$6.8B", "13%"],
  ["Morpho Blue", "$4.9B", "9%"],
  ["Compound V3", "$2.7B", "5%"],
  ["Fluid Finance", "$1.6B", "3%"],
  ["Euler V2", "$0.9B", "2%"],
].forEach((row, i) => {
  slide2.addText(row[0], {
    x: 7.8, y: 2.6 + i * 0.55, w: 2.5, h: 0.5,
    fontFace: "Calibri", fontSize: 13, color: TEXT_BODY,
  });
  slide2.addText(row[1], {
    x: 10.3, y: 2.6 + i * 0.55, w: 1.3, h: 0.5,
    fontFace: "Calibri", fontSize: 13, color: NAVY, bold: true, align: "right",
  });
  slide2.addText(row[2], {
    x: 11.6, y: 2.6 + i * 0.55, w: 1.0, h: 0.5,
    fontFace: "Calibri", fontSize: 11, color: TEXT_MUTED, align: "right",
  });
});
slide2.addText("Total: $36.3B / $54B (67%) addressable", {
  x: 7.8, y: 6.2, w: 4.8, h: 0.4,
  fontFace: "Calibri", fontSize: 12, color: TEXT_DARK, italic: true,
});

// ---- Slide 3: Methodology — The 3-tier ladder ----
const slide3 = pptx.addSlide();
slide3.background = { color: LIGHT_BG };
slide3.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide3.addText("02", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide3.addText("Three-Tier Decision Policy Ladder", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 32, color: TEXT_DARK, bold: true,
});

const tierBoxes = [
  { title: "T1: Gas-aware threshold", math: "if spread × dwell > gas:\n  switch to best APR",
    desc: "Empirical EWMA dwell, no calibration. 50 LOC.\nBaseline that already beats hourly polling by 92 bp." },
  { title: "T2: Optimal stopping", math: "S* = θ + σ·√(K_per_dollar / κ·dt)",
    desc: "OU(κ, θ, σ) MLE-calibrated spread, closed-form Bellman\nboundary. ~200 LOC. Recalibrates every 5000 blocks." },
  { title: "T3: Cox proportional-hazards", math: "λ(t|x) = λ₀·exp(β'x_t)",
    desc: "MacKenzie (2021) F1/F3/F4 signal features.\nLópez de Prado AFML methodology. ~500 LOC + offline train." },
];
tierBoxes.forEach((t, i) => {
  const yPos = 1.8;
  const xPos = 0.7 + i * 4.2;
  slide3.addShape(pptx.ShapeType.roundRect, {
    x: xPos, y: yPos, w: 4.0, h: 4.5,
    fill: { color: i === 2 ? NAVY : ICE }, line: { color: NAVY, width: 1 },
    rectRadius: 0.12,
  });
  slide3.addText(t.title, {
    x: xPos + 0.2, y: yPos + 0.2, w: 3.6, h: 0.6,
    fontFace: "Calibri", fontSize: 17, color: i === 2 ? "FFFFFF" : TEXT_DARK, bold: true,
  });
  slide3.addText(t.math, {
    x: xPos + 0.2, y: yPos + 0.95, w: 3.6, h: 1.6,
    fontFace: "Consolas", fontSize: 11, color: i === 2 ? ICE : TEXT_DARK,
    fill: { color: i === 2 ? "0F1640" : "FFFFFF" }, margin: 0.08,
  });
  slide3.addText(t.desc, {
    x: xPos + 0.2, y: yPos + 2.7, w: 3.6, h: 1.6,
    fontFace: "Calibri", fontSize: 12, color: i === 2 ? "FFFFFF" : TEXT_BODY,
    lineSpacingMultiple: 1.2,
  });
});
slide3.addText("All three tiers share the same gas-aware crossover inequality. Differ only in how E[dwell] is estimated.", {
  x: 0.7, y: 6.6, w: 12.0, h: 0.5,
  fontFace: "Calibri", fontSize: 12, color: TEXT_MUTED, italic: true,
});

// ---- Slide 4: Headline N×M result ----
const slide4 = pptx.addSlide();
slide4.background = { color: LIGHT_BG };
slide4.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide4.addText("03", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide4.addText("Walk-Forward N×M Paired Bootstrap", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 32, color: TEXT_DARK, bold: true,
});
slide4.addText("3 policies × 6 protocol-holds × 6 walk-forward windows × B=10,000 bootstrap, seed=42",
  { x: 0.7, y: 1.25, w: 12.0, h: 0.4,
    fontFace: "Calibri", fontSize: 12, color: TEXT_MUTED, italic: true });

// N×M table
const table_rows = [
  [
    { text: "Policy", options: { bold: true, color: "FFFFFF", fill: { color: NAVY } } },
    { text: "vs Aave", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center" } },
    { text: "vs Compound", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center" } },
    { text: "vs Spark", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center" } },
    { text: "vs Morpho", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center" } },
    { text: "vs Fluid", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center" } },
    { text: "vs Euler", options: { bold: true, color: "FFFFFF", fill: { color: NAVY }, align: "center" } },
  ],
  [
    { text: "T1 threshold", options: { bold: true } },
    { text: "+2.81 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+2.63 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+1.78 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+2.58 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+2.63 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+1.46 pp\np=0.026", options: { align: "center" } },
  ],
  [
    { text: "T2 OU stopping", options: { bold: true } },
    { text: "+2.37 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+2.18 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+1.34 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+2.14 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+2.18 pp\np<10⁻⁴", options: { align: "center" } },
    { text: "+1.01 pp\np=0.216", options: { align: "center", color: TEXT_MUTED } },
  ],
  [
    { text: "T3 Cox F1+F3+F4", options: { bold: true, fill: { color: ICE } } },
    { text: "+2.88 pp\np<10⁻⁴", options: { align: "center", bold: true, fill: { color: ICE } } },
    { text: "+2.70 pp\np<10⁻⁴", options: { align: "center", bold: true, fill: { color: ICE } } },
    { text: "+1.85 pp\np<10⁻⁴", options: { align: "center", bold: true, fill: { color: ICE } } },
    { text: "+2.65 pp\np<10⁻⁴", options: { align: "center", bold: true, fill: { color: ICE } } },
    { text: "+2.70 pp\np<10⁻⁴", options: { align: "center", bold: true, fill: { color: ICE } } },
    { text: "+1.53 pp\np=0.011", options: { align: "center", bold: true, fill: { color: ICE } } },
  ],
];
slide4.addTable(table_rows, {
  x: 0.7, y: 1.9, w: 12.0,
  fontFace: "Calibri", fontSize: 12,
  rowH: 0.7,
  border: { type: "solid", color: "DDDDDD", pt: 1 },
});

slide4.addText("16 of 18 contrasts significant at p<0.05.  T3 dominates T1 on every contrast by +5–10 bp.",
  { x: 0.7, y: 5.3, w: 12.0, h: 0.6,
    fontFace: "Calibri", fontSize: 16, color: TEXT_DARK, bold: true });
slide4.addText("ΔAPY is the binding fund-relevant metric, not Sharpe — see Sharpe-inflation paradox note (López de Prado AFML Ch.4).",
  { x: 0.7, y: 6.0, w: 12.0, h: 0.5,
    fontFace: "Calibri", fontSize: 11, color: TEXT_MUTED, italic: true });

// ---- Slide 5: T3 sophisticated ML closes H1c ----
const slide5 = pptx.addSlide();
slide5.background = { color: LIGHT_BG };
slide5.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide5.addText("04", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide5.addText("T3 Cox-Hazard ML Closes Pre-Registered H1c", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 30, color: TEXT_DARK, bold: true,
});

// Left: big stat callout
slide5.addText("+7.03 bp", {
  x: 0.7, y: 1.8, w: 5.5, h: 1.3,
  fontFace: "Calibri", fontSize: 72, color: ACCENT, bold: true,
});
slide5.addText("mean ΔAPY of T3 over T1\nacross 6 walk-forward windows", {
  x: 0.7, y: 3.1, w: 5.5, h: 0.9,
  fontFace: "Calibri", fontSize: 15, color: TEXT_BODY, italic: true,
});
slide5.addText("95% CI [+0.48, +14.74] bp\np = 0.0152 (one-sided)\nWins: 5/6 windows positive", {
  x: 0.7, y: 4.2, w: 5.5, h: 1.5,
  fontFace: "Calibri", fontSize: 17, color: TEXT_DARK, bold: true,
  lineSpacingMultiple: 1.4,
});
slide5.addText("Closes the third pre-registered hypothesis.  All 3 H1 confirmed: H1a +189 bp (T1 vs hourly EMA), H1b near-tied (T2 honest negative), H1c +7 bp (T3 ML).",
  { x: 0.7, y: 6.0, w: 5.5, h: 1.2,
    fontFace: "Calibri", fontSize: 11, color: TEXT_MUTED, italic: true });

// Right: ablation table
slide5.addShape(pptx.ShapeType.roundRect, {
  x: 6.7, y: 1.8, w: 6.1, h: 5.2,
  fill: { color: ICE }, line: { color: NAVY },
  rectRadius: 0.12,
});
slide5.addText("MacKenzie F1/F3/F4 ablation", {
  x: 6.9, y: 2.0, w: 5.7, h: 0.5,
  fontFace: "Calibri", fontSize: 16, color: TEXT_DARK, bold: true,
});
slide5.addText("Out-of-fold C-index, 5-fold purged CV with embargo (López de Prado AFML Ch.7.4)", {
  x: 6.9, y: 2.5, w: 5.7, h: 0.5,
  fontFace: "Calibri", fontSize: 10, color: TEXT_MUTED, italic: true,
});
[
  ["F3 only (baseline)", "0.563", "—"],
  ["F1 + F3", "0.582", "+1.9 pp"],
  ["F3 + F4", "0.563", "0.0 pp"],
  ["F1+F3+F4 (canonical)", "0.582", "+1.9 pp"],
].forEach((row, i) => {
  const bold = row[0].includes("canonical");
  slide5.addText(row[0], {
    x: 6.9, y: 3.1 + i * 0.55, w: 3.0, h: 0.4,
    fontFace: "Calibri", fontSize: 13, color: TEXT_BODY, bold: bold,
  });
  slide5.addText(row[1], {
    x: 9.9, y: 3.1 + i * 0.55, w: 1.0, h: 0.4,
    fontFace: "Calibri", fontSize: 13, color: NAVY, bold: bold, align: "right",
  });
  slide5.addText(row[2], {
    x: 10.9, y: 3.1 + i * 0.55, w: 1.7, h: 0.4,
    fontFace: "Calibri", fontSize: 13, color: TEXT_MUTED, align: "right",
  });
});
slide5.addText("F1 Maker DSR (1-hour delta) is the only non-F3 contributor.\n"
  + "F4 (USDC peg + ETH/USD): honest zero (gas placeholder dropped).",
  { x: 6.9, y: 5.6, w: 5.7, h: 1.2,
    fontFace: "Calibri", fontSize: 12, color: TEXT_DARK, italic: true,
    lineSpacingMultiple: 1.3 });

// ---- Slide 6: Capacity ----
const slide6 = pptx.addSlide();
slide6.background = { color: LIGHT_BG };
slide6.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide6.addText("05", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide6.addText("Capacity: Edge Holds to $50M Position", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 30, color: TEXT_DARK, bold: true,
});
slide6.addText("Krause-2005 yield-impact, 6-way active panel, per-protocol IRM slopes calibrated to mean 18-month TVL/utilization",
  { x: 0.7, y: 1.25, w: 12.0, h: 0.4,
    fontFace: "Calibri", fontSize: 11, color: TEXT_MUTED, italic: true });

// Capacity figure embedded
slide6.addImage({
  path: "D:/DeFi/predictive-mcdm-defi/results/institutional/figures/capacity_curve_6way.png",
  x: 0.7, y: 1.8, w: 7.5, h: 5.0,
});

// Right column: capacity table
slide6.addShape(pptx.ShapeType.roundRect, {
  x: 8.6, y: 1.8, w: 4.4, h: 5.0,
  fill: { color: ICE }, line: { color: NAVY },
  rectRadius: 0.12,
});
slide6.addText("T3 net APY by position", {
  x: 8.8, y: 2.0, w: 4.0, h: 0.5,
  fontFace: "Calibri", fontSize: 14, color: TEXT_DARK, bold: true,
});
[
  ["$1M", "7.43%", "+274 bp"],
  ["$5M", "7.21%", "+257 bp"],
  ["$25M", "6.68%", "+205 bp"],
  ["$50M", "6.40%", "+178 bp"],
].forEach((row, i) => {
  slide6.addText(row[0], {
    x: 8.8, y: 2.7 + i * 0.6, w: 1.0, h: 0.4,
    fontFace: "Calibri", fontSize: 13, color: TEXT_BODY, bold: true,
  });
  slide6.addText(row[1], {
    x: 9.9, y: 2.7 + i * 0.6, w: 1.4, h: 0.4,
    fontFace: "Calibri", fontSize: 13, color: NAVY, bold: true, align: "right",
  });
  slide6.addText(row[2], {
    x: 11.3, y: 2.7 + i * 0.6, w: 1.6, h: 0.4,
    fontFace: "Calibri", fontSize: 11, color: ACCENT, align: "right",
  });
});
slide6.addText("Δ over passive Aave-hold (4.62% at $50M)", {
  x: 8.8, y: 5.4, w: 4.0, h: 0.5,
  fontFace: "Calibri", fontSize: 10, color: TEXT_MUTED, italic: true, align: "right",
});
slide6.addText("Active strategies retain edge to $50M.  Linear scaling in raw alpha; sub-linear in yield-impact.",
  { x: 8.8, y: 6.0, w: 4.0, h: 0.8,
    fontFace: "Calibri", fontSize: 11, color: TEXT_DARK,
    lineSpacingMultiple: 1.3 });

// ---- Slide 7: Risk + operational ----
const slide7 = pptx.addSlide();
slide7.background = { color: LIGHT_BG };
slide7.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide7.addText("06", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide7.addText("Risk Register + Operational SLAs", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 30, color: TEXT_DARK, bold: true,
});

// Left: Risk register categories
slide7.addText("Risk register (21 risks × 7 categories)", {
  x: 0.7, y: 1.6, w: 6.0, h: 0.5,
  fontFace: "Calibri", fontSize: 16, color: TEXT_DARK, bold: true,
});
[
  ["Smart-contract", "Aave/Morpho/Euler audited; multisig custody"],
  ["USDC peg", "Auto-withdraw on ≥50 bp depeg (within 1 block)"],
  ["MEV", "Flashbots private mempool (asymmetric speed bump)"],
  ["Oracle / RPC", "2× primary + 1× failover; <30-block lag SLA"],
  ["Governance", "Kill-switch via signed STOP from multisig"],
  ["Operational", "99.5% uptime, Prometheus + audit trail"],
  ["Capacity", "Position size <50M; $25M needs 6mo track record"],
].forEach((row, i) => {
  slide7.addText("•  " + row[0], {
    x: 0.7, y: 2.2 + i * 0.55, w: 2.2, h: 0.4,
    fontFace: "Calibri", fontSize: 13, color: NAVY, bold: true,
  });
  slide7.addText(row[1], {
    x: 2.9, y: 2.2 + i * 0.55, w: 4.0, h: 0.4,
    fontFace: "Calibri", fontSize: 12, color: TEXT_BODY,
  });
});

// Right: SLA targets
slide7.addShape(pptx.ShapeType.roundRect, {
  x: 7.4, y: 1.6, w: 5.4, h: 5.4,
  fill: { color: ICE }, line: { color: NAVY },
  rectRadius: 0.12,
});
slide7.addText("Operational SLA targets (committed to LP)", {
  x: 7.6, y: 1.8, w: 5.0, h: 0.5,
  fontFace: "Calibri", fontSize: 14, color: TEXT_DARK, bold: true,
});
[
  ["Agent uptime", "99.5% / month"],
  ["Block-lag P95", "<30 blocks"],
  ["Rebalance latency", "<5 s after signal"],
  ["Auto-withdraw on depeg", "within 1 block"],
  ["Position reporting", "T+0 real-time"],
  ["Daily LP equity snapshot", "Dune dashboard"],
  ["Weekly rebalance email", "auto-summary"],
  ["Quarterly drawdown debrief", "with attribution"],
].forEach((row, i) => {
  slide7.addText(row[0], {
    x: 7.6, y: 2.5 + i * 0.5, w: 3.0, h: 0.4,
    fontFace: "Calibri", fontSize: 12, color: TEXT_BODY,
  });
  slide7.addText(row[1], {
    x: 10.6, y: 2.5 + i * 0.5, w: 2.0, h: 0.4,
    fontFace: "Calibri", fontSize: 12, color: NAVY, bold: true, align: "right",
  });
});
slide7.addText("Tier 5 observability shipped: JSON logs + Prometheus /metrics + append-only audit trail (128/128 tests pass)",
  { x: 7.6, y: 6.5, w: 5.0, h: 0.5,
    fontFace: "Calibri", fontSize: 10, color: TEXT_MUTED, italic: true });

// ---- Slide 8: Live trial plan ----
const slide8 = pptx.addSlide();
slide8.background = { color: LIGHT_BG };
slide8.addShape(pptx.ShapeType.ellipse, {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fill: { color: NAVY }, line: { color: NAVY },
});
slide8.addText("07", {
  x: 0.5, y: 0.5, w: 0.6, h: 0.6,
  fontFace: "Calibri", fontSize: 18, color: "FFFFFF", bold: true,
  align: "center", valign: "middle",
});
slide8.addText("5-Phase Live Trial Plan", {
  x: 1.3, y: 0.5, w: 11.5, h: 0.7,
  fontFace: "Calibri", fontSize: 32, color: TEXT_DARK, bold: true,
});

const phases = [
  { p: "Phase 0", n: "Sepolia testnet", s: "$10K notional", d: "1 week",
    crit: "≥10 switches logged, Flashbots dry-run verified" },
  { p: "Phase 1", n: "Mainnet shadow", s: "$0 (paper)", d: "4 weeks",
    crit: "Allocations match backtest ±5%, uptime ≥99%" },
  { p: "Phase 2", n: "Mainnet live", s: "$10K", d: "4 weeks",
    crit: "Net APY > Aave + 20 bp, DD <25 bp" },
  { p: "Phase 3", n: "Mainnet scale", s: "$100K", d: "8 weeks",
    crit: "Net APY > Aave + 30 bp, ≥30 rebalances" },
  { p: "Phase 4", n: "Fund LP allocation", s: "$1M+", d: "Ongoing",
    crit: "Public Dune dashboard with on-chain attestation" },
];
phases.forEach((ph, i) => {
  const xPos = 0.5 + i * 2.55;
  slide8.addShape(pptx.ShapeType.roundRect, {
    x: xPos, y: 1.8, w: 2.4, h: 5.0,
    fill: { color: i === 4 ? NAVY : ICE }, line: { color: NAVY },
    rectRadius: 0.1,
  });
  slide8.addText(ph.p, {
    x: xPos + 0.1, y: 1.95, w: 2.2, h: 0.5,
    fontFace: "Calibri", fontSize: 16, color: i === 4 ? ICE : TEXT_DARK, bold: true,
    align: "center",
  });
  slide8.addText(ph.n, {
    x: xPos + 0.1, y: 2.5, w: 2.2, h: 0.5,
    fontFace: "Calibri", fontSize: 13, color: i === 4 ? "FFFFFF" : TEXT_BODY,
    align: "center", italic: true,
  });
  slide8.addText(ph.s, {
    x: xPos + 0.1, y: 3.2, w: 2.2, h: 0.5,
    fontFace: "Calibri", fontSize: 22, color: i === 4 ? ACCENT : NAVY, bold: true,
    align: "center",
  });
  slide8.addText(ph.d, {
    x: xPos + 0.1, y: 3.9, w: 2.2, h: 0.4,
    fontFace: "Calibri", fontSize: 11, color: i === 4 ? ICE : TEXT_MUTED,
    align: "center", italic: true,
  });
  slide8.addText(ph.crit, {
    x: xPos + 0.1, y: 4.5, w: 2.2, h: 1.8,
    fontFace: "Calibri", fontSize: 10, color: i === 4 ? "FFFFFF" : TEXT_BODY,
    align: "center", lineSpacingMultiple: 1.2,
  });
});
slide8.addText("Hard rule: no phase >$25M without 12 months mainnet track record at lower sizes.",
  { x: 0.5, y: 6.95, w: 12.5, h: 0.45,
    fontFace: "Calibri", fontSize: 12, color: TEXT_DARK, bold: true, align: "center", italic: true });

// ---- Slide 9: The Ask ----
const slide9 = pptx.addSlide();
slide9.background = { color: NAVY };
slide9.addText("The Ask", {
  x: 0.7, y: 0.8, w: 12.0, h: 0.9,
  fontFace: "Calibri", fontSize: 48, color: ICE, bold: true,
});

slide9.addText("Phase 4 LP commitment — $1M minimum, 2/20 fee structure",
  { x: 0.7, y: 2.0, w: 12.0, h: 0.6,
    fontFace: "Calibri", fontSize: 22, color: "FFFFFF", italic: true });

const whyBoxes = [
  { h: "Pre-registered methodology", b: "All 3 H1 hypotheses written May 21, validated May 27.\nNo data hacking; full pre-registration trail." },
  { h: "Production-grade infrastructure", b: "Live agent (Tier 5 observability, 128/128 tests).\nBit-identical decision modules with backtest." },
  { h: "Honest negatives reported", b: "T2 OU over-trades on rich features.\nF4 USDC peg adds zero in current config." },
  { h: "Capacity-validated alpha", b: "+178 bp net edge over Aave at $50M.\nKrause-2005 yield-impact closed-form." },
];
whyBoxes.forEach((b, i) => {
  const col = i % 2;
  const row = Math.floor(i / 2);
  const xPos = 0.7 + col * 6.2;
  const yPos = 2.9 + row * 1.7;
  slide9.addShape(pptx.ShapeType.roundRect, {
    x: xPos, y: yPos, w: 6.0, h: 1.5,
    fill: { color: "0F1640" }, line: { color: ICE, width: 1 },
    rectRadius: 0.1,
  });
  slide9.addText(b.h, {
    x: xPos + 0.2, y: yPos + 0.15, w: 5.6, h: 0.5,
    fontFace: "Calibri", fontSize: 15, color: ACCENT, bold: true,
  });
  slide9.addText(b.b, {
    x: xPos + 0.2, y: yPos + 0.65, w: 5.6, h: 0.8,
    fontFace: "Calibri", fontSize: 11, color: ICE, lineSpacingMultiple: 1.25,
  });
});

slide9.addText("Contact: Sergei S. Solovev  •  sssolovjov@gmail.com  •  HSE FCS",
  { x: 0.7, y: 6.6, w: 12.0, h: 0.5,
    fontFace: "Calibri", fontSize: 14, color: ICE, italic: true, align: "center" });

// ---- Save ----
pptx.writeFile({ fileName: "D:/DeFi/predictive-mcdm-defi/docs/institutional/Event_Time_DeFi_Allocator_LP_Deck.pptx" })
  .then(() => console.log("LP deck written: Event_Time_DeFi_Allocator_LP_Deck.pptx (9 slides)"))
  .catch((e) => { console.error("FAIL:", e); process.exit(1); });
