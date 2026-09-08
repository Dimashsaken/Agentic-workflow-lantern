"""Rendering layer for Mission Control v3 — atoms, CSS, scripts, and the page shell.

Every color, font size, and radius is a literal from design/design-system.md
(tokens contentHash 288d9538); the light palette is the same ladder mirrored (v3,
D22) — dark stays canonical. Additions are proposed in the mockups README, never
invented here. Direction: "flight strips" (mockup C) for runs, swim lanes for a
run's executions (the IndyDevDan bar), artifact-first gate cards (the HumanLayer
bar: one glance = what needs me, one click = act).

No build step: CSS and the small vanilla-JS layer (theme, keyboard map, the
execution drawer over the existing fetch/SSE pattern) are inlined by page().
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
  color-scheme:dark;
  --surface-0:#0A0A0C; --surface-1:#121216; --surface-2:#191920; --surface-3:#22222A;
  --edge:#24242C; --edge-top:rgb(255 255 255 / 5.5%);
  --text:#E8E8EC; --text-muted:#8E8E98; --text-dim:#6C6C76;
  --accent:#F2C57F; --accent-soft:#2C2113; --on-accent:#08080A;
  --success:#43C67E; --success-soft:#12301F;
  --warning:#E7935A; --warning-soft:#2E1E16;
  --danger:#E5705F; --danger-soft:#231517;
  --gold-deep:#8C6A2F; --gold-light:#C9B183;
  --night-1:#46565F; --night-2:#5C6E77; --night-3:#7B8A90;
  --dawn-1:#C77A4E; --dawn-2:#D89A5E; --dawn-3:#E8B570; --dawn-4:#F2C77E;
  --danger-edge:#3A211E; --accent-edge:#3A2D18; --success-edge:#1B3D28;
  --warning-edge:#3A2A1E; --hot-edge:#2E2A22; --hot-bg:#191920;
  --shadow:0 6px 18px #00000059;
  --font-ui:'Figtree','Segoe UI',system-ui,sans-serif;
  --font-mono:'JetBrains Mono','Cascadia Mono',Consolas,monospace;
  --font-label:'ADAM.CG PRO','Figtree','Segoe UI',system-ui,sans-serif;
  --text-caps:11px; --text-xs:13px; --text-sm:14px; --text-base:15px;
  --text-md:16px; --text-lg:20px; --text-xl:28px;
  --r-sm:6px; --r-md:12px; --r-lg:16px; --r-pill:999px;
  --lane-cols:250px minmax(0,1fr) 236px;
}
/* Light: the same ladder mirrored — canvas warm off-white, cards white, the gold
   ramp deepened so accent text keeps contrast. Chosen explicitly (toggle) or by
   the OS when nothing is stored; dark remains the design system's canonical. */
:root[data-theme=light],
:root:not([data-theme=dark]).sys-light{
  color-scheme:light;
  --surface-0:#F6F5F1; --surface-1:#FFFFFF; --surface-2:#F0EEE8; --surface-3:#E6E3DB;
  --edge:#DCD9D0; --edge-top:rgb(0 0 0 / 3%);
  --text:#1C1C21; --text-muted:#5B5B66; --text-dim:#85858F;
  --accent:#B07A1C; --accent-soft:#F6E9CF; --on-accent:#FFFFFF;
  --success:#1E8A52; --success-soft:#DCF2E5;
  --warning:#B4601C; --warning-soft:#F8E6D5;
  --danger:#C23F36; --danger-soft:#F8E0DD;
  --gold-deep:#8C6A2F; --gold-light:#7A5F2E;
  --night-1:#9AA6AC; --night-2:#7F8E96; --night-3:#65737B;
  --dawn-1:#B8683C; --dawn-2:#B97E3B; --dawn-3:#A9762A; --dawn-4:#9C6E22;
  --danger-edge:#EBC2BD; --accent-edge:#E8D3A6; --success-edge:#BFE3CC;
  --warning-edge:#EFCDB3; --hot-edge:#E3D3B0; --hot-bg:#FBF6EA;
  --shadow:0 6px 18px rgb(0 0 0 / 12%);
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
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ── shell: one slim top bar, nothing else ────────────────────────────── */
.topbar{display:flex;align-items:center;gap:30px;padding:15px 28px;
  border-bottom:1px solid var(--edge)}
.topbar .wordmark{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.24em;font-size:var(--text-xs);color:var(--gold-light);white-space:nowrap}
.topbar nav{display:flex;gap:24px;overflow-x:auto;scrollbar-width:none}
.topbar nav::-webkit-scrollbar{display:none}
.topbar nav a{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.13em;font-size:var(--text-caps);color:var(--text-muted);
  padding:6px 0 5px;border-bottom:2px solid transparent;white-space:nowrap}
.topbar nav a.on{color:var(--text);border-bottom-color:var(--accent)}
.topbar nav a:hover{color:var(--text)}
.topbar .right{margin-left:auto;display:flex;align-items:center;gap:14px;
  font-size:var(--text-xs);color:var(--text-muted);white-space:nowrap}
.topbar .right .live{display:inline-flex;align-items:center;gap:8px;color:var(--text)}
.topbar .right .live.stale{color:var(--danger)}
.topbar .right .live.stale .dot{background:var(--danger);box-shadow:none}
.topbar .right a{color:var(--text-muted);text-decoration:underline;
  text-underline-offset:3px}
.topbar .right a:hover{color:var(--text)}
.tbtn{background:none;border:1px solid var(--edge);border-radius:var(--r-pill);
  color:var(--text-muted);cursor:pointer;font-family:var(--font-label);
  text-transform:uppercase;letter-spacing:.11em;font-size:var(--text-caps);
  padding:4px 10px;line-height:1.4}
.tbtn:hover{color:var(--text);border-color:var(--text-dim)}
.page{padding:0 28px 44px}

/* one-line status bar under the top bar (home only) */
.statusline{display:flex;align-items:center;gap:9px;flex-wrap:wrap;
  padding:13px 28px;border-bottom:1px solid var(--edge);
  font-size:var(--text-xs);color:var(--text-muted)}
.statusline b{color:var(--text);font-weight:600}
.statusline .num{font-family:var(--font-mono);font-variant-numeric:tabular-nums;
  color:var(--text);font-size:var(--text-xs)}
.statusline .sep{color:var(--text-dim)}
.statusline .warn{color:var(--warning)}
.statusline .bad{color:var(--danger)}

/* gate-latency ledger: full-width strip between the inbox and the board.
   Scrolls sideways at narrow widths so no gate's number is ever clipped. */
.ledger{display:flex;align-items:center;gap:32px;padding:14px 28px;
  background:var(--surface-1);border-bottom:1px solid var(--edge);
  overflow-x:auto}
.ledger .lhead{flex:0 0 auto}
.ledger .lhead .d{font-size:var(--text-xs);color:var(--text-muted);margin-top:2px}
.ledger .lm{flex:0 0 auto}
.ledger .lm .v{font-family:var(--font-mono);font-size:var(--text-xl);
  line-height:1.1;font-variant-numeric:tabular-nums;color:var(--text);
  white-space:nowrap}
.ledger .lm .v.warn{color:var(--warning)}
.ledger .lm .v.dim{color:var(--text-dim)}
.ledger .lm .s{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.11em;font-size:var(--text-caps);color:var(--text-muted);
  margin-top:3px;white-space:nowrap}
.ledger .lerr{font-size:var(--text-xs);color:var(--text-muted)}

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
.chip.blocked{color:var(--danger);border-color:var(--danger-edge);background:var(--danger-soft)}
.chip.gate{color:var(--accent);border-color:var(--accent-edge);background:var(--accent-soft)}
.chip.ok{color:var(--success);border-color:var(--success-edge);background:var(--success-soft)}
.chip.warn{color:var(--warning);border-color:var(--warning-edge);background:var(--warning-soft)}
.chip.tier{color:var(--night-3);border-color:var(--edge);background:transparent}
.btn{display:inline-block;font-family:var(--font-ui);font-size:var(--text-sm);
  font-weight:600;padding:9px 16px;border-radius:var(--r-sm);cursor:pointer;
  border:1px solid var(--edge);background:var(--surface-3);color:var(--text)}
.btn.primary{background:var(--accent);color:var(--on-accent);border-color:var(--accent)}
.btn.danger{background:transparent;border-color:var(--danger-edge);color:var(--danger)}
.btn.sm{padding:6px 12px;font-size:var(--text-xs)}
input[type=text],input[type=password]{background:var(--surface-0);color:var(--text);
  border:1px solid var(--edge);border-radius:var(--r-sm);padding:8px 11px;
  font-family:var(--font-ui);font-size:var(--text-sm)}
input::placeholder{color:var(--text-dim)}
select{background:var(--surface-0);color:var(--text);border:1px solid var(--edge);
  border-radius:var(--r-sm);padding:8px 11px;font-family:var(--font-ui);
  font-size:var(--text-sm);min-width:240px}
kbd{font-family:var(--font-mono);font-size:var(--text-caps);border:1px solid var(--edge);
  border-bottom-width:2px;border-radius:4px;padding:1px 6px;background:var(--surface-2);
  color:var(--text)}

/* codebase connection: the product-target picker (D15) */
.pick{border:1px solid var(--edge);border-radius:var(--r-md);padding:16px 18px;
  margin:14px 0;background:var(--surface-1)}
.pick h3{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text-muted);margin:0 0 4px;font-weight:600}
.pick .hint{font-size:var(--text-xs);color:var(--text-dim);margin:0 0 12px;line-height:1.6}
.pick .hint code{font-family:var(--font-mono)}
.repolist{display:flex;flex-direction:column;gap:2px;max-height:340px;overflow-y:auto;
  margin:0 0 12px}
.repolist label{display:flex;align-items:baseline;gap:10px;padding:8px 10px;
  border-radius:var(--r-sm);cursor:pointer;border:1px solid transparent}
.repolist label:hover{background:var(--surface-2);border-color:var(--edge)}
.repolist .nm{font-weight:600;font-size:var(--text-sm)}
.repolist .br{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--gold-deep)}
.repolist .pt{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--text-dim);margin-left:auto;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:46%}
.pick .row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px}
.pick .fld{display:flex;flex-direction:column;gap:5px}
.pick .fld .lb{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.12em;font-size:var(--text-caps);color:var(--text-dim)}
.pick .warnbox{border:1px solid var(--warning-edge);background:var(--warning-soft);
  color:var(--warning);border-radius:var(--r-sm);padding:10px 12px;
  font-size:var(--text-xs);line-height:1.6;margin:0 0 12px}
.pick .errbox{border:1px solid var(--danger-edge);background:var(--danger-soft);
  color:var(--danger);border-radius:var(--r-sm);padding:10px 12px;
  font-size:var(--text-xs);line-height:1.6;margin:0 0 12px}

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
.kcard.hot{background:var(--hot-bg);border-color:var(--hot-edge)}
.kcard.stale{border-color:var(--warning)}
.kcard.stale .stg .age{color:var(--warning)}
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
.kcard .acts .ev{font-size:var(--text-caps);color:var(--text-muted);
  text-decoration:underline;text-underline-offset:3px;margin-left:auto}
.kcard .acts .ev:hover{color:var(--text)}

/* ── readout tiles (cost page, catalog) ───────────────────────────────── */
.readout{display:grid;grid-template-columns:repeat(5,1fr) auto;gap:1px;
  background:var(--edge);border-bottom:1px solid var(--edge);margin:0 -32px}
.readout>div{background:var(--surface-0);padding:18px 26px 16px}
.readout .v{font-family:var(--font-mono);font-size:var(--text-xl);line-height:1;
  font-variant-numeric:tabular-nums;margin:7px 0 5px}
.readout .v small{font-size:var(--text-sm);color:var(--text-dim)}
.readout .d{font-size:var(--text-xs);color:var(--text-muted)}
.readout .v.act{color:var(--accent)}
.readout .v.bad{color:var(--danger)}
.readout .v.warn{color:var(--warning)}
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
.strip.hot{background:var(--hot-bg);border-color:var(--hot-edge);border-radius:var(--r-md);
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

/* ── the inbox + gate cards ───────────────────────────────────────────── */
.inbox{padding:18px 28px 6px}
.inbox .ihead{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.inbox .ihead h2{font-size:var(--text-md);font-weight:600;margin:0}
.inbox .ihead .keys{margin-left:auto;font-size:var(--text-caps);color:var(--text-dim);
  display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.inbox .iempty{font-size:var(--text-xs);color:var(--text-dim);margin:6px 0 10px}
.gcard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-lg);
  padding:20px 22px;margin:16px 0;scroll-margin:80px}
.gcard.kfocus{outline:2px solid var(--accent);outline-offset:2px}
.gcard.stale{border-color:var(--warning)}
.gcard .ghead{display:flex;align-items:flex-start;justify-content:space-between;
  gap:16px;flex-wrap:wrap}
.gcard .ghead h2{font-size:var(--text-md);font-weight:600;margin:2px 0 3px}
.gcard .ghead .gid{font-family:var(--font-mono);font-size:var(--text-xs);
  color:var(--text-muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.gcard .ghead .gage{font-family:var(--font-mono);font-size:var(--text-xs);
  color:var(--dawn-3);text-align:right;white-space:nowrap}
.gcard .gdesc{font-size:var(--text-xs);color:var(--text-muted);margin:6px 0 0;
  max-width:92ch}
.blockwarn{border:1px solid var(--danger-edge);background:var(--danger-soft);border-radius:var(--r-md);
  padding:12px 15px;margin:14px 0 4px;font-size:var(--text-xs);line-height:1.55;
  color:var(--text-muted)}
.blockwarn b{color:var(--danger);font-weight:600}
.blockwarn .q{display:block;margin-top:6px;color:var(--text);font-style:italic}
.gopts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));
  gap:14px;margin:16px 0 4px}
.gopt{background:var(--surface-0);border:1px solid var(--edge);
  border-radius:var(--r-md);padding:12px}
.gopt.rec{border-color:var(--accent-edge)}
.gopt .on{display:flex;align-items:baseline;justify-content:space-between;gap:8px;
  margin-bottom:4px}
.gopt .on b{font-size:var(--text-sm);font-weight:600}
.gopt .axis{font-size:var(--text-caps);color:var(--text-dim);line-height:1.5;
  margin-bottom:10px}
.gopt img{width:100%;border:1px solid var(--edge);border-radius:var(--r-sm);
  background:var(--surface-0);display:block}
.missingpng{border:1px dashed var(--warning-edge);background:var(--warning-soft);
  border-radius:var(--r-sm);padding:10px 12px;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--warning);line-height:1.5}
.gmeta{display:flex;gap:18px;flex-wrap:wrap;margin:12px 0 0;
  font-family:var(--font-mono);font-size:var(--text-caps);color:var(--text-dim)}
.gmeta b{color:var(--text-muted);font-weight:400}
.gmeta a{color:var(--dawn-3)}
.commits{margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--text-muted);line-height:1.5}
.commits code{font-family:var(--font-mono);color:var(--text-dim)}
.gact{display:flex;gap:10px;align-items:center;margin-top:16px;
  padding-top:14px;border-top:1px solid var(--edge);flex-wrap:wrap}
.gact form{display:flex;gap:10px;flex:1;min-width:280px;flex-wrap:wrap;align-items:center}
.gact input[type=text]{flex:1;min-width:200px}
.gact .nxt{font-size:var(--text-caps);color:var(--text-dim);flex-basis:100%}
.decided .att{grid-template-columns:106px 240px 1fr 130px}
/* artifact-first: the thing being decided sits open, bounded, scrollable */
.artbox{border:1px solid var(--edge);border-radius:var(--r-md);background:var(--surface-0);
  margin:12px 0 0;max-height:420px;overflow:auto}
.artbox .abh{position:sticky;top:0;background:var(--surface-0);padding:8px 14px;
  border-bottom:1px solid var(--edge);font-size:var(--text-caps);color:var(--text-muted);
  display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;z-index:1}
.artbox .abh b{color:var(--text);font-weight:600;letter-spacing:0;text-transform:none;
  font-size:var(--text-xs)}
.artbox .prose{padding:6px 18px 16px}
.artbox table.vt{margin:0}
.vtbl{width:100%;border-collapse:collapse}
.vtbl th,.vtbl td{border-top:1px solid var(--edge);padding:7px 10px;font-size:var(--text-xs);
  color:var(--text-muted);text-align:left;vertical-align:top}
.vtbl th{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);color:var(--text-dim);border-top:0;font-weight:400}
.vtbl td.id{font-family:var(--font-mono);color:var(--text);white-space:nowrap}
.rounds{display:flex;flex-direction:column;gap:6px;margin:10px 0 0}
.round{display:flex;gap:12px;align-items:baseline;font-size:var(--text-xs);
  color:var(--text-muted);flex-wrap:wrap}
.round .rn{font-family:var(--font-mono);color:var(--text);white-space:nowrap}

/* rendered markdown reports */
/* Reports carry long paths, branch names and URLs. On a phone an unbreakable token
   would push the card past the viewport, so prose breaks anywhere; code blocks and
   tables keep their shape and scroll inside themselves instead. */
.prose{font-size:var(--text-sm);line-height:1.65;color:var(--text);max-width:92ch;
  overflow-wrap:anywhere}
.prose img{max-width:100%;height:auto}
.prose pre,.prose table{overflow-wrap:normal}
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
details.report pre.raw{margin:0;padding:12px 16px;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-muted);white-space:pre-wrap;
  overflow-wrap:anywhere;max-height:480px;overflow:auto;line-height:1.55}

/* ── run detail ───────────────────────────────────────────────────────── */
.runhead{padding:24px 0 18px;border-bottom:1px solid var(--edge);
  display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap;
  align-items:flex-start}
.runhead h1{font-family:var(--font-mono);font-size:var(--text-lg);font-weight:400;
  margin:4px 0 8px;overflow-wrap:anywhere}
.runhead .meta{font-size:var(--text-xs);color:var(--text-muted);line-height:1.7}
.runhead .meta code{font-family:var(--font-mono);color:var(--text-muted);overflow-wrap:anywhere}
.runhead .meta a.lnk{color:var(--dawn-3);text-decoration:underline;text-underline-offset:3px}
.runhead .totals{text-align:right}
.runhead .totals .v{font-family:var(--font-mono);font-size:var(--text-xl);
  line-height:1.1}
.runhead .totals .d{font-size:var(--text-caps);color:var(--text-dim);
  font-family:var(--font-mono);margin-top:4px;line-height:1.5}
.runnav{display:flex;gap:16px;flex-wrap:wrap;margin:14px 0 0;font-size:var(--text-caps);
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.12em}
.runnav a{color:var(--text-muted);border-bottom:2px solid transparent;padding-bottom:3px}
.runnav a.on{color:var(--text);border-bottom-color:var(--accent)}
.runnav a:hover{color:var(--text)}
.scard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-lg);
  padding:16px 18px;margin:12px 0}
.scard.cur{background:var(--hot-bg);border-color:var(--hot-edge)}
.scard.pend{opacity:.55}
.scard .shead{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.scard .shead .nm{font-size:var(--text-sm);font-weight:600}
.scard .shead .actor{font-size:var(--text-caps);color:var(--text-dim)}
.scard .shead .right{margin-left:auto;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);text-align:right;line-height:1.5}
.scard .sdesc{font-size:var(--text-caps);color:var(--text-dim);margin:5px 0 0}
.scard .err{font-family:var(--font-mono);font-size:var(--text-caps);
  color:var(--danger);background:var(--danger-soft);border:1px solid var(--danger-edge);
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

/* ── swim lanes: one lane per stage execution key, time flowing right ──── */
.lanes{margin-top:16px;border:1px solid var(--edge);border-radius:var(--r-lg);
  background:var(--surface-1);overflow:hidden}
.lanes .lhead,.lane{display:grid;grid-template-columns:var(--lane-cols);gap:14px;
  align-items:center;padding:9px 16px;border-bottom:1px solid var(--edge)}
.lanes .lhead{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.12em;font-size:var(--text-caps);color:var(--text-dim);
  background:var(--surface-0)}
.lanes .lhead .r{text-align:right}
.lane:last-child{border-bottom:0}
.lane.future{opacity:.5}
.lane.cur{background:var(--hot-bg)}
.lane .lname{min-width:0}
.lane .lname .k{font-family:var(--font-mono);font-size:var(--text-xs);color:var(--text);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lane .lname .k small{color:var(--text-dim);font-size:var(--text-caps)}
.lane .lname .r{font-size:var(--text-caps);color:var(--text-dim);margin-top:3px;
  display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.slots{display:grid;grid-template-columns:repeat(var(--n,1),minmax(0,1fr));gap:3px;
  min-height:26px;align-items:center}
.slots .ghost{grid-column:1 / -1;font-size:var(--text-caps);color:var(--text-dim);
  font-family:var(--font-mono)}
.pill{grid-column:var(--slot) / span 1;display:block;position:relative;height:26px;
  border-radius:var(--r-sm);background:var(--surface-3);border:1px solid var(--edge);
  overflow:hidden;color:var(--text);font-family:var(--font-mono);
  font-size:var(--text-caps);line-height:24px;padding:0 7px;white-space:nowrap;
  text-overflow:ellipsis;cursor:pointer;scroll-margin:120px}
.pill i{position:absolute;left:0;top:0;bottom:0;width:var(--w,100%);opacity:.38;
  background:var(--night-2)}
.pill.ok i{background:var(--success)} .pill.bad i{background:var(--danger)}
.pill.run i{background:var(--dawn-3);animation:pulse 1.6s ease-in-out infinite}
.pill.wait i{background:var(--accent)} .pill.skip i{background:var(--text-dim)}
@keyframes pulse{50%{opacity:.18}}
.pill span{position:relative}
.pill:hover{border-color:var(--text-dim)}
.pill.kfocus{outline:2px solid var(--accent);outline-offset:1px}
.lane .lright{display:grid;grid-template-columns:auto auto auto;gap:12px;
  justify-content:end;align-items:center;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-muted);text-align:right;white-space:nowrap}
.lane .lright .money{color:var(--text);font-size:var(--text-xs)}
.gaterow{display:flex;align-items:center;gap:10px;padding:6px 16px;
  border-bottom:1px solid var(--edge);font-size:var(--text-caps);color:var(--text-dim);
  background:var(--surface-0);flex-wrap:wrap}
.gaterow .dia{color:var(--accent);font-size:15px;line-height:1}
.gaterow.ok .dia{color:var(--success)} .gaterow.bad .dia{color:var(--danger)}
.gaterow.future .dia{color:var(--text-dim)}
.gaterow .gn{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  color:var(--text-muted)}
.gaterow .who{font-family:var(--font-mono)}
.gaterow a{color:var(--dawn-3);text-decoration:underline;text-underline-offset:3px}
.lanefoot{display:flex;gap:16px;flex-wrap:wrap;margin:10px 2px 0;font-size:var(--text-caps);
  color:var(--text-dim);align-items:center}
.lanefoot .sw{display:inline-flex;align-items:center;gap:6px}
.lanefoot .sw i{width:12px;height:8px;border-radius:2px;display:inline-block;opacity:.6}

/* ── the execution drawer ─────────────────────────────────────────────── */
.drawer{position:fixed;top:0;right:0;height:100vh;height:100dvh;width:min(760px,100vw);
  transform:translateX(102%);transition:transform .16s ease-out;overflow:auto;
  background:var(--surface-1);border-left:1px solid var(--edge);z-index:50;
  box-shadow:var(--shadow);outline:none}
.drawer.open{transform:none}
.dscrim{position:fixed;inset:0;background:#00000066;z-index:49;display:none}
.dscrim.on{display:block}
.dwrap{padding:0 22px 40px}
.dhead{position:sticky;top:0;background:var(--surface-1);padding:16px 0 12px;
  border-bottom:1px solid var(--edge);display:flex;gap:12px;align-items:flex-start;
  flex-wrap:wrap;z-index:2}
.dhead h2{font-family:var(--font-mono);font-size:var(--text-md);font-weight:500;margin:0;
  overflow-wrap:anywhere}
.dhead .dsub{font-size:var(--text-caps);color:var(--text-dim);margin-top:4px;
  display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.dhead .dclose{margin-left:auto}
.dgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1px;
  background:var(--edge);border:1px solid var(--edge);border-radius:var(--r-md);
  overflow:hidden;margin:14px 0}
.dgrid>div{background:var(--surface-0);padding:10px 12px}
.dgrid .k{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.12em;
  font-size:var(--text-caps);color:var(--text-dim)}
.dgrid .v{font-family:var(--font-mono);font-size:var(--text-sm);color:var(--text);
  margin-top:3px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.dgrid .v small{color:var(--text-dim);font-size:var(--text-caps)}
.dsect{margin:18px 0 0}
.dsect h3{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text-muted);font-weight:400;margin:0 0 8px;
  display:flex;gap:10px;align-items:baseline}
.dsect h3 small{letter-spacing:0;text-transform:none;font-family:var(--font-mono);
  color:var(--text-dim)}
.dacts{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0 0;
  padding:12px;border:1px dashed var(--edge);border-radius:var(--r-md)}
.dacts form{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0}
.dacts .hint{font-size:var(--text-caps);color:var(--text-dim);flex-basis:100%}
.tcalls{width:100%;border-collapse:collapse}
.tcalls th{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);color:var(--text-dim);text-align:left;font-weight:400;
  padding:0 10px 6px 0}
.tcalls th.r,.tcalls td.r{text-align:right}
.tcalls td{border-top:1px solid var(--edge);padding:6px 10px 6px 0;font-size:var(--text-xs);
  color:var(--text-muted);vertical-align:top;font-family:var(--font-mono)}
.tcalls td.n{color:var(--text-dim);white-space:nowrap}
.tcalls td.nm{color:var(--text);white-space:nowrap}
.tcalls td.a{max-width:0;width:60%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tcalls tr.trow{cursor:pointer}
.tcalls tr.tout td{border-top:0;padding-top:0}
.tcalls tr.tout pre{margin:0 0 6px;padding:8px 11px;background:var(--surface-0);
  border:1px solid var(--edge);border-radius:var(--r-sm);white-space:pre-wrap;
  overflow-wrap:anywhere;max-height:260px;overflow:auto;font-size:var(--text-caps);
  color:var(--text-muted)}
.tcalls tr.tout{display:none}
.tcalls tr.tout.on{display:table-row}
pre.prompt,pre.jsonv{margin:0;padding:12px 14px;background:var(--surface-0);
  border:1px solid var(--edge);border-radius:var(--r-sm);white-space:pre-wrap;
  overflow-wrap:anywhere;max-height:440px;overflow:auto;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-muted);line-height:1.55}
.vres{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 8px;
  font-size:var(--text-xs);color:var(--text-muted)}
.vres ul{margin:4px 0 0;padding-left:18px;font-size:var(--text-xs);color:var(--danger)}
.memlist{margin:0;padding-left:18px;font-size:var(--text-xs);color:var(--text-muted);
  line-height:1.55}
.memlist li{margin-bottom:6px}
.memlist .tm{font-family:var(--font-mono);color:var(--text-dim)}
.dnote{font-size:var(--text-xs);color:var(--text-dim);line-height:1.55}
details.dfold{border:1px solid var(--edge);border-radius:var(--r-md);
  background:var(--surface-0);margin:8px 0 0}
details.dfold summary{cursor:pointer;padding:9px 14px;font-size:var(--text-xs);
  color:var(--text-muted);font-weight:600}
details.dfold[open] summary{border-bottom:1px solid var(--edge)}
details.dfold .inner{padding:10px 14px 14px}
details.dfold .prose{padding:0}

/* ── traceability matrix ──────────────────────────────────────────────── */
.mwrap{overflow-x:auto;margin-top:14px}
.matrix{border-collapse:collapse;min-width:900px;width:100%}
.matrix th{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);color:var(--text-dim);text-align:left;font-weight:400;
  padding:0 12px 8px 0;vertical-align:bottom}
.matrix th small{display:block;letter-spacing:0;text-transform:none;
  font-family:var(--font-mono);margin-top:2px}
.matrix td{border-top:1px solid var(--edge);padding:9px 12px 9px 0;font-size:var(--text-xs);
  color:var(--text-muted);vertical-align:top}
.matrix td.ac{font-family:var(--font-mono);color:var(--text);white-space:nowrap;
  position:sticky;left:0;background:var(--surface-0)}
.matrix td.txt{min-width:260px;max-width:420px;color:var(--text);line-height:1.5}
.matrix td.txt small{display:block;color:var(--text-dim);margin-top:3px}
.matrix .cell{display:flex;flex-direction:column;gap:4px;align-items:flex-start}
.matrix .cell .d{font-family:var(--font-mono);font-size:var(--text-caps);color:var(--text-dim);
  max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chip.none{color:var(--text-dim);border-style:dashed;background:transparent}
.msum{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0 0;font-size:var(--text-xs);
  color:var(--text-muted);align-items:center}
.msum b{color:var(--text);font-family:var(--font-mono)}
.mnotes{margin:12px 0 0;font-size:var(--text-xs);color:var(--text-dim);line-height:1.6}
.mnotes code{font-family:var(--font-mono)}

/* ── factory catalog ──────────────────────────────────────────────────── */
.cat{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;
  margin:12px 0 4px}
.ccard{background:var(--surface-1);border:1px solid var(--edge);
  border-top:1px solid var(--edge-top);border-radius:var(--r-md);padding:13px 15px}
.ccard .cn{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text);display:flex;gap:8px;align-items:center;
  flex-wrap:wrap}
.ccard .cn .chip{margin-left:auto}
.ccard .cm{font-size:var(--text-xs);color:var(--text-muted);line-height:1.5;margin:7px 0 0}
.ccard{overflow:hidden}
.ccard .cr{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim)}
/* A long tool list wraps inside its card instead of running off the edge — the
   roster is read at a glance, and clipped text reads as a rendering fault. */
.ccard .cr span{min-width:0;overflow-wrap:anywhere;line-height:1.5}
.cattbl{width:100%;border-collapse:collapse;margin-top:8px}
.cattbl th{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);color:var(--text-dim);text-align:left;font-weight:400;
  padding:0 12px 8px 0}
.cattbl td{border-top:1px solid var(--edge);padding:8px 12px 8px 0;font-size:var(--text-xs);
  color:var(--text-muted);vertical-align:top}
.cattbl td.m{font-family:var(--font-mono);color:var(--text);white-space:nowrap}
.cattbl td code{font-family:var(--font-mono);color:var(--text-muted);overflow-wrap:anywhere}
.cattbl td.dim{color:var(--text-dim)}
.envnote{font-size:var(--text-caps);color:var(--text-dim);margin:8px 0 0;line-height:1.6}

/* ── cost ─────────────────────────────────────────────────────────────── */
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
.trip{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;
  margin:14px 0 0}
.tripc{background:var(--surface-1);border:1px solid var(--edge);border-radius:var(--r-md);
  padding:13px 15px}
.tripc .tn{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text-muted);display:flex;gap:8px;align-items:center}
.tripc .tn .chip{margin-left:auto}
.tripc .tv{font-family:var(--font-mono);font-size:var(--text-lg);margin:8px 0 4px;
  font-variant-numeric:tabular-nums}
.tripc .tv small{font-size:var(--text-xs);color:var(--text-dim)}
.tripc .tbar{height:6px;background:var(--surface-3);border-radius:var(--r-pill);
  overflow:hidden;margin:8px 0}
.tripc .tbar i{display:block;height:100%;background:var(--dawn-2)}
.tripc .tbar i.over{background:var(--danger)}
.tripc .tbar i.warn{background:var(--warning)}
.tripc .td{font-size:var(--text-caps);color:var(--text-dim);line-height:1.6}
.tripc .marks{display:flex;gap:10px;flex-wrap:wrap;margin-top:6px}
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
p.sub{font-size:var(--text-xs);color:var(--text-muted);margin:0 0 10px;max-width:96ch}
p.sub code{font-family:var(--font-mono)}

/* keyboard help overlay */
.khelp{position:fixed;right:22px;bottom:22px;width:min(380px,calc(100vw - 44px));
  background:var(--surface-2);border:1px solid var(--edge);border-radius:var(--r-lg);
  box-shadow:var(--shadow);padding:16px 18px;z-index:60;display:none}
.khelp.on{display:block}
.khelp h3{font-family:var(--font-label);text-transform:uppercase;letter-spacing:.14em;
  font-size:var(--text-caps);color:var(--text-muted);font-weight:400;margin:0 0 10px}
.khelp .kr{display:flex;gap:12px;align-items:baseline;font-size:var(--text-xs);
  color:var(--text-muted);padding:3px 0}
.khelp .kr span:last-child{margin-left:auto;text-align:right}

/* ── chat: the conversation shell (docs/CHAT.md) ──────────────────────── */
/* The shell is a fixed frame: the two columns scroll inside it, the page
   itself never does. Without min-height:0 a grid/flex child floors at its
   content height, so a long transcript pushed the whole window around
   instead of scrolling under a pinned header and composer. */
.chatwrap{display:grid;grid-template-columns:288px minmax(0,1fr);
  height:calc(100vh - 54px);min-height:0;overflow:hidden}
.chatside{border-right:1px solid var(--edge);overflow-y:auto;min-height:0;
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

.chatmain{display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden}
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

.transcript{flex:1;min-height:0;overflow-y:auto;padding:6px 28px 26px;
  overflow-anchor:none;overscroll-behavior:contain}
.tinner{max-width:920px;margin:0 auto}
.turn{max-width:920px;margin:0 auto}
/* Grows so the newest question can sit at the top of the window, shrinks as
   the answer fills it — the frame stays still while text streams in. */
.tailpad{height:0}
.msg{padding:16px 0 4px}
.msg .who{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.15em;font-size:var(--text-caps);color:var(--text-dim);
  display:flex;align-items:baseline;gap:10px}
.msg .who .tm{font-family:var(--font-mono);letter-spacing:0;margin-left:auto}
.msg.you .who{color:var(--night-3)}
.msg.agent .who{color:var(--dawn-3)}
.msg .who .copy{margin-left:auto;background:none;border:1px solid transparent;
  border-radius:var(--r-pill);color:var(--text-dim);cursor:pointer;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.13em;
  font-size:var(--text-caps);padding:2px 9px;opacity:0;transition:opacity .12s}
.msg.agent:hover .who .copy,.msg .who .copy:focus{opacity:1}
.msg .who .copy:hover{color:var(--text-muted);border-color:var(--edge)}
.msg .utext{font-size:var(--text-base);color:var(--text);line-height:1.6;
  margin-top:6px;white-space:pre-wrap;overflow-wrap:anywhere}
.msg .atext{margin-top:6px}
.msg .atext.streaming{white-space:pre-wrap;font-size:var(--text-sm);
  line-height:1.65;color:var(--text-muted);max-width:92ch}
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
details.workfold{margin:10px 0 2px}
details.workfold>summary{cursor:pointer;font-family:var(--font-mono);
  font-size:var(--text-caps);color:var(--text-dim);list-style:none;
  padding:2px 0 2px 16px}
details.workfold>summary:hover{color:var(--text-muted)}
details.workfold>summary::before{content:'▸ '}
details.workfold[open]>summary::before{content:'▾ '}
details.workfold .work{margin-top:4px}
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
  background:var(--danger-soft);border:1px solid var(--danger-edge);border-radius:var(--r-sm);
  padding:9px 12px;margin-top:8px;overflow-wrap:anywhere}
.tstop{font-size:var(--text-xs);color:var(--warning);margin-top:8px}

.workingline{display:flex;align-items:center;gap:9px;margin-top:12px;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.13em;
  font-size:var(--text-caps);color:var(--accent)}
.workingline .dot{background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);
  animation:caret 1.2s steps(2) infinite}
.workingline .hint{color:var(--text-dim);letter-spacing:.11em}
.workingline .stop{margin-left:6px;background:none;border:1px solid var(--edge);
  border-radius:var(--r-pill);color:var(--text-muted);cursor:pointer;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.11em;
  font-size:var(--text-caps);padding:3px 10px}
.workingline .stop:hover{color:var(--danger);border-color:var(--danger-edge)}

.composer{border-top:1px solid var(--edge);padding:14px 28px 10px;position:relative}
.jumplatest{position:absolute;left:50%;top:-46px;transform:translateX(-50%);
  display:none;background:var(--surface-2);border:1px solid var(--edge);
  border-radius:var(--r-pill);color:var(--text-muted);cursor:pointer;
  font-family:var(--font-label);text-transform:uppercase;letter-spacing:.13em;
  font-size:var(--text-caps);padding:6px 14px;box-shadow:var(--shadow)}
.jumplatest.on{display:block}
.jumplatest:hover{background:var(--surface-3);color:var(--text)}
.queued{display:none;flex-direction:column;gap:5px;margin-bottom:8px}
.queued.on{display:flex}
.qchip{display:flex;align-items:baseline;gap:9px;background:var(--surface-1);
  border:1px dashed var(--edge);border-radius:var(--r-sm);padding:6px 10px}
.qchip .ql{font-family:var(--font-label);text-transform:uppercase;
  letter-spacing:.13em;font-size:var(--text-caps);color:var(--accent);flex:0 0 auto}
.qchip .qt{font-size:var(--text-xs);color:var(--text-muted);white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;min-width:0;flex:1}
.qchip .qx{background:none;border:0;color:var(--text-dim);cursor:pointer;
  font-size:15px;line-height:1;padding:0 2px}
.qchip .qx:hover{color:var(--danger)}
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
.cfoot .keys{margin-left:auto;color:var(--text-dim)}
.cfoot .cstat{display:none;align-items:center;gap:7px;color:var(--accent)}
.cfoot .cstat.on{display:inline-flex}
.cfoot .cstat .dot{background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);
  animation:caret 1.2s steps(2) infinite}

/* ── chat hub + agent roster ──────────────────────────────────────────── */
.hub{flex:1;min-height:0;overflow-y:auto;padding:24px 28px}
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
.acard.hero{grid-column:1 / -1;background:var(--hot-bg);
  border-color:var(--hot-edge);padding:16px 18px}
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
.notice{border:1px solid var(--warning-edge);background:var(--warning-soft);color:var(--text-muted);
  border-radius:var(--r-md);padding:11px 14px;font-size:var(--text-xs);
  margin:14px 0;line-height:1.55}
.notice b{color:var(--warning)}

/* ── phone: one column, nothing clipped, the drawer becomes a sheet ───── */
@media (max-width:820px){
  .topbar{gap:14px;padding:11px 14px;flex-wrap:wrap}
  .topbar nav{order:3;flex-basis:100%;gap:16px;padding-top:4px}
  .topbar .right{gap:10px}
  .topbar .right .live b{display:none}
  .page{padding:0 14px 40px}
  .statusline{padding:10px 14px}
  .ledger{padding:12px 14px;gap:22px}
  .inbox{padding:14px 14px 4px}
  .kb{grid-template-columns:1fr;padding:14px;gap:10px}
  .kbcol{display:block}
  .readout{grid-template-columns:repeat(2,1fr);margin:0 -14px}
  .readout>div{padding:14px 16px}
  .readout .cta{display:none}
  .gcard{padding:14px;border-radius:var(--r-md)}
  .gcard .ghead .gage{text-align:left}
  .artbox{max-height:320px}
  .runhead{flex-direction:column;gap:12px}
  .runhead .totals{text-align:left}
  :root{--lane-cols:1fr}
  .lanes .lhead{display:none}
  .lane{gap:8px;padding:10px 12px}
  .lane .lright{justify-content:start;text-align:left}
  .slots{overflow-x:auto;grid-auto-columns:minmax(72px,1fr);
    grid-template-columns:repeat(var(--n,1),minmax(72px,1fr))}
  .drawer{width:100vw;border-left:0}
  .dwrap{padding:0 14px 40px}
  .dgrid{grid-template-columns:repeat(2,1fr)}
  .tcalls td.a{white-space:normal;overflow-wrap:anywhere}
  .evt{grid-template-columns:96px 1fr;gap:8px}
  .evt .ty{grid-column:1 / -1}
  .att,.decided .att{grid-template-columns:96px 1fr;gap:8px}
  .att .er{grid-column:1 / -1}
  .chatwrap{grid-template-columns:1fr;height:auto;min-height:calc(100vh - 54px)}
  .chatside{border-right:0;border-bottom:1px solid var(--edge);max-height:38vh}
  .chathead,.composer{padding-left:14px;padding-right:14px}
  .transcript{padding:6px 14px 20px}
  .hub{padding:16px 14px}
  .khelp{right:12px;bottom:12px}
  .cat{grid-template-columns:1fr}
}
"""

