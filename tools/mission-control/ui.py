"""Rendering layer for Mission Control v2 — atoms, CSS, and the page shell.

Every color, font size, and radius is a literal from design/design-system.md
(tokens contentHash 288d9538). Additions are proposed in the mockups README,
never invented here. Direction: "flight strips" (mockup C) — one run, one row,
grouped by who owes the next move; the 7-stage pipeline is a rail in each row.
"""

import html

H = html.escape

# Fallback note: ADAM.CG PRO is licensed and not vendored — degrades to Figtree
# caps with wide tracking (mockups README §4.1). Figtree + JetBrains Mono come
# from Google Fonts; the tool is Tailscale-only but browsers have internet.
FONTS = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
    "<link href='https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700"
    "&family=JetBrains+Mono:wght@400;500&display=swap' rel='stylesheet'>"
)

CSS = """
:root{
  --surface-0:#0A0A0C; --surface-1:#121216; --surface-2:#191920; --surface-3:#22222A;
  --edge:#24242C; --edge-top:rgb(255 255 255 / 5.5%);
  --text:#E8E8EC; --text-muted:#8E8E98; --text-dim:#6C6C76;
  --accent:#F2C57F; --accent-soft:#2C2113; --on-accent:#08080A;
  --success:#43C67E; --success-soft:#12301F;
  --warning:#E7935A; --warning-soft:#2E1E16;
  --danger:#E5705F;
  --gold-deep:#8C6A2F; --gold-light:#C9B183;
  --night-1:#46565F; --night-2:#5C6E77; --night-3:#7B8A90;
  --dawn-1:#C77A4E; --dawn-2:#D89A5E; --dawn-3:#E8B570; --dawn-4:#F2C77E;
  --font-ui:'Figtree','Segoe UI',system-ui,sans-serif;
  --font-mono:'JetBrains Mono','Cascadia Mono',Consolas,monospace;
  --font-label:'ADAM.CG PRO','Figtree','Segoe UI',system-ui,sans-serif;
  --text-caps:11px; --text-xs:13px; --text-sm:14px; --text-base:15px;
  --text-md:16px; --text-lg:20px; --text-xl:28px;
  --r-sm:6px; --r-md:12px; --r-lg:16px; --r-pill:999px;
}
*{box-sizing:border-box}
html,body{margin:0;background:var(--surface-0);color:var(--text);
  font-family:var(--font-ui);font-size:var(--text-base);line-height:1.5;
  -webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
.mono{font-family:var(--font-mono);font-variant-numeric:tabular-nums slashed-zero;
  font-feature-settings:"tnum" 1,"zero" 1}
.caps{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text-muted)}

/* ── shell: one slim top bar, nothing else ────────────────────────────── */
.topbar{display:flex;align-items:center;gap:30px;padding:15px 28px;
  border-bottom:1px solid var(--edge)}
.topbar .wordmark{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.24em;font-size:var(--text-xs);color:var(--gold-light)}
.topbar nav{display:flex;gap:24px}
.topbar nav a{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.13em;font-size:var(--text-caps);color:var(--text-muted);
  padding:6px 0 5px;border-bottom:2px solid transparent}
.topbar nav a.on{color:var(--text);border-bottom-color:var(--accent)}
.topbar nav a:hover{color:var(--text)}
.topbar .right{margin-left:auto;display:flex;align-items:center;gap:16px;
  font-size:var(--text-xs);color:var(--text-muted)}
.topbar .right .live{display:inline-flex;align-items:center;gap:8px;color:var(--text)}
.topbar .right .live.stale{color:var(--danger)}
.topbar .right .live.stale .dot{background:var(--danger);box-shadow:none}
.topbar .right a{color:var(--text-muted);text-decoration:underline;
  text-underline-offset:3px}
.topbar .right a:hover{color:var(--text)}
.page{padding:0 28px 44px}

/* one-line status bar under the top bar (board only) */
.statusline{display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  padding:13px 28px;border-bottom:1px solid var(--edge);
  font-size:var(--text-xs);color:var(--text-muted)}
.statusline b{color:var(--text);font-weight:600}
.statusline .num{font-family:var(--font-mono);font-variant-numeric:tabular-nums;
  color:var(--text);font-size:var(--text-xs)}
.statusline .sep{color:var(--text-dim)}
.statusline .warn{color:var(--warning)}
.statusline .bad{color:var(--danger)}

/* ── atoms ────────────────────────────────────────────────────────────── */
.dot{width:6px;height:6px;border-radius:var(--r-pill);display:inline-block;
  vertical-align:middle;flex:0 0 auto}
.dot.live{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}
.dot.gate{background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.dot.fail{background:var(--danger)}
.dot.idle{background:var(--text-dim)}
.chip{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;
  border:1px solid var(--edge);border-radius:var(--r-pill);
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);color:var(--text-muted);background:var(--surface-2);
  white-space:nowrap}
.chip.blocked{color:var(--danger);border-color:#3A211E;background:#231517}
.chip.gate{color:var(--accent);border-color:#3A2D18;background:var(--accent-soft)}
.chip.ok{color:var(--success);border-color:#1B3D28;background:var(--success-soft)}
.chip.warn{color:var(--warning);border-color:#3A2A1E;background:var(--warning-soft)}
.btn{display:inline-block;font-family:var(--font-ui);font-size:var(--text-sm);
  font-weight:600;padding:9px 16px;border-radius:var(--r-sm);cursor:pointer;
  border:1px solid var(--edge);background:var(--surface-3);color:var(--text)}
.btn.primary{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}
.btn.danger{background:transparent;border-color:#3A211E;color:var(--danger)}
input[type=text],input[type=password]{background:var(--surface-0);color:var(--text);
  border:1px solid var(--edge);border-radius:var(--r-sm);padding:8px 11px;
  font-family:var(--font-ui);font-size:var(--text-sm)}
input::placeholder{color:var(--text-dim)}

/* progress = ordered quantity → night→dawn ramp; accent stays scarce */
.srail{display:flex;width:100%;gap:2px;height:4px;border-radius:var(--r-pill);
  overflow:hidden}
.srail i{flex:1;background:var(--surface-3)}
.srail i.done{background:var(--night-2)}
.srail i.now{background:var(--dawn-4)}
.srail i.fail{background:var(--danger)}
.srail.tall{height:6px}

/* ── the board: five ticket columns, Fredrin-style ────────────────────── */
.kb{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:16px;
  padding:22px 28px 44px;align-items:start}
.kbcol{min-width:0}
.kbhead{display:flex;align-items:baseline;gap:9px;padding:2px 2px 10px;
  border-bottom:1px solid var(--edge);margin-bottom:12px}
.kbhead .n{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.14em;font-size:var(--text-xs);color:var(--text-muted)}
.kbhead .c{font-family:var(--font-mono);font-size:var(--text-xs);
  color:var(--text-dim);font-variant-numeric:tabular-nums}
.kbhead.hot{border-bottom-color:var(--accent)}
.kbhead.hot .n{color:var(--accent)} .kbhead.hot .c{color:var(--accent)}
.kbempty{font-size:var(--text-xs);color:var(--text-dim);line-height:1.55;
  padding:2px 2px 0}
.kcard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-md);
  padding:13px 14px;margin-bottom:12px}
.kcard.hot{background:var(--surface-2);border-color:#2E2A22}
.kcard.dim{opacity:.6}
.kcard .title{display:block;font-size:var(--text-sm);font-weight:600;
  color:var(--text);line-height:1.35;overflow-wrap:anywhere}
.kcard .title:hover{color:var(--dawn-3)}
.kcard .meta{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--text-dim);margin-top:2px;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}
.kcard .chips{display:flex;flex-wrap:wrap;gap:5px;margin:10px 0 0}
.kcard .stg{display:flex;align-items:center;justify-content:space-between;
  gap:8px;margin:11px 0 6px}
.kcard .stg .lab{font-size:var(--text-caps);color:var(--text-muted);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kcard .stg .age{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--dawn-3);font-variant-numeric:tabular-nums;white-space:nowrap}
.kcard .stg .age.cold{color:var(--text-dim)}
.kcard .wl{font-size:var(--text-xs);color:var(--text-muted);line-height:1.5;
  margin-top:8px}
.kcard .wl b{color:var(--text);font-weight:600}
.kcard .kerr{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--danger);margin-top:8px;line-height:1.5;overflow-wrap:anywhere;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden}
.kcard .foot{display:flex;align-items:baseline;justify-content:space-between;
  gap:8px;margin-top:11px;padding-top:9px;border-top:1px solid var(--edge);
  font-family:var(--font-mono);font-size:var(--text-caps);color:var(--text-dim)}
.kcard .foot .m{font-size:var(--text-xs);color:var(--text)}
.kcard .acts{display:flex;gap:8px;align-items:center;margin-top:11px}
.kcard .acts form{display:inline}
.btn.sm{padding:6px 12px;font-size:var(--text-xs)}
.kcard .acts .ev{font-size:var(--text-caps);color:var(--text-muted);
  text-decoration:underline;text-underline-offset:3px;margin-left:auto}
.kcard .acts .ev:hover{color:var(--text)}

/* ── board readout ────────────────────────────────────────────────────── */
.readout{display:grid;grid-template-columns:repeat(5,1fr) auto;gap:1px;
  background:var(--edge);border-bottom:1px solid var(--edge);margin:0 -32px}
.readout>div{background:var(--surface-0);padding:18px 26px 16px}
.readout .v{font-family:var(--font-mono);font-size:var(--text-xl);line-height:1;
  font-variant-numeric:tabular-nums;margin:7px 0 5px}
.readout .v small{font-size:var(--text-sm);color:var(--text-dim)}
.readout .d{font-size:var(--text-xs);color:var(--text-muted)}
.readout .v.act{color:var(--accent)}
.readout .v.bad{color:var(--danger)}
.readout .cta{display:flex;align-items:center;padding:18px 32px 16px}

/* headline + gate-age panel */
.saidrow{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:52px;
  padding:22px 0 20px;border-bottom:1px solid var(--edge);align-items:start}
.saidrow.noages{grid-template-columns:1fr}
.said h1{font-size:var(--text-lg);font-weight:600;margin:0 0 6px;letter-spacing:-.01em}
.said p{font-size:var(--text-sm);line-height:1.6;color:var(--text-muted);margin:0;
  max-width:96ch}
.said b{color:var(--text);font-weight:600}
.said em{font-style:normal;color:var(--danger)}
.ages{border-left:1px solid var(--edge);padding-left:24px}
.ages .row{display:flex;justify-content:space-between;align-items:baseline;
  gap:12px;padding:5px 0;font-size:var(--text-xs);color:var(--text-muted)}
.ages .row b{font-family:var(--font-mono);font-weight:400;color:var(--text);
  font-variant-numeric:tabular-nums;white-space:nowrap}
.ages .bar{height:3px;background:var(--surface-3);border-radius:var(--r-pill);
  margin:9px 0 4px;overflow:hidden}
.ages .bar i{display:block;height:100%;background:var(--dawn-2)}
.ages .split{border-top:1px solid var(--edge);margin-top:6px;padding-top:9px}

/* ── strip groups ─────────────────────────────────────────────────────── */
.grp{display:flex;align-items:baseline;gap:12px;padding:26px 0 9px}
.grp .n{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text)}
.grp .c{font-family:var(--font-mono);font-size:var(--text-caps);color:var(--text-dim)}
.grp .rule{flex:1;height:1px;background:var(--edge)}
.grp .note{font-size:var(--text-xs);color:var(--text-dim)}
.grp.hot .n{color:var(--accent)}

.stripwrap{overflow-x:auto}
.hdr,.strip{display:grid;min-width:1150px;
  grid-template-columns:14px minmax(225px,1.5fr) 138px 112px minmax(195px,1.4fr) 78px 100px 130px 64px 16px;
  gap:14px;align-items:center}
.hdr{padding:0 12px 8px;font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.12em;font-size:var(--text-caps);color:var(--text-dim)}
.hdr .r{text-align:right}
.strip{padding:13px 12px;border-radius:var(--r-sm);border:1px solid transparent;
  border-bottom:1px solid var(--edge)}
.strip:hover{background:var(--surface-1)}
.strip.hot{background:var(--surface-2);border-color:#2E2A22;border-radius:var(--r-md);
  margin-bottom:6px}
.strip.hot:hover{background:var(--surface-3)}
.strip.dim{opacity:.62}
.strip .id{display:block;font-family:var(--font-mono);font-size:var(--text-xs);
  color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.strip .sub{display:block;font-size:var(--text-caps);color:var(--text-dim);
  margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.strip .st .lab{font-size:var(--text-caps);color:var(--text-muted);
  display:block;margin-bottom:6px;white-space:nowrap}
.strip .wait{font-size:var(--text-xs);color:var(--text-muted);line-height:1.45;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.strip .wait b{color:var(--text);font-weight:600}
.strip .wait .why{display:block;font-size:var(--text-caps);color:var(--text-dim);
  margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.strip .t{font-family:var(--font-mono);font-size:var(--text-xs);text-align:right;
  font-variant-numeric:tabular-nums;color:var(--dawn-3);white-space:nowrap}
.strip .t.cold{color:var(--text-dim)}
.strip .mdl{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--text-muted);text-align:right;line-height:1.45}
.strip .mdl span{color:var(--text-dim);display:block}
.strip .tok{font-family:var(--font-mono);font-size:var(--text-caps);text-align:right;
  color:var(--text-muted);font-variant-numeric:tabular-nums;line-height:1.45}
.strip .tok span{color:var(--text-dim);display:block}
.strip .money{font-family:var(--font-mono);font-size:var(--text-sm);text-align:right;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.strip .go{color:var(--text-dim);text-align:right;font-size:var(--text-xs)}
.strip.hot .go{color:var(--accent)}

.empty{padding:11px 12px 12px;font-size:var(--text-xs);color:var(--text-dim);
  border-bottom:1px solid var(--edge);line-height:1.55}
.empty b{color:var(--text-muted);font-weight:600}
.empty code{font-family:var(--font-mono);color:var(--text-muted)}

/* attempt / retry feed */
.feed{margin-top:34px;border-top:1px solid var(--edge);padding-top:20px}
.feed .th{display:flex;justify-content:space-between;align-items:baseline;
  margin-bottom:6px}
.att{display:grid;grid-template-columns:106px 220px 1fr 100px;gap:16px;
  padding:11px 12px;border-bottom:1px solid var(--edge);font-size:var(--text-xs);
  align-items:center}
.att:last-child{border-bottom:0}
.att .tm{font-family:var(--font-mono);color:var(--text-dim);white-space:nowrap}
.att .rn{font-family:var(--font-mono);color:var(--text-muted);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.att .er{font-family:var(--font-mono);font-size:var(--text-caps);color:var(--danger);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.att .er.ok{color:var(--success)}
.att .at{text-align:right;font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.11em;font-size:var(--text-caps);color:var(--text-dim);
  white-space:nowrap}

/* ── gate cards ───────────────────────────────────────────────────────── */
.gcard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-lg);
  padding:20px 22px;margin:16px 0}
.gcard .ghead{display:flex;align-items:flex-start;justify-content:space-between;
  gap:16px;flex-wrap:wrap}
.gcard .ghead h2{font-size:var(--text-md);font-weight:600;margin:2px 0 3px}
.gcard .ghead .gid{font-family:var(--font-mono);font-size:var(--text-xs);
  color:var(--text-muted)}
.gcard .ghead .gage{font-family:var(--font-mono);font-size:var(--text-xs);
  color:var(--dawn-3);text-align:right;white-space:nowrap}
.gcard .gdesc{font-size:var(--text-xs);color:var(--text-muted);margin:6px 0 0;
  max-width:92ch}
.blockwarn{border:1px solid #3A211E;background:#231517;border-radius:var(--r-md);
  padding:12px 15px;margin:14px 0 4px;font-size:var(--text-xs);line-height:1.55;
  color:var(--text-muted)}
.blockwarn b{color:var(--danger);font-weight:600}
.blockwarn .q{display:block;margin-top:6px;color:var(--text);font-style:italic}
.gopts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:14px;margin:16px 0 4px}
.gopt{background:var(--surface-0);border:1px solid var(--edge);
  border-radius:var(--r-md);padding:12px}
.gopt.rec{border-color:#3A2D18}
.gopt .on{display:flex;align-items:baseline;justify-content:space-between;gap:8px;
  margin-bottom:4px}
.gopt .on b{font-size:var(--text-sm);font-weight:600}
.gopt .axis{font-size:var(--text-caps);color:var(--text-dim);line-height:1.5;
  margin-bottom:10px}
.gopt img{width:100%;border:1px solid var(--edge);border-radius:var(--r-sm);
  background:var(--surface-0);display:block}
.gmeta{display:flex;gap:18px;flex-wrap:wrap;margin:12px 0 0;
  font-family:var(--font-mono);font-size:var(--text-caps);color:var(--text-dim)}
.gmeta b{color:var(--text-muted);font-weight:400}
.gact{display:flex;gap:10px;align-items:center;margin-top:16px;
  padding-top:14px;border-top:1px solid var(--edge);flex-wrap:wrap}
.gact input{flex:1;min-width:220px}
.decided .att{grid-template-columns:106px 240px 1fr 130px}

/* rendered markdown reports */
.prose{font-size:var(--text-sm);line-height:1.65;color:var(--text);max-width:92ch}
.prose h1{font-size:var(--text-md);margin:18px 0 6px}
.prose h2{font-size:var(--text-sm);font-weight:700;margin:16px 0 4px}
.prose h3{font-size:var(--text-sm);font-weight:600;margin:12px 0 3px;
  color:var(--text-muted)}
.prose p,.prose li{color:var(--text-muted)}
.prose strong{color:var(--text)}
.prose code{font-family:var(--font-mono);font-size:var(--text-xs);
  background:var(--surface-2);border-radius:4px;padding:1px 5px}
.prose pre{background:var(--surface-0);border:1px solid var(--edge);
  border-radius:var(--r-sm);padding:10px 12px;overflow-x:auto}
.prose pre code{background:none;padding:0}
.prose table{border-collapse:collapse;margin:8px 0}
.prose th,.prose td{border:1px solid var(--edge);padding:5px 9px;
  font-size:var(--text-xs);color:var(--text-muted);text-align:left}
.prose th{color:var(--text)}
.prose a{color:var(--dawn-3);text-decoration:underline;text-underline-offset:3px}
details.report{border:1px solid var(--edge);border-radius:var(--r-md);
  background:var(--surface-0);margin:12px 0 0}
details.report summary{cursor:pointer;padding:10px 14px;font-size:var(--text-xs);
  color:var(--text-muted);font-weight:600}
details.report[open] summary{border-bottom:1px solid var(--edge)}
details.report .prose{padding:6px 18px 16px}

/* ── run detail ───────────────────────────────────────────────────────── */
.runhead{padding:24px 0 18px;border-bottom:1px solid var(--edge);
  display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;
  align-items:flex-start}
.runhead h1{font-family:var(--font-mono);font-size:var(--text-lg);font-weight:400;
  margin:4px 0 8px}
.runhead .meta{font-size:var(--text-xs);color:var(--text-muted);line-height:1.7}
.runhead .meta code{font-family:var(--font-mono);color:var(--text-muted)}
.runhead .totals{text-align:right}
.runhead .totals .v{font-family:var(--font-mono);font-size:var(--text-xl);
  line-height:1.1}
.runhead .totals .d{font-size:var(--text-caps);color:var(--text-dim);
  font-family:var(--font-mono);margin-top:4px;line-height:1.5}
.scard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-lg);
  padding:16px 18px;margin:12px 0}
.scard.cur{background:var(--surface-2);border-color:#2E2A22}
.scard.pend{opacity:.55}
.scard .shead{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.scard .shead .nm{font-size:var(--text-sm);font-weight:600}
.scard .shead .actor{font-size:var(--text-caps);color:var(--text-dim)}
.scard .shead .right{margin-left:auto;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);text-align:right;line-height:1.5}
.scard .sdesc{font-size:var(--text-caps);color:var(--text-dim);margin:5px 0 0}
.scard .err{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--danger);background:#231517;border:1px solid #3A211E;
  border-radius:var(--r-sm);padding:8px 11px;margin:10px 0 0;
  overflow-wrap:anywhere}
.tries{margin:10px 0 0;font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--text-dim);line-height:1.8}
.tries .ok{color:var(--success)} .tries .bad{color:var(--danger)}
.arts{margin:10px 0 0;font-size:var(--text-xs)}
.arts a{color:var(--dawn-3);text-decoration:underline;text-underline-offset:3px;
  margin-right:14px}
.evt{display:grid;grid-template-columns:120px 200px 1fr;gap:16px;
  padding:8px 12px;border-bottom:1px solid var(--edge);font-size:var(--text-xs);
  align-items:baseline}
.evt:last-child{border-bottom:0}
.evt .tm{font-family:var(--font-mono);color:var(--text-dim);white-space:nowrap}
.evt .ac{font-family:var(--font-mono);color:var(--text-muted);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.evt .ty{color:var(--text-muted)}
.evt .ty b{color:var(--text);font-weight:600}
.evt .ty span{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--text-dim);display:block;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap}

/* ── spend ────────────────────────────────────────────────────────────── */
.spendtbl{width:100%;border-collapse:collapse;margin-top:6px}
.spendtbl th{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.12em;font-size:var(--text-caps);color:var(--text-dim);
  text-align:left;padding:0 14px 8px 0;font-weight:400}
.spendtbl th.r,.spendtbl td.r{text-align:right}
.spendtbl td{padding:9px 14px 9px 0;border-top:1px solid var(--edge);
  font-size:var(--text-xs);color:var(--text-muted);
  font-family:var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
.spendtbl td.d{font-family:var(--font-ui);color:var(--text)}
.spendtbl td .bar{width:150px;height:5px;background:var(--surface-3);
  border-radius:var(--r-pill);overflow:hidden;display:inline-block;
  vertical-align:middle}
.spendtbl td .bar i{display:block;height:100%;background:var(--dawn-2)}
.spendtbl td .bar i.over{background:var(--danger)}
.footnote{font-size:var(--text-caps);color:var(--text-dim);margin-top:14px;
  line-height:1.6}

/* ── login ────────────────────────────────────────────────────────────── */
.login{max-width:360px;margin:16vh auto 0;background:var(--surface-1);
  border:1px solid var(--edge);border-top:1px solid var(--edge-top);
  border-radius:var(--r-lg);padding:30px 28px;text-align:center}
.login .logo{width:34px;height:34px;border-radius:var(--r-pill);
  border:1.5px solid var(--gold-light);margin:0 auto 14px}
.login h1{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.16em;font-size:var(--text-sm);font-weight:400;margin:0 0 6px}
.login p{font-size:var(--text-xs);color:var(--text-muted);margin:0 0 18px}
.login input{width:100%;margin:5px 0}
.login .btn{width:100%;margin-top:12px}
.login .err{color:var(--danger);font-size:var(--text-xs);margin:10px 0 0}

h2.sect{font-size:var(--text-md);font-weight:600;margin:30px 0 4px}
p.sub{font-size:var(--text-xs);color:var(--text-muted);margin:0 0 10px}

/* ── chat: the conversation shell (docs/CHAT.md) ──────────────────────── */
.chatwrap{display:grid;grid-template-columns:288px minmax(0,1fr);
  height:calc(100vh - 54px)}
.chatside{border-right:1px solid var(--edge);overflow-y:auto;
  padding:16px 14px 24px;display:flex;flex-direction:column;gap:2px}
.chatside .newchat{display:block;text-align:center;margin-bottom:12px;
  padding:9px 12px;border:1px solid var(--edge);border-radius:var(--r-sm);
  background:var(--surface-2);font-family:var(--font-label);
  text-transform:uppercase;letter-spacing:.13em;font-size:var(--text-caps);
  color:var(--text)}
.chatside .newchat:hover{background:var(--surface-3)}
.sgrp{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text-dim);padding:12px 8px 5px}
.sess{display:block;padding:8px 10px;border-radius:var(--r-sm);
  border:1px solid transparent}
.sess:hover{background:var(--surface-1)}
.sess.on{background:var(--surface-2);border-color:var(--edge)}
.sess .t1{display:flex;align-items:center;gap:7px;min-width:0}
.sess .t1 .ttl{font-size:var(--text-xs);color:var(--text);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;flex:1}
.sess .t2{display:flex;gap:8px;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);margin-top:3px}
.sess .t2 .ag{color:var(--text-muted);text-transform:uppercase;
  letter-spacing:.08em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sess .t2 .sp{margin-left:auto;white-space:nowrap}
.sideempty{font-size:var(--text-xs);color:var(--text-dim);line-height:1.6;
  padding:8px 10px}

.chatmain{display:flex;flex-direction:column;min-width:0}
.chathead{display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap;
  padding:16px 28px 13px;border-bottom:1px solid var(--edge)}
.chathead .anm{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.16em;font-size:var(--text-sm);color:var(--gold-light)}
.chathead .adesc{font-size:var(--text-xs);color:var(--text-muted);
  margin-top:4px;max-width:76ch;line-height:1.55}
.chathead .chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.chathead .totals{margin-left:auto;text-align:right;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);line-height:1.6;white-space:nowrap}
.chathead .totals .v{font-size:var(--text-lg);color:var(--text);display:block;
  font-variant-numeric:tabular-nums}
.chathead form.rename{margin:0}
.chathead input.ttl{background:transparent;border:1px solid transparent;
  border-radius:var(--r-sm);color:var(--text);font-family:var(--font-ui);
  font-size:var(--text-md);font-weight:600;padding:2px 6px;margin-left:-6px;
  width:min(56ch,60vw)}
.chathead input.ttl:hover{border-color:var(--edge)}
.chathead input.ttl:focus{border-color:var(--edge);outline:none;
  background:var(--surface-1)}

.transcript{flex:1;overflow-y:auto;padding:6px 28px 26px;scroll-behavior:smooth}
.turn{max-width:920px;margin:0 auto}
.msg{padding:16px 0 4px}
.msg .who{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.15em;font-size:var(--text-caps);color:var(--text-dim);
  display:flex;align-items:baseline;gap:10px}
.msg .who .tm{font-family:var(--font-mono);letter-spacing:0;margin-left:auto}
.msg.you .who{color:var(--night-3)}
.msg.agent .who{color:var(--dawn-3)}
.msg .utext{font-size:var(--text-base);color:var(--text);line-height:1.6;
  margin-top:6px;white-space:pre-wrap;overflow-wrap:anywhere}
.msg .atext{margin-top:6px}
.msg .atext.streaming{white-space:pre-wrap;font-size:var(--text-sm);
  line-height:1.65;color:var(--text)}
.msg .atext.streaming::after{content:'▌';color:var(--dawn-3);
  animation:caret 1.1s steps(2) infinite}
@keyframes caret{50%{opacity:0}}

/* tool lines: the agent's visible work, Claude-Code anatomy */
.work{margin:10px 0 2px;border-left:2px solid var(--edge);padding:2px 0 2px 14px;
  display:flex;flex-direction:column;gap:3px}
.tl{font-family:var(--font-mono);font-size:var(--text-xs);color:var(--text-muted);
  display:flex;gap:8px;align-items:baseline;min-width:0}
.tl .g{color:var(--dawn-2);flex:0 0 auto}
.tl .tn{color:var(--text)}
.tl .ta{color:var(--text-dim);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;min-width:0}
.tl.spec .g{color:var(--night-3)}
details.tlo{margin:-1px 0 2px 20px}
details.tlo summary{cursor:pointer;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);list-style:none}
details.tlo summary:hover{color:var(--text-muted)}
details.tlo summary::before{content:'▸ '}
details.tlo[open] summary::before{content:'▾ '}
details.tlo pre{background:var(--surface-0);border:1px solid var(--edge);
  border-radius:var(--r-sm);padding:8px 11px;margin:5px 0 3px;overflow-x:auto;
  font-size:var(--text-caps);color:var(--text-muted);max-height:260px;
  overflow-y:auto;white-space:pre-wrap;overflow-wrap:anywhere}

.tfoot{display:flex;gap:14px;margin-top:10px;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);align-items:baseline;
  flex-wrap:wrap}
.tfoot .m{color:var(--text-muted)}
.terr{font-family:var(--font-mono);font-size:var(--text-xs);color:var(--danger);
  background:#231517;border:1px solid #3A211E;border-radius:var(--r-sm);
  padding:9px 12px;margin-top:8px;overflow-wrap:anywhere}
.tstop{font-size:var(--text-xs);color:var(--warning);margin-top:8px}

.workingline{display:flex;align-items:center;gap:9px;margin-top:12px;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.13em;
  font-size:var(--text-caps);color:var(--accent)}
.workingline .dot{background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);
  animation:caret 1.2s steps(2) infinite}
.workingline .stop{margin-left:6px;background:none;border:1px solid var(--edge);
  border-radius:var(--r-pill);color:var(--text-muted);cursor:pointer;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);padding:3px 10px}
.workingline .stop:hover{color:var(--danger);border-color:#3A211E}

.composer{border-top:1px solid var(--edge);padding:14px 28px 10px}
.composer .cbox{max-width:920px;margin:0 auto}
.composer textarea{width:100%;background:var(--surface-1);color:var(--text);
  border:1px solid var(--edge);border-radius:var(--r-md);padding:12px 52px 12px 14px;
  font-family:var(--font-ui);font-size:var(--text-base);line-height:1.5;
  resize:none;min-height:48px;max-height:220px;display:block}
.composer textarea:focus{outline:none;border-color:var(--gold-deep)}
.composer textarea::placeholder{color:var(--text-dim)}
.composer .crow{position:relative}
.composer .send{position:absolute;right:9px;bottom:9px;width:32px;height:32px;
  border-radius:var(--r-sm);border:1px solid var(--accent);background:var(--accent);
  color:var(--on-accent);font-size:15px;cursor:pointer;line-height:1}
.composer .send:disabled{background:var(--surface-3);border-color:var(--edge);
  color:var(--text-dim);cursor:default}
.cfoot{display:flex;gap:8px;max-width:920px;margin:9px auto 0;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.13em;
  font-size:var(--text-caps);color:var(--text-dim);flex-wrap:wrap}
.cfoot b{color:var(--text-muted);font-weight:400}

/* ── chat hub + agent roster ──────────────────────────────────────────── */
.hub{flex:1;overflow-y:auto;padding:24px 28px}
.hub .inner{max-width:920px;margin:0 auto}
.hub h1{font-size:var(--text-lg);font-weight:600;margin:6px 0 4px}
.lede{font-size:var(--text-sm);color:var(--text-muted);margin:0 0 18px;
  max-width:78ch;line-height:1.6}
.agrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));
  gap:12px;margin:14px 0 4px}
.acard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-md);
  padding:13px 15px;cursor:pointer;display:block}
.acard:hover{background:var(--surface-2)}
.acard.sel{border-color:var(--gold-deep);background:var(--surface-2)}
.acard .an{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.14em;font-size:var(--text-caps);color:var(--text)}
.acard.sel .an{color:var(--accent)}
.acard .ad{font-size:var(--text-xs);color:var(--text-muted);line-height:1.5;
  margin:6px 0 0;display:-webkit-box;-webkit-line-clamp:3;
  -webkit-box-orient:vertical;overflow:hidden}
.acard .am{display:flex;gap:10px;margin-top:10px;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);flex-wrap:wrap}
.acard.hero{grid-column:1 / -1;background:var(--surface-2);
  border-color:#2E2A22;padding:16px 18px}
.acard.hero .an{color:var(--gold-light);font-size:var(--text-xs)}
.acard.hero .ad{-webkit-line-clamp:unset;max-width:88ch;color:var(--text)}
.roster .acard{cursor:default}
.roster .acard:hover{background:var(--surface-1)}
.acard .arow{display:flex;gap:8px;row-gap:8px;align-items:center;margin-top:11px;
  flex-wrap:wrap}
.acard .arow .go{margin-left:auto;white-space:nowrap}
.newagent{background:var(--surface-0);border:1px dashed var(--edge);
  border-radius:var(--r-md);padding:16px 18px;margin-top:18px}
.newagent h3{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.14em;font-size:var(--text-caps);color:var(--text-muted);
  font-weight:400;margin:0 0 10px}
.newagent .frow{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.newagent input[type=text]{flex:1;min-width:220px}
.newagent textarea{width:100%;background:var(--surface-0);color:var(--text);
  border:1px solid var(--edge);border-radius:var(--r-sm);padding:9px 11px;
  font-family:var(--font-ui);font-size:var(--text-sm);min-height:70px;resize:vertical}
.newagent .hint{font-size:var(--text-caps);color:var(--text-dim);margin:4px 0 10px;
  line-height:1.6}
.newagent label.radio{display:inline-flex;gap:6px;align-items:center;
  font-size:var(--text-xs);color:var(--text-muted);margin-right:14px}
.notice{border:1px solid #3A2A1E;background:var(--warning-soft);color:var(--text-muted);
  border-radius:var(--r-md);padding:11px 14px;font-size:var(--text-xs);
  margin:14px 0;line-height:1.55}
.notice b{color:var(--warning)}
"""

