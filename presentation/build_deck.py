"""
Generates the OpenGov "Sr Data Platform Engineer" case-study presentation (Part 1:
Platform Architecture & Data Foundation) as a native, editable .pptx.

Run:  python presentation/build_deck.py
Out:  presentation/OpenGov_Data_Platform_CaseStudy.pptx

Design: 16:9, navy theme, white-circle/navy-arrow OpenGov logo mark, one big
data-flow diagram (slide 3), an RBAC diagram (slide 10), a decision-matrix table
(slide 4), and speaker notes on every slide to drive a ~20 minute talk.
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "image.png")   # OpenGov mark

# ----------------------------------------------------------------------------- theme (OpenGov indigo brand)
NAVY   = RGBColor(0x19, 0x15, 0x52)   # deep indigo (title bars, dark slides, dark boxes)
NAVY2  = RGBColor(0x2A, 0x24, 0x70)   # secondary deep indigo
BLUE   = RGBColor(0x3B, 0x34, 0xB8)   # rich indigo (primary box fills)
ACCENT = RGBColor(0x4A, 0x3F, 0xFF)   # OpenGov brand indigo (rules, bullets, arrows)
LAV    = RGBColor(0xA7, 0x9F, 0xFF)   # light lavender (accent text on dark)
LIGHT  = RGBColor(0xEC, 0xEB, 0xFB)   # light panel
CARD   = RGBColor(0xF5, 0xF5, 0xFC)   # card fill
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
INK    = RGBColor(0x1B, 0x1B, 0x33)   # near-black body text
GRAY   = RGBColor(0x5C, 0x5B, 0x77)   # muted
GRAYINK= RGBColor(0x3E, 0x3D, 0x5C)   # sub-bullet text
GREEN  = RGBColor(0x2E, 0xA0, 0x74)   # "build" accent
AMBER  = RGBColor(0xE0, 0x8A, 0x2B)   # "buy" accent
CODEFG = RGBColor(0xE6, 0xE9, 0xF5)   # code text
CODECMT= RGBColor(0x8E, 0xD6, 0xB0)   # code comment

FONT = "Segoe UI"

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = prs.slide_width, prs.slide_height

BLANK = prs.slide_layouts[6]

# ----------------------------------------------------------------------------- helpers
def blank():
    return prs.slides.add_slide(BLANK)

def set_bg(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color

def _noline(shape):
    shape.line.fill.background()

def rect(slide, x, y, w, h, fill, shape=MSO_SHAPE.RECTANGLE, line=None, line_w=1.0):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = fill
    if line is None:
        _noline(s)
    else:
        s.line.color.rgb = line; s.line.width = Pt(line_w)
    s.shadow.inherit = False
    return s

def text_in(shape, text, size=14, color=INK, bold=False, align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE, font=FONT):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = Inches(0.06); tf.margin_right = Inches(0.06)
    tf.margin_top = Inches(0.03); tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color; r.font.name = font
    return tf

def textbox(slide, x, y, w, h):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = Inches(0.04); tf.margin_right = Inches(0.04)
    tf.margin_top = Inches(0.02); tf.margin_bottom = Inches(0.02)
    return tb, tf

def place_logo(slide, cx, cy, size):
    """Place the OpenGov logo image centered at (cx, cy)."""
    slide.shapes.add_picture(LOGO, Inches(cx - size/2), Inches(cy - size/2),
                             Inches(size), Inches(size))

def title_bar(slide, title, kicker=None):
    bar = rect(slide, 0, 0, SW.inches, 1.12, NAVY)
    rect(slide, 0, 1.12, SW.inches, 0.055, ACCENT)          # accent rule
    tb, tf = textbox(slide, 0.55, 0.12, 10.8, 0.92)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    if kicker:
        p0 = tf.paragraphs[0]; r0 = p0.add_run(); r0.text = kicker.upper()
        r0.font.size = Pt(11); r0.font.bold = True; r0.font.color.rgb = LAV; r0.font.name = FONT
        p0.space_after = Pt(1)
        p = tf.add_paragraph()
    else:
        p = tf.paragraphs[0]
    r = p.add_run(); r.text = title
    r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
    place_logo(slide, SW.inches - 0.72, 0.56, 0.6)          # mark in the bar

PAGE = [1]
def footer(slide, n=None):
    PAGE[0] += 1
    tb, tf = textbox(slide, 0.55, 7.06, 8.0, 0.35)
    p = tf.paragraphs[0]; r = p.add_run()
    r.text = "OpenGov Data Platform  ·  Case Study — Viewpoint  ·  Akash Pahilwan"
    r.font.size = Pt(9); r.font.color.rgb = GRAY; r.font.name = FONT
    tb2, tf2 = textbox(slide, SW.inches - 1.4, 7.06, 0.9, 0.35)
    p2 = tf2.paragraphs[0]; p2.alignment = PP_ALIGN.RIGHT; r2 = p2.add_run()
    r2.text = str(PAGE[0]); r2.font.size = Pt(9); r2.font.color.rgb = GRAY; r2.font.name = FONT

def bullets(slide, items, x, y, w, h, base=18):
    """items: list of (level:int, lead:str|None, body:str)."""
    tb, tf = textbox(slide, x, y, w, h)
    for i, (level, lead, body) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8 if level == 0 else 3)
        p.line_spacing = 1.07
        size = base if level == 0 else base - 3
        g = p.add_run()
        g.text = "▸  " if level == 0 else "        –  "
        g.font.size = Pt(size); g.font.name = FONT
        g.font.color.rgb = ACCENT if level == 0 else GRAY
        if lead:
            r = p.add_run(); r.text = lead + ("   " if body else "")
            r.font.bold = True; r.font.size = Pt(size); r.font.color.rgb = INK; r.font.name = FONT
        if body:
            r2 = p.add_run(); r2.text = body
            r2.font.size = Pt(size); r2.font.name = FONT
            r2.font.color.rgb = INK if level == 0 else GRAYINK
    return tb

def takeaway(slide, text, y=6.35):
    bar = rect(slide, 0.55, y, 12.23, 0.5, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    rect(slide, 0.55, y, 0.09, 0.5, ACCENT)
    tb, tf = textbox(slide, 0.8, y, 11.8, 0.5)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    r0 = p.add_run(); r0.text = "Takeaway   "; r0.font.bold = True
    r0.font.size = Pt(13); r0.font.color.rgb = BLUE; r0.font.name = FONT
    r1 = p.add_run(); r1.text = text
    r1.font.size = Pt(13); r1.font.color.rgb = INK; r1.font.name = FONT

def code_box(slide, x, y, w, h, lines, title=None, fs=10):
    """Dark code sketch with light text and green comments."""
    rect(slide, x, y, w, h, NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    tb, tf = textbox(slide, x + 0.16, y + 0.12, w - 0.32, h - 0.24)
    tf.word_wrap = False; tf.vertical_anchor = MSO_ANCHOR.TOP
    first = True
    if title:
        p = tf.paragraphs[0]; p.space_after = Pt(6)
        r = p.add_run(); r.text = title
        r.font.name = "Consolas"; r.font.size = Pt(fs); r.font.bold = True; r.font.color.rgb = LAV
        first = False
    for ln in lines:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.line_spacing = 1.0; p.space_after = Pt(1)
        if "--" in ln:
            idx = ln.index("--"); code, comment = ln[:idx], ln[idx:]
        else:
            code, comment = ln, None
        if code:
            r1 = p.add_run(); r1.text = code
            r1.font.name = "Consolas"; r1.font.size = Pt(fs); r1.font.color.rgb = CODEFG
        if comment:
            r2 = p.add_run(); r2.text = comment
            r2.font.name = "Consolas"; r2.font.size = Pt(fs); r2.font.color.rgb = CODECMT

def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text

def content(title, kicker=None):
    s = blank(); set_bg(s, WHITE); title_bar(s, title, kicker); return s

# ============================================================================= SLIDE 1 — Title
s = blank(); set_bg(s, NAVY)
rect(s, 0, 0, 0.28, SH.inches, ACCENT)                    # left accent band
place_logo(s, 2.0, 2.35, 1.35)
tb, tf = textbox(s, 1.9, 3.45, 10.8, 2.6)
p = tf.paragraphs[0]; r = p.add_run(); r.text = "OpenGov Data Platform"
r.font.size = Pt(46); r.font.bold = True; r.font.color.rgb = WHITE; r.font.name = FONT
p2 = tf.add_paragraph(); p2.space_before = Pt(6)
r2 = p2.add_run(); r2.text = "Platform Architecture & Data Foundation"
r2.font.size = Pt(22); r2.font.color.rgb = LAV; r2.font.name = FONT
p3 = tf.add_paragraph(); p3.space_before = Pt(18)
r3 = p3.add_run(); r3.text = "Case Study — Viewpoint"
r3.font.size = Pt(15); r3.font.color.rgb = RGBColor(0xC7,0xD3,0xE0); r3.font.name = FONT
p4 = tf.add_paragraph()
r4 = p4.add_run(); r4.text = "Akash Pahilwan  ·  Senior Data Platform Engineer"
r4.font.size = Pt(15); r4.font.bold = True; r4.font.color.rgb = WHITE; r4.font.name = FONT
notes(s, "Open with the thesis: I build the factory — the governed foundation that "
         "lets every domain team ship analytics and AI on top, safely and fast. Today "
         "I'll walk foundation -> pipelines -> self-service -> trust & governance, then "
         "close with a forward-looking bet on making the platform AI-ready.")

# ============================================================================= SLIDE 2 — Thesis
s = content("The platform is a product — I build the factory", "Foundation")
bullets(s, [
    (0, "The mandate:", "one governed foundation powering analytics and AI across GTM, Finance, Product, and HR/People."),
    (0, "Federated, not centralized:", "domain teams build on a paved path with guardrails — self-service, not a ticket queue."),
    (0, "Four principles guide every decision:", ""),
    (1, "Governed by default", "— RBAC, masking, and lineage are built in, not bolted on."),
    (1, "Self-service paved path", "— golden templates + IaC modules; onboard a domain in a PR."),
    (1, "Observable & SLA-driven", "— freshness, quality, and cost measured from day one."),
    (1, "IaC-first & reproducible", "— everything is code, tested in CI, rebuildable in any environment."),
], 0.7, 1.5, 12.0, 4.6, base=19)
takeaway(s, "Trust and speed are not a trade-off — the right guardrails deliver both.")
footer(s, 2)
notes(s, "Frame the role: a platform engineer's customer is other engineers/analysts. "
         "The job is to make the right thing the easy thing. Stress federation with "
         "guardrails — central team owns the paved path, domains own their data products. "
         "These four principles recur on every later slide.")

# ============================================================================= SLIDE 3 — Architecture diagram
s = content("Target-state architecture: source → dashboard", "Foundation")

def dbox(x, y, w, h, txt, fill, tc=WHITE, fs=11, bold=False, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    b = rect(s, x, y, w, h, fill, shape=shape)
    text_in(b, txt, size=fs, color=tc, bold=bold)
    return b

def arrow(x, y, w=0.35, h=0.3):
    a = rect(s, x, y, w, h, ACCENT, shape=MSO_SHAPE.RIGHT_ARROW)
    return a

def col_label(x, y, w, txt):
    tb, tf = textbox(s, x, y, w, 0.3)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER; r = p.add_run()
    r.text = txt.upper(); r.font.size = Pt(10); r.font.bold = True
    r.font.color.rgb = BLUE; r.font.name = FONT

top = 1.75
# Col 1 — Sources
col_label(0.55, top-0.32, 2.25, "Sources")
srcs = [("Salesforce  (GTM)", BLUE), ("Marketo  (GTM)", BLUE), ("NetSuite  (Finance)", BLUE),
        ("Telemetry  (Product)", NAVY2), ("Workday  (HR)", BLUE)]
for i,(t,c) in enumerate(srcs):
    dbox(0.55, top + i*0.72, 2.25, 0.58, t, c, fs=10)

# Col 2 — Ingestion
col_label(3.15, top-0.32, 2.5, "Ingestion")
dbox(3.15, top+0.15, 2.5, 1.05, "Fivetran\nmanaged connectors (SaaS)", AMBER, fs=11, bold=True)
dbox(3.15, top+1.55, 2.5, 1.35, "Custom Python\nAWS S3 + Lambda\n(telemetry & APIs)", GREEN, fs=11, bold=True)

# Col 3 — Snowflake
col_label(6.05, top-0.32, 3.65, "Snowflake  +  dbt")
snow = rect(s, 6.05, top, 3.65, 3.55, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line=BLUE, line_w=1.0)
layers = [("RAW  — source-system schemas", NAVY), ("STAGING — cleaned / conformed", BLUE),
          ("MARTS — domain, business-ready", BLUE), ("SANDBOX — analyst scratch", GRAY)]
for i,(t,c) in enumerate(layers):
    dbox(6.28, top+0.24 + i*0.72, 3.2, 0.58, t, c, fs=10)
tb, tf = textbox(s, 6.28, top+3.02, 3.2, 0.4)
p=tf.paragraphs[0]; p.alignment=PP_ALIGN.CENTER; r=p.add_run()
r.text="dbt transforms & tests RAW→STAGING→MARTS"; r.font.size=Pt(9); r.font.italic=True
r.font.color.rgb=BLUE; r.font.name=FONT

# Col 4 — Consumers
col_label(10.05, top-0.32, 2.7, "Consumers")
cons = [("BI & Dashboards", BLUE), ("AI / ML  ·  LLM + RAG", NAVY2), ("Reverse ETL → apps", BLUE)]
for i,(t,c) in enumerate(cons):
    dbox(10.05, top+0.35 + i*0.95, 2.7, 0.72, t, c, fs=11, bold=(i==1))

# arrows between columns
arrow(2.83, top+1.4); arrow(5.68, top+1.4); arrow(9.73, top+1.4)

# cross-cutting foundation band
band = rect(s, 0.55, 5.55, 12.18, 0.62, NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
text_in(band, "FOUNDATION   ·   Terraform (IaC)   ·   RBAC + Dynamic Masking   ·   Observability & Data SLAs   ·   CI/CD",
        size=12, color=WHITE, bold=True)
footer(s, 3)
notes(s, "This is the anchor diagram — walk it left to right. Sources land via Fivetran "
         "(connectorized SaaS) or a custom Python path on AWS (S3 + Lambda) for telemetry "
         "and bespoke APIs. Everything lands in Snowflake RAW, then dbt promotes RAW→STAGING"
         "→MARTS, with SANDBOX for exploration. Consumers are BI, AI/ML + LLM/RAG, and "
         "reverse ETL. The navy band is the cross-cutting foundation that every layer sits "
         "on: IaC, RBAC+masking, observability, CI/CD. Invite the 'why Fivetran here, Lambda "
         "there' question — next slide answers it.")

# ============================================================================= SLIDE 4 — Fivetran vs custom (table)
s = content("Ingestion: buy vs. build", "Pipelines")
rows = [
    ("Dimension", "Fivetran  (buy)", "Custom Python on AWS  (build)"),
    ("Best for", "Connectorized SaaS sources", "High-volume / bespoke sources, no connector"),
    ("Examples", "Salesforce, NetSuite, Workday, Marketo", "Product telemetry, operational APIs"),
    ("Schema drift", "Schema-on-write — auto-evolves its tables", "Schema-on-read — VARIANT + contracts"),
    ("Latency", "Scheduled batch", "Near-real-time — S3 event → Lambda"),
    ("Control", "Low (fully managed)", "Full — custom logic & cost tuning"),
    ("Cost model", "Per-MAR (rows synced)", "Compute — S3 / Lambda / warehouse"),
]
nrows, ncols = len(rows), 3
gf = s.shapes.add_table(nrows, ncols, Inches(0.6), Inches(1.5), Inches(12.13), Inches(4.2))
tbl = gf.table
tbl.columns[0].width = Inches(2.3); tbl.columns[1].width = Inches(4.6); tbl.columns[2].width = Inches(5.23)
for ci in range(ncols):
    tbl.rows[0].height = Inches(0.62)
for ri, row in enumerate(rows):
    for ci, val in enumerate(row):
        cell = tbl.cell(ri, ci)
        cell.text = val
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.12); cell.margin_right = Inches(0.08)
        para = cell.text_frame.paragraphs[0]
        run = para.runs[0]; run.font.name = FONT
        if ri == 0:
            cell.fill.solid(); cell.fill.fore_color.rgb = NAVY
            run.font.size = Pt(14); run.font.bold = True; run.font.color.rgb = WHITE
        else:
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE if ri % 2 else CARD
            run.font.size = Pt(12.5); run.font.color.rgb = INK
            if ci == 0:
                run.font.bold = True; run.font.color.rgb = BLUE
            if ci == 1 and ri > 0:
                run.font.color.rgb = AMBER if val else INK
            if ci == 2 and ri > 0:
                run.font.color.rgb = GREEN
takeaway(s, "Buy the commodity (SaaS connectors), build the differentiator (telemetry scale, cost, custom logic).")
footer(s, 4)
notes(s, "The decision rule: buy vs build on control, cost curve, and whether a reliable "
         "connector exists. Fivetran wins for SaaS — someone else maintains the connector "
         "and absorbs API changes. Telemetry is the opposite: huge volume, simple shape, "
         "cost at Fivetran's per-row pricing would be brutal, and we want near-real-time "
         "via S3 events → Lambda. So we own that path. Be ready to defend the cost math.")

# ============================================================================= SLIDE 5 — Custom connector engineering
s = content("Custom connectors: the hard parts, handled", "Pipelines")
bullets(s, [
    (0, "Schema drift:", "land raw as VARIANT/JSON — schema-on-read; explicit contract + registry; additive evolution; alert on breaking change."),
    (0, "Pagination:", "cursor / keyset over offset; persist a high-water mark; fully resumable from the last checkpoint."),
    (0, "Rate limiting:", "exponential backoff + jitter; honor Retry-After; token-bucket throttle; bounded concurrency."),
    (0, "Reliability & idempotency:", "dedup on a natural key; checkpoint per page/file; failures route to a dead-letter / quarantine."),
    (0, "Reusable by design:", "one config-driven framework, many sources — add a source with config, not a copy-paste."),
], 0.7, 1.55, 12.0, 4.4, base=18)
takeaway(s, "A connector is a distributed-systems problem — treat retries, checkpoints, and drift as first-class.")
footer(s, 5)
notes(s, "This is where hands-on depth shows. Emphasize: never block ingestion on a schema "
         "change — land as VARIANT, evolve additively, and alert. Keyset pagination + a "
         "persisted watermark makes runs resumable. Backoff + Retry-After keeps us a good "
         "API citizen. Idempotency via natural key is what makes re-runs safe — this is the "
         "exact pattern I'll implement in the Part 2 telemetry script.")

# ============================================================================= SLIDE 5B — Schema drift (CI/CD)
s = content("Schema drift when objects ship via CI/CD", "Pipelines")
bullets(s, [
    (0, "Two schemas, two rules:", "the upstream source shape is uncontrolled; our deployed objects change only through reviewed PRs."),
    (0, "Custom path — schema-on-read:", "RAW lands each record as a VARIANT; a new source field needs zero DDL, zero deploy — typed at read time in dbt."),
    (0, "Detect, don't auto-alter:", "compare the payload to a registered contract — additive → log + surface; breaking → alert + quarantine. CI/CD never mutates a live table from drift."),
    (0, "Promote a field = a pull request:", "expose it by adding one typed column in dbt; CI runs contracts + tests; review + merge deploys it."),
    (0, "Fivetran — schema-on-write:", "it types columns and ALTERs its own RAW tables on drift; the dbt source contract + tests are our CI tripwire one layer down."),
], 0.65, 1.5, 7.05, 4.7, base=16.5)
code_box(s, 8.0, 1.6, 4.78, 4.55, [
    "-- RAW - schema-on-read (stable DDL)",
    "CREATE OR ALTER TABLE",
    "  raw.product_events.page_views (",
    "  event_id  STRING,   -- promoted key",
    "  loaded_at TIMESTAMP_NTZ,",
    "  _filename STRING,",
    "  payload   VARIANT   -- new fields",
    ");                    -- land here, no PR",
    "",
    "-- STAGING (dbt) - type late",
    "SELECT",
    " payload:event_id::string  AS event_id,",
    " payload:properties.duration_ms::int",
    "                           AS duration_ms",
    "FROM {{ source('product_events',",
    "               'page_views') }}",
    "-- expose a field = one line, via PR",
], title="drift: land loose, type in a PR")
takeaway(s, "Upstream drift lands safely in VARIANT; the deployed schema changes only through a reviewed, tested PR — drift is a blocking CI signal, not silent breakage.")
footer(s)
notes(s, "This directly answers 'we deploy objects via CI/CD — how does drift fit?'. Separate "
         "the two schemas. The SOURCE shape is uncontrolled and can change any time; OUR "
         "objects are code and change only via a reviewed, tested PR. RAW uses a VARIANT "
         "column so upstream additions need no DDL and never break a load — CI/CD does not "
         "run on every upstream change. Drift is detected against a contract and surfaced "
         "(additive) or quarantined + alerted (breaking), but never auto-alters a deployed "
         "table. To make a new field real, an engineer adds one typed column in dbt via a "
         "PR; contracts + tests run in CI as the tripwire. Fivetran is the contrast: it is "
         "schema-on-WRITE — it types columns and ALTERs its own RAW tables when the source "
         "drifts — so the read-time boundary moves one layer down: dbt sources select only "
         "the columns we depend on, and the source contract + tests fail CI before bad data "
         "flows downstream. Crisp framing if pushed: schema-on-read is a property of the RAW "
         "layer. In the custom path we own RAW, so we land VARIANT and type late; in the "
         "Fivetran path Fivetran owns and evolves RAW, so our read-time contract is the dbt "
         "source. Either way, a new field enters the deployed model only through a reviewed "
         "PR. Use CREATE OR ALTER / additive, idempotent migrations so redeploys are safe "
         "on half-failures.")

# ============================================================================= SLIDE 6 — Reliable landing
s = content("Reliable landing in Snowflake", "Pipelines")
bullets(s, [
    (0, "Partitioned landing zone:", "S3 keys as source/table/ingest_date=… — immutable, append-only, replayable."),
    (0, "File formats:", "JSON → VARIANT for semi-structured; Parquet for large columnar; compressed; bounded file sizes."),
    (0, "Load path:", "external stage + COPY INTO, or Snowpipe on arrival; capture METADATA$FILENAME for lineage."),
    (0, "Quality gates at load:", "validate required fields; bad rows → _QUARANTINE table; never fail the whole batch on one row."),
    (0, "Observability:", "a _LOAD_LOG row per file — records processed, quarantined, load timestamp."),
    (0, "Idempotent:", "dedup on natural key so re-loading a file is a no-op."),
], 0.7, 1.55, 12.0, 4.4, base=18)
takeaway(s, "RAW is immutable truth — validate and quarantine at the door, log every load.")
footer(s, 6)
notes(s, "RAW is the system of record — never mutate it. Partition for replay and cheap "
         "pruning. The quarantine + load-log pattern gives operability: you can always "
         "answer 'did the 09:00 file land, and how many rows did we reject?' This maps "
         "one-to-one to the PAGE_VIEWS ingestion I build in Part 2, including the "
         "intentional null user_id record that gets quarantined.")

# ============================================================================= SLIDE 7 — Layer model
s = content("Snowflake layer model & environment strategy", "Foundation")
bullets(s, [
    (0, "Database-per-layer:", "RAW → STAGING → MARTS → SANDBOX; clear ownership and blast-radius per layer."),
    (1, "RAW", "— loader-owned, immutable, source-system schemas, no business logic."),
    (1, "STAGING", "— dbt-owned; typed, renamed, conformed; light transforms."),
    (1, "MARTS", "— dbt-owned; business-ready, domain schemas, tested & documented."),
    (1, "SANDBOX", "— analyst scratch; safe to break, no downstream dependencies."),
    (0, "Warehouse strategy:", "separate ingest / transform / BI warehouses; right-sized; auto-suspend for cost."),
    (0, "Environments:", "dev and prod isolated; promotion through CI, never manual edits in prod."),
], 0.7, 1.5, 12.0, 4.7, base=18)
takeaway(s, "Layers give ownership and blast-radius control; warehouses give workload & cost isolation.")
footer(s, 7)
notes(s, "Database-per-layer (vs schema-per-layer) gives cleaner grants and isolation, and "
         "scales to many domains: RAW holds source schemas, MARTS holds domain schemas. "
         "Separate warehouses stop a heavy dbt run from starving BI, and make cost "
         "attributable. Prod is only ever changed through CI.")

# ============================================================================= SLIDE 8 — dbt multi-domain
s = content("dbt for many domains — without a monolith", "Pipelines")
bullets(s, [
    (0, "Layered models:", "staging (1:1 with source) → intermediate → marts (by domain)."),
    (0, "Organize by domain, not by one giant project:", "folders + CODEOWNERS per domain (revops, finance, product, hr)."),
    (0, "dbt Mesh:", "each domain exposes PUBLIC models via contracts; consumers depend on stable interfaces, not internals."),
    (0, "Quality is code:", "generic + singular tests, model contracts, source freshness, exposures for BI/AI lineage."),
    (0, "Incremental vs full-refresh:", "incremental for high-volume events (telemetry); full-refresh for small dimensions."),
    (0, "Fast CI:", "slim CI builds only state:modified+ — seconds, not full rebuilds."),
], 0.7, 1.55, 12.0, 4.5, base=18)
takeaway(s, "Contracts + dbt Mesh let domains move independently while consumers stay safe.")
footer(s, 8)
notes(s, "The 1-to-10-domains question lives here. Answer: don't grow one monolith — split "
         "by domain with clear ownership, and use dbt Mesh contracts as the interface "
         "between domains. Public models are the API; internals can refactor freely. "
         "Incremental vs full-refresh is a volume/cost decision. Mention mart_revops__"
         "pipeline (Part 2) would be exposed as a PUBLIC contracted model.")

# ============================================================================= SLIDE 9 — Self-service onboarding
s = content("Self-service: onboard a domain in a pull request", "Self-service")
bullets(s, [
    (0, "One Terraform module — domain_workspace:", "input a domain name, get a full, governed workspace."),
    (1, "Provisions", "schemas (staging / marts / sandbox), functional + access roles, service accounts, a warehouse."),
    (1, "Applies", "default grants, PII tags, cost limits, and naming standards automatically."),
    (0, "Golden-path templates:", "starter dbt project, connector config, and CI workflow scaffolded for the team."),
    (0, "PR-driven:", "a domain is onboarded by opening a PR — reviewed, planned, applied by CI. No tickets."),
    (0, "Outcome:", "consistent and governed by construction; hours, not weeks; the platform team doesn't become the bottleneck."),
], 0.7, 1.5, 12.0, 4.7, base=18)
takeaway(s, "The paved path makes the governed way the easiest way — self-service without losing control.")
footer(s, 9)
notes(s, "This is the 'factory' payoff and a differentiator vs teams that hand-craft each "
         "domain. A single opinionated Terraform module encodes all standards, so every "
         "new domain is born compliant. Teams self-serve via PR; the platform team reviews "
         "the module, not every request. This is how RBAC actually scales to 10 domains — "
         "it's generated, not hand-written.")

# ============================================================================= SLIDE 10 — RBAC diagram
s = content("RBAC at scale: functional + access roles", "Trust & Governance")

def node(x, y, w, h, txt, fill, tc=WHITE, fs=11, bold=True):
    b = rect(s, x, y, w, h, fill, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    text_in(b, txt, size=fs, color=tc, bold=bold); return b

def hint(x, y, w, txt):
    tb, tf = textbox(s, x, y, w, 0.3)
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER; r = p.add_run()
    r.text = txt.upper(); r.font.size = Pt(10); r.font.bold = True; r.font.color.rgb = BLUE; r.font.name = FONT

ytop = 1.95
hint(0.6, ytop-0.35, 2.6, "Users")
node(0.6, ytop+0.15, 2.6, 0.6, "OPENGOV_ANALYST", BLUE, fs=10)
node(0.6, ytop+0.95, 2.6, 0.6, "OPENGOV_DBT_SVC", NAVY2, fs=10)
node(0.6, ytop+1.75, 2.6, 0.6, "human  vs  service", GRAY, fs=10, bold=False)

hint(3.75, ytop-0.35, 2.9, "Functional roles (job)")
node(3.75, ytop+0.05, 2.9, 0.6, "REVOPS_ANALYST", BLUE, fs=11)
node(3.75, ytop+0.85, 2.9, 0.6, "REVOPS_DEVELOPER", BLUE, fs=11)
node(3.75, ytop+1.65, 2.9, 0.6, "REVOPS_ADMIN", NAVY, fs=11)

hint(7.25, ytop-0.35, 2.7, "Access roles (grants)")
node(7.25, ytop+0.05, 2.7, 0.55, "AR_MARTS_R", GREEN, fs=10)
node(7.25, ytop+0.75, 2.7, 0.55, "AR_STAGING_R", GREEN, fs=10)
node(7.25, ytop+1.45, 2.7, 0.55, "AR_RAW_RW", GREEN, fs=10)
node(7.25, ytop+2.15, 2.7, 0.55, "AR_SANDBOX_RW", GREEN, fs=10)

hint(10.5, ytop-0.35, 2.3, "Objects")
node(10.5, ytop+0.05, 2.3, 0.55, "MARTS schema", NAVY2, fs=10)
node(10.5, ytop+0.75, 2.3, 0.55, "STAGING schema", NAVY2, fs=10)
node(10.5, ytop+1.45, 2.3, 0.55, "RAW schema", NAVY2, fs=10)
node(10.5, ytop+2.15, 2.3, 0.55, "SANDBOX schema", NAVY2, fs=10)

for x in (3.3, 6.75, 10.05):
    rect(s, x, ytop+1.1, 0.32, 0.28, ACCENT, shape=MSO_SHAPE.RIGHT_ARROW)

tb, tf = textbox(s, 0.6, ytop+2.75, 12.1, 0.5)
p = tf.paragraphs[0]; r = p.add_run()
r.text = "granted to  ►  users     |     inherit  ►  access roles     |     hold privileges on  ►  objects"
r.font.size = Pt(11); r.font.italic = True; r.font.color.rgb = GRAY; r.font.name = FONT
takeaway(s, "Access roles are reused building blocks; add a domain = generate a new set — grants never sprawl.  Row-access policies handle multi-tenant isolation.")
footer(s, 10)
notes(s, "Snowflake's recommended two-tier model: access roles hold object privileges; "
         "functional roles (job-based) inherit access roles; users get functional roles. "
         "Why it scales: access roles are reusable primitives, so a 10th domain is a "
         "generated set of roles — no bespoke grant spaghetti. Service accounts get their "
         "own functional roles (dbt vs human analyst). Row-access policies enforce "
         "tenant/region isolation on shared tables. This exact model is what I build in Part 2.")

# ============================================================================= SLIDE 11 — PII & masking
s = content("PII & column security for Finance / HR", "Trust & Governance")
bullets(s, [
    (0, "Dynamic data masking:", "policies on sensitive columns (ARR, salary, PII) — masked/NULL unless a privileged role."),
    (0, "Tag-based masking:", "tag a column once (PII, FINANCIAL) → policy applies everywhere; scales across domains automatically."),
    (0, "Row access policies:", "tenant / region / business-unit isolation on shared tables — multi-tenant by design."),
    (0, "Auditing:", "ACCESS_HISTORY answers 'who read ACCOUNT.ARR, and when'; ACCOUNT_USAGE for governance reporting."),
    (0, "Least privilege everywhere:", "no static credentials — key-pair / OIDC only; secrets from env / secret manager."),
], 0.7, 1.55, 12.0, 4.4, base=18)
takeaway(s, "Governance is data-driven: tag once, enforce everywhere, and prove access after the fact.")
footer(s, 11)
notes(s, "Enterprise edition gives us dynamic masking, row access policies, and "
         "ACCESS_HISTORY — I confirmed the account is Enterprise. The scaling trick is "
         "TAG-based masking: analysts tag columns; the policy is attached to the tag, so "
         "coverage follows the tag across every table and domain. ACCESS_HISTORY is the "
         "answer to the audit probe on ARR. In Part 2 I implement the ARR masking policy: "
         "NULL below REVOPS_ADMIN, real value for REVOPS_ADMIN.")

# ============================================================================= SLIDE 12 — Observability & SLAs
s = content("Observability & data SLAs from day one", "Trust & Governance")
bullets(s, [
    (0, "Monitor every source & mart:", "freshness, volume, schema, and quality checks — automated, not eyeballed."),
    (0, "Quality as code:", "dbt tests + source freshness run in CI and in production; breaches alert immediately."),
    (0, "Published data SLAs:", "each data product declares freshness, availability, and quality targets — and we measure them."),
    (0, "Pipeline observability:", "run metadata, lineage, and failure alerting to Slack / on-call."),
    (0, "Cost observability:", "per-warehouse / per-domain spend, query monitors, auto-suspend — FinOps built in."),
], 0.7, 1.55, 12.0, 4.4, base=18)
takeaway(s, "If it isn't measured, it isn't trusted — SLAs turn 'the data looks off' into an alert.")
footer(s, 12)
notes(s, "Observability is a day-one concern, not a phase-2 add-on. The mindset: treat data "
         "products like services with SLAs. dbt tests catch quality regressions in CI "
         "before they ship. Cost observability matters because Snowflake spend is "
         "consumption-based — per-domain attribution enables chargeback and keeps the "
         "platform's economics honest.")

# ============================================================================= SLIDE 13 — CI/CD & IaC
s = content("CI/CD & IaC — the delivery backbone", "Trust & Governance")
bullets(s, [
    (0, "Everything as code:", "Terraform (infra + RBAC), dbt (transforms), Python (ingestion) — versioned & reviewed."),
    (0, "PR-gated pipeline:", "plan / lint / test on pull request → apply on merge; dev → prod environments."),
    (0, "Secure auth:", "OIDC or key-pair — no static secrets; fork PRs never see production credentials."),
    (0, "Standards enforced:", "sqlfluff, terraform fmt/validate, naming rules — the linter is the reviewer."),
    (0, "Idempotent & safe:", "scripts re-run cleanly and survive half-failures; a PR comment summarizes changes + tests."),
], 0.7, 1.55, 12.0, 4.4, base=18)
takeaway(s, "The pipeline is the control plane — every change is reviewed, tested, and reversible.")
footer(s, 13)
notes(s, "This is the enforcement mechanism for everything else. Key security points the "
         "panel probes: OIDC/key-pair over passwords, and protecting secrets from malicious "
         "fork PRs (secrets aren't exposed to untrusted PRs; apply only runs post-merge). "
         "Idempotency + half-failure safety is what makes automated provisioning trustworthy. "
         "The PR-comment summary is exactly the CI deliverable in Part 2.")

# ============================================================================= SLIDE 14 — Differentiator
s = content("Beyond the brief: making the platform AI-ready", "Differentiating Perspective")
bullets(s, [
    (0, "The risk:", "AI/LLM consumers will happily query ungoverned data and return confident, wrong answers."),
    (0, "Governed semantic / metrics layer:", "define metrics once (revenue, pipeline, churn) → one source of truth for BI, notebooks, and LLMs."),
    (0, "Data contracts:", "producers commit to schema + semantics; breaking changes are blocked in CI — trust shifts left."),
    (0, "AI consumes products, not raw:", "RAG and agents read documented, contracted marts + the semantic layer — never RAW."),
    (0, "Governance travels to AI:", "masking & row-access policies apply to LLM service accounts too — a model can't leak ARR."),
], 0.7, 1.5, 12.0, 4.5, base=18)
takeaway(s, "Trustworthy AI and trustworthy analytics come from the same governed foundation — the semantic layer is the interface.")
footer(s, 14)
notes(s, "This is my point of view. The trap everyone is walking into: pointing LLMs at raw "
         "warehouses. Without a semantic layer, the model guesses join logic and metric "
         "definitions — confidently wrong. Solution: a governed metrics/semantic layer as "
         "the single interface for humans AND AI, plus data contracts enforced in CI so "
         "definitions can't silently drift. Crucially, Snowflake's masking/row policies "
         "apply to the LLM's service account — governance isn't bypassed by AI. This is how "
         "OpenGov gets trustworthy AI, not just more AI.")

# ============================================================================= SLIDE 15 — Close
s = content("Close: one foundation, analytics and AI on top", "Wrap-up")
bullets(s, [
    (0, "Foundation → pipelines → self-service → trust:", "one governed, IaC-first platform serving every domain."),
    (0, "Buy the commodity, build the differentiator:", "Fivetran for SaaS; custom Python for telemetry & the semantic layer."),
    (0, "Guardrails as paved paths:", "self-service onboarding, RBAC + masking, observability — built in from day one."),
    (0, "Key tradeoffs I'll defend:", "Fivetran vs custom, incremental vs full-refresh, centralized vs federated (dbt Mesh)."),
    (0, "Next — the hands-on build (RevOps):", "RBAC + ARR masking · S3→Snowflake ingestion · dbt marts · PR-gated CI/CD."),
], 0.7, 1.5, 12.0, 4.6, base=18)
takeaway(s, "The measure of the platform: how fast a federated team can ship something trustworthy on top of it.")
footer(s, 15)
notes(s, "Recap the four-part arc and restate the thesis. Signal you're ready for the "
         "hands-on deep dive and for tradeoff questions. End on the platform-as-product "
         "line — the success metric is federated teams shipping trustworthy data & AI "
         "products quickly, safely, and independently.")

# ============================================================================= SLIDE 16 — BONUS (hidden): VARIANT internals
s = content("Why VARIANT stays fast at scale", "Internals · Bonus")
bullets(s, [
    (0, "Not a text blob:", "each micro-partition shreds consistent JSON paths into typed, compressed sub-columns with min/max stats — native-column treatment."),
    (0, "Projection works:", "selecting payload:properties.duration_ms reads only that sub-column off disk — never the whole document."),
    (0, "Pruning works:", "filters on extracted paths skip whole micro-partitions via metadata — scan cost tracks the answer, not the table."),
    (0, "When it degrades:", "wildly heterogeneous keys defeat sub-columnarization — promote hot filter / dedup keys to real columns (event_id)."),
    (0, "Discipline & limits:", "16 MB per value (events are KBs); missing key → NULL, never an error; TRY_CAST + tests absorb type drift; marts never read payload."),
], 0.65, 1.5, 7.05, 4.7, base=16.5)
code_box(s, 8.0, 1.6, 4.78, 4.55, [
    "-- inside one micro-partition,",
    "-- payload VARIANT is stored as:",
    "--  :event_id            -> sub-col",
    "--  :account_id          -> sub-col",
    "--  :properties.duration_ms -> sub-col",
    "--  ...each with min/max stats",
    "",
    "-- projection: reads ONE sub-column",
    "SELECT payload:properties.duration_ms",
    "FROM raw.product_events.page_views",
    "",
    "-- pruning: skips micro-partitions",
    "WHERE payload:event_timestamp",
    "      ::timestamp_ntz >= '2026-07-01'",
    "",
    "-- drift-safe typing in staging",
    "TRY_CAST(payload:properties.duration_ms",
    "         AS INT)  -- bad value -> NULL",
], title="VARIANT internals — sketch")
takeaway(s, "Schema-on-read is nearly free at query time — consistent paths are columnarized on write; type once in staging, downstream never parses JSON.")
footer(s)
notes(s, "BONUS / HIDDEN — pull up only if the panel digs into VARIANT performance. Key "
         "message: VARIANT is not a JSON string column. On write, Snowflake examines paths "
         "that occur consistently across rows in a micro-partition and stores each as its "
         "own typed, compressed sub-column with min/max metadata — so path projection and "
         "partition pruning behave like native columns. It degrades only when keys are "
         "wildly inconsistent row-to-row; the fix is promoting hot keys (event_id) to real "
         "columns, which we do anyway for dedup. Drift behavior: missing key reads as NULL "
         "(never an error), new keys are invisible until a PR selects them, and TRY_CAST + "
         "dbt tests turn type drift into a quarantine signal instead of a failed job. "
         "16 MB/value limit is ~4 orders of magnitude above a telemetry event. One-breath "
         "close: 'stable RAW DDL, columnarized paths, type once in incremental staging — "
         "downstream never touches JSON.'")
s._element.set('show', '0')                                  # hidden in slideshow

# ============================================================================= SLIDE 17 — BONUS (hidden): S3 layout & hourly loads
s = content("S3 layout & hourly loads — append-only RAW", "Internals · Bonus")
bullets(s, [
    (0, "One prefix per source object:", "source/object/dt=YYYY-MM-DD/hr=HH/ — hourly runs list one narrow prefix; backfill = re-point at a date range; lifecycle rules attach per prefix."),
    (0, "Append new files, never replace:", "RAW is an immutable log, not a mirror — 'latest' applies to which files we read this run, not to what we keep."),
    (0, "Idempotent in three layers:", "COPY's 64-day file-load history (re-run loads zero) · _LOAD_LOG watermark + trailing-window rescan for late files · event_id dedup in staging."),
    (0, "Full refresh without mutation:", "COPY FORCE=TRUE into a fresh table, then ALTER TABLE SWAP — rebuild history, never edit it."),
    (0, "COPY now, Snowpipe next:", "scheduled Python + COPY keeps validation / quarantine / _LOAD_LOG in code; production evolution: Snowpipe auto-ingest per S3 event, no scheduler."),
], 0.65, 1.5, 7.05, 4.7, base=16.5)
code_box(s, 8.0, 1.6, 4.78, 4.55, [
    "s3://og-telemetry/",
    "  product_events/page_views/",
    "    dt=2026-07-12/hr=14/",
    "      page_views_1430_part001.json.gz",
    "    dt=2026-07-12/hr=15/ ...",
    "",
    "-- hourly job: append new files only",
    "COPY INTO raw.product_events.page_views",
    "FROM @s3_stage/page_views/dt=2026-07-12/",
    "FILE_FORMAT = (TYPE = 'JSON');",
    "-- 64-day file history: re-run = 0 rows",
    "",
    "-- staging: producer resends -> 1 row",
    "QUALIFY ROW_NUMBER() OVER (",
    "  PARTITION BY event_id",
    "  ORDER BY loaded_at DESC) = 1",
], title="land hourly, append-only")
takeaway(s, "Copy only the latest files, keep every row — append-only RAW plus three idempotency layers makes any re-run or backfill safe.")
footer(s)
notes(s, "BONUS / HIDDEN — pull up if asked about bucket layout, hourly cadence, or 'why not "
         "Snowpipe'. Hive-style dt=/hr= prefixes sort lexicographically by time, so the "
         "watermark is just the last processed prefix; re-scan a trailing 24-48h window so "
         "late-arriving files in an old hour still load (COPY's file history dedups the "
         "overlap for free). Append-only stance: never 'replace with latest' — RAW keeps "
         "every loaded row; dedup and current-state are computed in staging (QUALIFY on "
         "event_id). Snowpipe question: for the case-study deliverable I keep a scheduled "
         "Python job + COPY, because the assessed logic — schema validation, quarantine, "
         "_LOAD_LOG summary — lives in that code, and hourly batch on an XS warehouse is "
         "cheap. In production, with files landing continuously, I'd flip to Snowpipe: S3 "
         "event notification -> per-file auto-ingest, exactly-once per file, ~1-minute "
         "latency, no scheduler or watermark logic at all; validation then moves to a "
         "post-load stream/task. Same table, same append-only contract — only the trigger "
         "changes. 64-day detail: COPY's per-file load history EXPIRES after 64 days. A "
         "backfill touching older files is silently SKIPPED by default (status unknown -> "
         "skip, no error — a silent gap, not duplicates). Deliberate old backfill: set "
         "LOAD_UNCERTAIN_FILES=TRUE (staging's event_id dedup absorbs any repeats) or "
         "FORCE=TRUE into a fresh table + SWAP. This expiry is exactly why the design has "
         "three layers — COPY history expires, a watermark can miss late files, so event_id "
         "dedup in staging is the backstop that never expires.")
s._element.set('show', '0')                                  # hidden in slideshow

# ============================================================================= SLIDE 18 — BONUS (hidden): COPY logs & 64-day horizon
s = content("COPY INTO — load logs & the 64-day horizon", "Internals · Bonus")
bullets(s, [
    (0, "COPY returns a per-file result set:", "rows_parsed / rows_loaded / errors per file — the Python job persists it to _LOAD_LOG; ours never expires."),
    (0, "Built-in audit views:", "COPY_HISTORY table function = 14 days, per table; ACCOUNT_USAGE = 365 days, account-wide (~90 min lag)."),
    (0, "The 64-day dedup horizon:", "the internal metadata COPY uses to skip already-loaded files expires after 64 days — separate from the audit views."),
    (0, "Beyond 64 days = silent skip:", "unknown-status files are skipped — a silent gap, not duplicates; backfill via LOAD_UNCERTAIN_FILES=TRUE or FORCE + SWAP."),
    (0, "Why three layers:", "COPY history expires · watermarks miss late files · event_id dedup in staging never expires."),
], 0.65, 1.5, 7.05, 4.7, base=16.5)
code_box(s, 8.0, 1.6, 4.78, 4.55, [
    "-- COPY's return: per-file summary",
    "--  file | status | rows_parsed |",
    "--  rows_loaded | first_error ...",
    "--  -> Python writes it to _LOAD_LOG",
    "",
    "-- audit: last 14 days, this table",
    "SELECT file_name, last_load_time,",
    "       row_count, error_count",
    "FROM TABLE(information_schema",
    "  .copy_history(",
    "   table_name => 'PAGE_VIEWS',",
    "   start_time => dateadd(day, -14,",
    "     current_timestamp())));",
    "",
    "-- audit: 365 days, account-wide",
    "SELECT * FROM snowflake",
    "  .account_usage.copy_history;",
    "",
    "-- backfill older than 64 days",
    "COPY INTO ...",
    "  LOAD_UNCERTAIN_FILES = TRUE;",
], title="every load is observable")
takeaway(s, "Snowflake logs every COPY (14-day / 365-day views) and returns a per-file summary — persisting it in _LOAD_LOG gives an audit trail that outlives every retention window.")
footer(s)
notes(s, "BONUS / HIDDEN — pull up for 'can we see what COPY loaded?' or the 64-day "
         "follow-up. Three observable layers: (1) COPY INTO itself returns a result set — "
         "one row per file with status, rows_parsed, rows_loaded, errors_seen, first_error "
         "— and the Part 2 Python job captures exactly this into _LOAD_LOG, which is the "
         "brief's load-summary requirement and lives forever. (2) COPY_HISTORY / "
         "LOAD_HISTORY: INFORMATION_SCHEMA table functions keep 14 days per table; "
         "SNOWFLAKE.ACCOUNT_USAGE views keep 365 days account-wide with up to ~90 min "
         "latency — these are audit/observability surfaces. (3) Distinct from both: the "
         "internal per-file dedup metadata COPY consults to skip already-loaded files — "
         "64-day lifetime, not directly queryable. Beyond 64 days the load status is "
         "'unknown' and COPY silently SKIPS the file by default (gap, not duplicates); "
         "deliberate backfills set LOAD_UNCERTAIN_FILES=TRUE and let staging's event_id "
         "dedup absorb repeats, or rebuild with FORCE=TRUE + SWAP. Close with the "
         "three-layer line: history expires, watermarks miss late files, staging dedup "
         "never expires.")
s._element.set('show', '0')                                  # hidden in slideshow

# ----------------------------------------------------------------------------- save
out = __file__.rsplit("\\", 1)[0] + "\\OpenGov_Data_Platform_CaseStudy.pptx"
prs.save(out)
print("Saved:", out)
print("Slides:", len(prs.slides._sldIdLst))