# Boot before first paint: honour the stored theme, else the OS preference. Kept
# tiny and inline in <head> so a light-mode reader never sees a dark flash.
THEME_BOOT = """
<script>
(function(){try{var t=localStorage.getItem('lantern-theme');var r=document.documentElement;
if(t==='light'||t==='dark'){r.dataset.theme=t;}
else if(window.matchMedia&&matchMedia('(prefers-color-scheme: light)').matches){r.classList.add('sys-light');}
}catch(e){}})();
</script>
"""

# The reload keeps the board live without a JS framework: skip whenever the
# operator is typing a note, has opened a fold themselves, is inside the drawer,
# or has a card under keyboard focus — state is never lost under them.
SCRIPT = """
<script>
(function(){
  var t0=Date.now(), pill=document.getElementById('livepill'), touched=false;
  document.addEventListener('toggle', function(e){
    if(e.target.tagName==='DETAILS' && e.target.open) touched=true; }, true);
  setInterval(function(){
    if(!pill) return;
    var s=Math.floor((Date.now()-t0)/1000);
    if(s>=75){pill.classList.add('stale');
      pill.querySelector('b').textContent='Stale '+s+'s';}
  },5000);
  setInterval(function(){
    if(document.querySelector('input:focus,textarea:focus,select:focus')) return;
    if(touched) return;
    if(document.querySelector('.drawer.open,.khelp.on,.kfocus')) return;
    location.reload();
  },30000);
})();
</script>
"""