# The reload keeps the board live without a JS framework: skip whenever the
# operator is typing a note or reading an opened report, so state is never lost.
SCRIPT = """
<script>
(function(){
  var t0=Date.now(), pill=document.getElementById('livepill');
  setInterval(function(){
    if(!pill) return;
    var s=Math.floor((Date.now()-t0)/1000);
    if(s>=75){pill.classList.add('stale');
      pill.querySelector('b').textContent='Stale '+s+'s';}
  },5000);
  setInterval(function(){
    if(document.querySelector('input:focus,textarea:focus')) return;
    if(document.querySelector('details[open]')) return;
    location.reload();
  },30000);
})();
</script>
"""

NAV = [("Board", "/"), ("Chat", "/chat"), ("Gates", "/gates"), ("Runs", "/runs"),
       ("Agents", "/agents"), ("Spend", "/spend")]


def page(title: str, body: str, user: str | None = None, active: str = "/",
         clock: str = "", auto_reload: bool = True) -> str:
    """auto_reload=False for live-streaming pages (chat): the 30s reloader would
    tear down an in-flight SSE transcript; those pages update themselves."""
    if not user:                                       # login page: no shell
        return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
                f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>{H(title)}</title><link rel='icon' href='data:,'>{FONTS}<style>{CSS}</style></head>"
                f"<body>{body}</body></html>")
    tabs = "".join(
        f"<a href='{href}'{' class=on' if href == active else ''}>{H(name)}</a>"
        for name, href in NAV)
    top = (f"<header class='topbar'><a class='wordmark' href='/'>Lantern</a>"
           f"<nav>{tabs}</nav><span class='right'>"
           f"<span class='live' id='livepill'><span class='dot live'></span>"
           f"<b>Live</b>&nbsp;· {H(clock)} UTC</span>"
           f"<span>{H(user)}</span><a href='/logout'>log out</a></span></header>")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{H(title)}</title>{FONTS}<style>{CSS}</style></head>"
            f"<body>{top}{body}{SCRIPT if auto_reload else ''}</body></html>")