# Theme toggle, keyboard map, and the execution drawer. Vanilla JS over plain
# links and forms: every action works without it (links open full pages, forms
# post), the script only shortens the path. The map is documented in
# docs/MISSION-CONTROL.md — keep the two in step.
KEYS_JS = """
<script>
(function(){
  var root=document.documentElement;
  function theme(){return root.dataset.theme||(root.classList.contains('sys-light')?'light':'dark');}
  function setTheme(t){root.dataset.theme=t;root.classList.remove('sys-light');
    try{localStorage.setItem('lantern-theme',t);}catch(e){}
    var b=document.getElementById('themebtn'); if(b) b.textContent=(t==='dark'?'light':'dark')+' mode';}
  var tb=document.getElementById('themebtn');
  if(tb){tb.textContent=(theme()==='dark'?'light':'dark')+' mode';
    tb.addEventListener('click',function(){setTheme(theme()==='dark'?'light':'dark');});}

  var drawer=document.getElementById('drawer'), scrim=document.getElementById('dscrim');
  function openDrawer(href){
    if(!drawer) { location.href=href; return; }
    drawer.classList.add('open'); scrim.classList.add('on');
    drawer.innerHTML="<div class='dwrap'><div class='dhead'><span class='caps'>loading execution…</span></div></div>";
    var url=href+(href.indexOf('?')<0?'?':'&')+'fragment=1';
    fetch(url,{credentials:'same-origin'}).then(function(r){
      if(r.status===401||r.status===303){location.href='/login';throw new Error('login');}
      return r.text();}).then(function(h){drawer.innerHTML=h;drawer.setAttribute('tabindex','-1');drawer.focus();
      drawer.scrollTop=0;wireDrawer();}).catch(function(e){
      drawer.innerHTML="<div class='dwrap'><div class='dhead'><span class='caps'>could not load</span></div>"+
        "<p class='dnote'>Open it as a page instead: <a href='"+href+"'>"+href+"</a></p></div>";});
  }
  function closeDrawer(){ if(!drawer) return; drawer.classList.remove('open'); scrim.classList.remove('on');
    var f=focusables()[idx]; if(f) f.focus({preventScroll:true}); }
  function wireDrawer(){
    drawer.querySelectorAll('.dclose').forEach(function(b){b.addEventListener('click',closeDrawer);});
    drawer.querySelectorAll('tr.trow').forEach(function(tr){tr.addEventListener('click',function(){
      var o=tr.nextElementSibling; if(o&&o.classList.contains('tout')) o.classList.toggle('on');});});
  }
  if(scrim) scrim.addEventListener('click',closeDrawer);
  document.addEventListener('click',function(e){
    var a=e.target.closest('a[data-drawer]'); if(!a) return;
    if(e.metaKey||e.ctrlKey||e.shiftKey||e.button!==0) return;
    e.preventDefault(); openDrawer(a.getAttribute('href'));
  });

  var idx=-1;
  function focusables(){return Array.prototype.slice.call(document.querySelectorAll('[data-k]'));}
  function setFocus(i){var items=focusables(); if(!items.length) return;
    idx=((i%items.length)+items.length)%items.length;
    items.forEach(function(x){x.classList.remove('kfocus');});
    var el=items[idx]; el.classList.add('kfocus');
    if(el.tabIndex<0) el.tabIndex=-1;
    el.focus({preventScroll:true}); el.scrollIntoView({block:'center',behavior:'smooth'});}
  document.addEventListener('focusin',function(e){var el=e.target.closest('[data-k]'); if(!el) return;
    var items=focusables(); var i=items.indexOf(el); if(i>=0){idx=i;
      items.forEach(function(x){x.classList.remove('kfocus');}); el.classList.add('kfocus');}});
  function current(){return focusables()[idx]||null;}
  function decide(kind){var el=current(); if(!el) return;
    var f=el.querySelector('form[data-decide]'); if(!f) return;
    var gate=f.dataset.gate, run=f.dataset.run, blocked=f.dataset.blocked==='1';
    var note=f.querySelector('input[name=note]');
    if(kind==='approve'){
      if(!confirm((blocked?'This report says BLOCKED. ':'')+'Approve '+gate+' for '+run+'?')) return;
      f.action=f.dataset.approve; f.submit();
    } else {
      var n=prompt('Reject '+gate+' for '+run+' — note for the audit log (required):', note?note.value:'');
      if(n===null||!n.trim()) return;
      if(note) note.value=n; f.action=f.dataset.reject; f.submit();
    }}
  var help=document.getElementById('khelp');
  function toggleHelp(force){ if(!help) return; help.classList.toggle('on', force); }
  var hb=document.getElementById('helpbtn'); if(hb) hb.addEventListener('click',function(){toggleHelp();});
  document.addEventListener('keydown',function(e){
    var tag=(e.target.tagName||'').toLowerCase();
    if(tag==='input'||tag==='textarea'||tag==='select'||e.target.isContentEditable){
      if(e.key==='Escape') e.target.blur(); return; }
    if(e.metaKey||e.ctrlKey||e.altKey) return;
    switch(e.key){
      case 'j': case 'ArrowDown': if(!drawer||!drawer.classList.contains('open')){e.preventDefault(); setFocus(idx+1);} break;
      case 'k': case 'ArrowUp': if(!drawer||!drawer.classList.contains('open')){e.preventDefault(); setFocus(idx-1);} break;
      case 'Enter': { var el=current(); if(!el) return;
        if(el.hasAttribute('data-drawer')){e.preventDefault(); openDrawer(el.getAttribute('href'));}
        else { var a=el.matches('a[href]')?el:el.querySelector('a[data-open],a.title'); if(a){location.href=a.href;} }
        break; }
      case 'a': decide('approve'); break;
      case 'r': decide('reject'); break;
      case 'o': { var el2=current(); var a2=el2&&(el2.matches('a[href]')?el2:el2.querySelector('a[data-open],a.title')); if(a2) location.href=a2.href; break; }
      case 't': { var t=document.querySelector('a[data-key-t]'); if(t) location.href=t.href; break; }
      case 'h': if(document.body.dataset.page!=='home') location.href='/'; break;
      case 'd': setTheme(theme()==='dark'?'light':'dark'); break;
      case 'Escape': closeDrawer(); toggleHelp(false);
        focusables().forEach(function(x){x.classList.remove('kfocus');}); idx=-1; break;
      case '?': toggleHelp(); break;
    }
  });
})();
</script>
"""

NAV = [("Home", "/"), ("Runs", "/runs"), ("Gates", "/gates"), ("Chat", "/chat"),
       ("Agents", "/agents"), ("Factory", "/factory"), ("Cost", "/cost")]

KEYMAP = [
    ("j / k", "next / previous card or execution"),
    ("Enter", "open it (the run, or the execution drawer)"),
    ("a", "approve the focused gate (asks first)"),
    ("r", "reject the focused gate with a note"),
    ("t", "traceability view of this run"),
    ("h", "home"),
    ("d", "dark / light"),
    ("Esc", "close the drawer, drop focus"),
    ("?", "this map"),
]


def _help_panel() -> str:
    rows = "".join(f"<div class='kr'><span><kbd>{H(k)}</kbd></span><span>{H(d)}</span></div>"
                   for k, d in KEYMAP)
    return f"<div class='khelp' id='khelp'><h3>Keyboard</h3>{rows}</div>"


def page(title: str, body: str, user: str | None = None, active: str = "/",
         clock: str = "", auto_reload: bool = True, kind: str = "") -> str:
    """auto_reload=False for live-streaming pages (chat): the 30s reloader would
    tear down an in-flight SSE transcript; those pages update themselves.
    `kind` tags <body data-page> for the keyboard layer (home/run/gates/…)."""
    head = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{H(title)}</title><link rel='icon' href='data:,'>{THEME_BOOT}{FONTS}"
            f"<style>{CSS}</style></head>")
    if not user:                                       # login page: no shell
        return f"{head}<body>{body}</body></html>"
    tabs = "".join(
        f"<a href='{href}'{' class=on' if href == active else ''}>{H(name)}</a>"
        for name, href in NAV)
    top = (f"<header class='topbar'><a class='wordmark' href='/'>Lantern</a>"
           f"<nav>{tabs}</nav><span class='right'>"
           f"<span class='live' id='livepill'><span class='dot live'></span>"
           f"<b>Live</b>&nbsp;· {H(clock)} UTC</span>"
           f"<button class='tbtn' id='themebtn' type='button' title='d'>theme</button>"
           f"<button class='tbtn' id='helpbtn' type='button' title='?'>?</button>"
           f"<span>{H(user)}</span><a href='/logout'>log out</a></span></header>")
    shell = ("<div class='dscrim' id='dscrim'></div>"
             "<aside class='drawer' id='drawer' aria-label='execution'></aside>" + _help_panel())
    return (f"{head}<body data-page='{H(kind)}'>{top}{body}{shell}{KEYS_JS}"
            f"{SCRIPT if auto_reload else ''}</body></html>")


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