# ── atoms ────────────────────────────────────────────────────────────────────

def chip(text: str, kind: str = "") -> str:
    return f"<span class='chip {kind}'>{H(text)}</span>"


def dot(kind: str) -> str:
    return f"<span class='dot {kind}'></span>"


def srail(segs: list[str], tall: bool = False) -> str:
    body = "".join(f"<i class='{s}'></i>" if s else "<i></i>" for s in segs)
    return f"<span class='srail{' tall' if tall else ''}'>{body}</span>"


def fmt_int(n) -> str:
    return f"{int(n):,}" if n is not None else "—"


def fmt_money(x: float | None) -> str:
    if x is None:
        return "—"
    if 0 < x < 0.01:
        return "<$0.01"
    return f"${x:,.2f}"


def ago(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h}h {m:02d}m" if m else f"{h}h"
    d, h = divmod(h, 24)
    return f"{d}d {h}h" if h else f"{d}d"


def strip(d: dict, hot: bool = False, dim: bool = False) -> str:
    """One run, one row. Keys: href dot id sub stage_label segs chip wait_main
    wait_why elapsed elapsed_cold model_l1 model_l2 tok_l1 tok_l2 money."""
    ch = chip(*d["chip"]) if d.get("chip") else "<span class='caps'>—</span>"
    cls = "strip" + (" hot" if hot else "") + (" dim" if dim else "")
    t_cls = "t cold" if d.get("elapsed_cold") else "t"
    return f"""<a class='{cls}' href='{H(d["href"])}'>
      {dot(d["dot"])}
      <span><span class='id'>{H(d["id"])}</span><span class='sub'>{H(d["sub"])}</span></span>
      <span class='st'><span class='lab'>{H(d["stage_label"])}</span>{srail(d["segs"])}</span>
      <span>{ch}</span>
      <span class='wait'><b>{H(d["wait_main"][0])}</b>{H(d["wait_main"][1])}
        <span class='why'>{H(d["wait_why"])}</span></span>
      <span class='{t_cls}'>{H(d["elapsed"])}</span>
      <span class='mdl'>{H(d["model_l1"])}<span>{H(d["model_l2"])}</span></span>
      <span class='tok'>{H(d["tok_l1"])}<span>{H(d["tok_l2"])}</span></span>
      <span class='money'>{H(d["money"])}</span>
      <span class='go'>→</span>
    </a>"""


def strip_header() -> str:
    return ("<div class='hdr'><span></span><span>Run</span><span>Stage</span>"
            "<span>Verdict</span><span>Waiting on</span><span class='r'>Elapsed</span>"
            "<span class='r'>Model</span><span class='r'>Tokens</span>"
            "<span class='r'>Est. $</span><span></span></div>")


def group_head(name: str, count: int, note: str = "", hot: bool = False) -> str:
    return (f"<div class='grp{' hot' if hot else ''}'><span class='n'>{H(name)}</span>"
            f"<span class='c'>{count}</span><span class='rule'></span>"
            + (f"<span class='note'>{H(note)}</span>" if note else "") + "</div>")