def fmt_k(n) -> str:
    """Compact token count: 1,094,851 → 1,095k; 850 → 850."""
    if not n:
        return "0"
    return f"{n / 1000:,.0f}k" if n >= 1000 else str(int(n))


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


def dur(seconds: float | None) -> str:
    """Execution duration: seconds under a minute keep their unit ('42s'), longer
    spans read like ago() ('4m', '1h 12m')."""
    if seconds is None:
        return "—"
    return ago(seconds)


def json_block(obj, cls: str = "jsonv") -> str:
    import json as _json
    try:
        text = _json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(obj)
    return f"<pre class='{cls}'>{H(text)}</pre>"


def gate_ledger(metrics: list[dict] | None) -> str:
    """The board's gate-latency strip (feat-20260831-gate-latency).
    metrics: [{'value','kind','sub'}, ...] pre-formatted by app.py, one per
    gate type; None means the aggregate query failed — the board must still
    render, so the strip degrades to a plain sentence."""
    head = ("<div class='lhead'><div class='caps'>GATE LATENCY · LAST 30 DAYS"
            "</div><div class='d'>Median time to decision · UTC</div></div>")
    if metrics is None:
        body = ("<div class='lerr'>Gate latency unavailable — refresh. "
                "Pending gates are still shown.</div>")
    else:
        body = "".join(
            f"<div class='lm'><div class='v{' ' + m['kind'] if m['kind'] else ''}'>"
            f"{H(m['value'])}</div><div class='s'>{H(m['sub'])}</div></div>"
            for m in metrics)
    return f"<section class='ledger'>{head}{body}</section>"


def strip(d: dict, hot: bool = False, dim: bool = False) -> str:
    """One run, one row. Keys: href dot id sub stage_label segs chip wait_main
    wait_why elapsed elapsed_cold model_l1 model_l2 tok_l1 tok_l2 money."""
    ch = chip(*d["chip"]) if d.get("chip") else "<span class='caps'>—</span>"
    cls = "strip" + (" hot" if hot else "") + (" dim" if dim else "")
    t_cls = "t cold" if d.get("elapsed_cold") else "t"
    return f"""<a class='{cls}' href='{H(d["href"])}' data-k>
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


def keys_hint(*pairs: tuple[str, str]) -> str:
    """Inline keyboard reminder for a section head: keys_hint(('j/k','move'), ...)."""
    return " ".join(f"<kbd>{H(k)}</kbd> {H(v)}" for k, v in pairs)
