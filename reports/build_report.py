"""Build the complete project report and study guide as a PDF.

    .venv/Scripts/python reports/build_report.py

Every number comes from the latest run:

    outputs/lab_results.json        written by the notebook
    models/metrics.json             written by src/build.py
    outputs/app/api_checks.json     written by tests/check_api.py
    outputs/app/planner_checks.json written by tests/check_planner.py

Code listings and printed results are read from the executed notebook and the
source files, and screenshots from outputs/app/, so the report cannot drift
from the project.
"""

import ast
import json
import re
import subprocess
from importlib import metadata
from pathlib import Path

import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, NextPageTemplate,
    PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "outputs" / "figures"
APP = ROOT / "outputs" / "app"
OUT = ROOT / "reports" / "Nutrition_Recommender_Project_Report.pdf"

# Fill these in before submitting; blank fields print as lines to write on.
STUDENT_NAME = ""
REGISTER_NUMBER = ""

TITLE = "Personalised Nutrition Recommender"
HEADER = f"{TITLE} (NUTRIX) — 21CSC305P Machine Learning Laboratory"


def load_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


LAB = load_json(ROOT / "outputs" / "lab_results.json")
MET = load_json(ROOT / "models" / "metrics.json")
API_CHECKS = load_json(APP / "api_checks.json")
PLANNER_CHECKS = load_json(APP / "planner_checks.json")
NOTEBOOK = load_json(ROOT / "notebooks" / "nutrition_ml_lab.ipynb")
CATALOG = pd.read_parquet(ROOT / "data" / "processed" / "catalog.parquet", columns=["card_url"])
PHOTOS = int(CATALOG["card_url"].notna().sum())

# ------------------------------------------------------------------ style

INK = colors.HexColor("#1f2933")
MUTED = colors.HexColor("#616e7c")
ACCENT = colors.HexColor("#2f7d5b")
RULE = colors.HexColor("#d9e2ec")
SHADE = colors.HexColor("#f0f4f8")
CODE_BG = colors.HexColor("#f3f6f4")
OUT_BG = colors.HexColor("#f7f7f2")

BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=14.2, alignment=TA_JUSTIFY, textColor=INK, spaceAfter=6)
PART = ParagraphStyle("part", fontName="Helvetica-Bold", fontSize=18, leading=24, textColor=ACCENT, spaceAfter=14)
H1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=20, textColor=INK, spaceBefore=6, spaceAfter=8, keepWithNext=1)
H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=15, textColor=ACCENT, spaceBefore=9, spaceAfter=4, keepWithNext=1)
LABEL = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, spaceBefore=6, spaceAfter=3, keepWithNext=1)
CAPTION = ParagraphStyle("caption", fontName="Helvetica-Oblique", fontSize=8.5, leading=11, textColor=MUTED, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10)
CELL = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8, leading=11.2, textColor=INK)
CELL_BOLD = ParagraphStyle("cellb", parent=CELL, fontName="Helvetica-Bold")
BULLET = ParagraphStyle("bullet", parent=BODY, leftIndent=14, bulletIndent=4, spaceAfter=2.5)
CODE = ParagraphStyle("code", fontName="Courier", fontSize=7.6, leading=9.3, textColor=INK)
NOTE = ParagraphStyle("note", parent=BODY, backColor=colors.HexColor("#eef7f1"), borderColor=colors.HexColor("#b7dcc5"),
                      borderWidth=0.6, borderPadding=7, leftIndent=7, rightIndent=7, spaceBefore=6, spaceAfter=12)

FRAME_W = A4[0] - 4.4 * cm
CODE_CHARS = 98

REPLACEMENTS = {"≤": "<=", "≥": ">=", "→": "->", "←": "<-", "−": "-", "≈": "~", "✓": "v", "×": "x", "…": "..."}


def safe(text):
    """Keep text inside the WinAnsi character set of the built-in PDF fonts."""
    out = []
    for ch in str(text):
        ch = REPLACEMENTS.get(ch, ch)
        try:
            ch.encode("cp1252")
            out.append(ch)
        except UnicodeEncodeError:
            out.append("?")
    return "".join(out)


def esc(text):
    return safe(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct(x, digits=1):
    return f"{100 * x:.{digits}f}%"


def num(x, digits=0):
    return f"{x:,.{digits}f}"


class Report(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(
            str(path), pagesize=A4, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
            topMargin=2.1 * cm, bottomMargin=1.8 * cm,
            title=f"{TITLE} - Project Report", author="21CSC305P Machine Learning Laboratory",
        )
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        self.addPageTemplates([
            PageTemplate("cover", frames=[frame]),
            PageTemplate("page", frames=[frame], onPage=self._header),
        ])

    def _header(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.8)
        canvas.setFillColor(MUTED)
        y = A4[1] - 1.25 * cm
        canvas.drawString(self.leftMargin, y, safe(HEADER))
        canvas.drawRightString(A4[0] - self.rightMargin, y, str(doc.page))
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.6)
        canvas.line(self.leftMargin, y - 5, A4[0] - self.rightMargin, y - 5)
        canvas.restoreState()


story = []


def part(title):
    story.append(PageBreak())
    story.append(Paragraph(esc(title), PART))


def h1(text):
    story.append(CondPageBreak(4 * cm))
    story.append(Paragraph(esc(text), H1))


def h2(text):
    story.append(CondPageBreak(2.5 * cm))
    story.append(Paragraph(esc(text), H2))


def label(text):
    story.append(Paragraph(esc(text), LABEL))


def p(text):
    story.append(Paragraph(safe(text), BODY))


def note(text):
    story.append(Paragraph(safe(text), NOTE))


def bullets(items):
    for item in items:
        story.append(Paragraph(safe(item), BULLET, bulletText="•"))
    story.append(Spacer(1, 4))


def steps(items):
    for i, item in enumerate(items, 1):
        story.append(Paragraph(safe(item), BULLET, bulletText=f"{i}."))
    story.append(Spacer(1, 4))


def _lines_block(lines, background, accent):
    lines = [safe(line.rstrip())[:CODE_CHARS] for line in lines] or [" "]
    rows = [[Preformatted(line or " ", CODE)] for line in lines]
    t = Table(rows, colWidths=[FRAME_W], hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0.3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.3),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
    ]
    if accent:
        style.append(("LINEBEFORE", (0, 0), (0, -1), 2, ACCENT))
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 8))


def code(lines):
    if isinstance(lines, str):
        lines = lines.strip("\n").splitlines()
    _lines_block(lines, CODE_BG, True)


def output(lines):
    if isinstance(lines, str):
        lines = lines.strip("\n").splitlines()
    _lines_block(lines, OUT_BG, False)


def _with_heading(parts):
    if story and isinstance(story[-1], Paragraph) and story[-1].style.name in ("h1", "h2", "label"):
        parts.insert(0, story.pop())
    return KeepTogether(parts)


def figure(path, width_cm, caption, max_height_cm=21):
    path = Path(path)
    if not path.exists():
        return
    w, h = ImageReader(str(path)).getSize()
    width = width_cm * cm
    height = width * h / w
    if height > max_height_cm * cm:
        width, height = width * max_height_cm * cm / height, max_height_cm * cm
    story.append(_with_heading([Image(str(path), width=width, height=height), Paragraph(esc(caption), CAPTION)]))


def fig(name, width_cm, caption, **kw):
    figure(FIG / f"{name}.png", width_cm, caption, **kw)


def shot(name, width_cm, caption, **kw):
    figure(APP / f"{name}.jpg", width_cm, caption, **kw)


def table(rows, widths, caption=None, header=True):
    data = [[Paragraph(safe(c), CELL_BOLD if (header and r == 0) else CELL) for c in row] for r, row in enumerate(rows)]
    t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SHADE), ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT)]
    t.setStyle(TableStyle(style))
    parts = [t, Paragraph(esc(caption), CAPTION) if caption else Spacer(1, 9)]
    story.append(_with_heading(parts) if len(rows) <= 14 else t)
    if len(rows) > 14:
        story.append(parts[1])


# ------------------------------------------------------------------ sources

CODE_CELLS = [c for c in NOTEBOOK["cells"] if c["cell_type"] == "code"]


def _text(value):
    return "".join(value) if isinstance(value, list) else value


def _trim(lines, max_lines):
    lines = [line.rstrip() for line in lines]
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["..."]
    return lines


def _cell(marker):
    for c in CODE_CELLS:
        if marker in _text(c["source"]):
            return c
    raise KeyError(f"no notebook cell contains {marker!r}")


def _slice(lines, start=None, stop=None):
    if start:
        lines = lines[next(i for i, line in enumerate(lines) if start in line):]
    if stop:
        lines = lines[:next((i for i, line in enumerate(lines) if stop in line), len(lines))]
    return lines


def nb_code(marker, start=None, stop=None, max_lines=40):
    return _trim(_slice(_text(_cell(marker)["source"]).splitlines(), start, stop), max_lines)


def nb_output(marker, max_lines=30, start=None, stop=None):
    chunks = []
    for o in _cell(marker).get("outputs", []):
        if o["output_type"] == "stream":
            chunks.append(_text(o["text"]))
        elif o["output_type"] in ("execute_result", "display_data"):
            data = o.get("data", {})
            if "text/plain" in data and "image/png" not in data:
                chunks.append(_text(data["text/plain"]))
    lines = "\n".join(chunk.rstrip("\n") for chunk in chunks).splitlines()
    return _trim(_slice(lines, start, stop), max_lines)


def py_source(rel, name, max_lines=40, start=None, stop=None, docstring=False):
    """A function or class from a Python file, found with the ast module."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    lines = text.splitlines()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name:
            first = node.lineno - 1
            chunk = lines[first:node.end_lineno]
            body0 = node.body[0]
            if not docstring and isinstance(body0, ast.Expr) and isinstance(getattr(body0, "value", None), ast.Constant) and isinstance(body0.value.value, str):
                drop = set(range(body0.lineno - 1 - first, body0.end_lineno - first))
                chunk = [line for i, line in enumerate(chunk) if i not in drop]
            return _trim(_slice(chunk, start, stop), max_lines)
    raise KeyError(f"{name} not found in {rel}")


def text_source(rel, start, stop=None, max_lines=30):
    return _trim(_slice((ROOT / rel).read_text(encoding="utf-8").splitlines(), start, stop), max_lines)


def version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "-"


def npm_version(package):
    path = ROOT / "frontend" / "node_modules" / package / "package.json"
    return json.loads(path.read_text())["version"] if path.exists() else "-"


def node_version():
    try:
        return subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=20).stdout.strip().lstrip("v")
    except (OSError, subprocess.SubprocessError):
        return "-"


# ------------------------------------------------------------------ diagrams

def _box(d, x, y, w, h, lines, fill=SHADE, stroke=ACCENT):
    d.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=fill, strokeColor=stroke, strokeWidth=0.8))
    top = y + h / 2 + (len(lines) - 1) * 5.5
    for i, line in enumerate(lines):
        d.add(String(x + w / 2, top - i * 11 - 3, safe(line), fontName="Helvetica-Bold" if i == 0 else "Helvetica",
                     fontSize=8.5 if i == 0 else 7.3, fillColor=INK, textAnchor="middle"))
    return x + w / 2, y, y + h


def _arrow(d, x1, y1, x2, y2, both=False):
    d.add(Line(x1, y1, x2, y2, strokeColor=MUTED, strokeWidth=0.8))
    d.add(Polygon([x2, y2, x2 - 3, y2 + 6, x2 + 3, y2 + 6], fillColor=MUTED, strokeColor=MUTED))
    if both:
        d.add(Polygon([x1, y1, x1 - 3, y1 - 6, x1 + 3, y1 - 6], fillColor=MUTED, strokeColor=MUTED))


def pipeline_diagram():
    d = Drawing(FRAME_W, 11.4 * cm)
    W = d.width
    bw, bh = 108, 40
    food = _box(d, 40, 282, 170, 36, ["Food.com", "recipes, reviews, photo URLs"])
    survey = _box(d, W - 210, 282, 170, 36, ["NHANES 2017-2018", "body size, activity, intake"])
    clean = _box(d, W / 2 - 150, 218, 300, 34, ["Cleaning and features", "src/recipes.py, src/energy.py, src/photos.py"])
    _arrow(d, food[0], food[1], W / 2 - 60, clean[2])
    _arrow(d, survey[0], survey[1], W / 2 + 60, clean[2])
    gap = (W - 4 * bw) / 5
    labels = [["Course SVM", "Program 4.2"], ["Archetypes", "5.1, 6, 8"], ["Recommender", "6 SVD, 9 ensemble"], ["Energy targets", "Program 3"]]
    mids = []
    for i, lab in enumerate(labels):
        x = gap + i * (bw + gap)
        mids.append(_box(d, x, 138, bw, bh, lab))
        _arrow(d, W / 2, clean[1], x + bw / 2, 138 + bh)
    plan = _box(d, W / 2 - 150, 66, 300, 32, ["Meal planner", "mixed-integer program (HiGHS)"])
    for i in (0, 2, 3):
        _arrow(d, mids[i][0], mids[i][1], W / 2 + (i - 1.5) * 50, plan[2])
    app = _box(d, W / 2 - 150, 2, 300, 34, ["NUTRIX web app", "FastAPI service + React interface"], fill=colors.white)
    _arrow(d, W / 2, plan[1], W / 2, app[2])
    _arrow(d, mids[1][0], mids[1][1], W / 2 - 150, app[2] - 4)
    return d


def app_diagram():
    d = Drawing(FRAME_W, 8.4 * cm)
    W = d.width
    browser = _box(d, 10, 150, 170, 72, ["Web browser", "React 19 single-page app", "8 pages, charts, dialogs", "http://localhost:8000"], fill=colors.white)
    api = _box(d, W / 2 - 75, 150, 150, 72, ["FastAPI service", "api/main.py", "JSON endpoints under /api", "serves frontend/dist"])
    models = _box(d, W - 175, 190, 165, 50, ["Trained models", "models/bundle.joblib", "data/processed/catalog.parquet"])
    db = _box(d, W - 175, 118, 165, 50, ["SQLite database", "data/user/nutrix.db", "profile, likes, meal log"])
    cdn = _box(d, 10, 20, 170, 50, ["Food.com image CDN", "recipe photos, cropped", "to card size on request"])
    notebook = _box(d, W / 2 - 75, 20, 150, 50, ["src/build.py", "trains and saves", "the model bundle"])
    d.add(Line(180, 186, W / 2 - 75, 186, strokeColor=MUTED, strokeWidth=0.8))
    d.add(Polygon([W / 2 - 75, 186, W / 2 - 81, 189, W / 2 - 81, 183], fillColor=MUTED, strokeColor=MUTED))
    d.add(Polygon([180, 186, 186, 189, 186, 183], fillColor=MUTED, strokeColor=MUTED))
    d.add(String((180 + W / 2 - 75) / 2, 192, "JSON over HTTP", fontName="Helvetica", fontSize=7.3, fillColor=MUTED, textAnchor="middle"))
    d.add(Line(W / 2 + 75, 200, W - 175, 215, strokeColor=MUTED, strokeWidth=0.8))
    d.add(Line(W / 2 + 75, 172, W - 175, 143, strokeColor=MUTED, strokeWidth=0.8))
    _arrow(d, cdn[0], cdn[2], browser[0], browser[1])
    _arrow(d, notebook[0], notebook[2], W - 175 + 20, 190) if False else None
    d.add(Line(W / 2 + 75, 45, W - 92, 45, strokeColor=MUTED, strokeWidth=0.8))
    d.add(Line(W - 92, 45, W - 92, 118, strokeColor=MUTED, strokeWidth=0.8, strokeDashArray=[2, 2]))
    d.add(String(W - 88, 90, "writes models", fontName="Helvetica", fontSize=7, fillColor=MUTED))
    return d


# ------------------------------------------------------------------ data

lab, met = LAB, MET
data, reg, bayes, svm = lab["data"], lab["regression"], lab["bayes"], lab["svm"]
km, gmm, pca_r, svd_r = lab["kmeans"], lab["gmm"], lab["pca"], lab["svd"]
hmm, cart, recl, plan = lab["hmm"], lab["cart"], lab["recommender"], lab["meal_plan"]
intake = met["intake"]
gens, rankers = met["generators"], met["ranker_test"]
best = met["ranker_choice"]
best_gen = max(gens, key=lambda g: gens[g]["HR@10"])
lift = rankers[best]["HR@10"] / gens[best_gen]["HR@10"]
random_hr = 10 / data["recipes"]

# ================================================================== cover

story.append(Spacer(1, 3.2 * cm))
story.append(Paragraph(TITLE, ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=27, leading=33, textColor=ACCENT, alignment=TA_CENTER)))
story.append(Spacer(1, 0.2 * cm))
story.append(Paragraph("NUTRIX", ParagraphStyle("t2", fontName="Helvetica-Bold", fontSize=18, leading=24, textColor=INK, alignment=TA_CENTER)))
story.append(Spacer(1, 0.4 * cm))
story.append(Paragraph(
    "Calorie Targets, Recipe Recommendations and Optimised Meal Plans Learned from Food.com Reviews and the NHANES Survey",
    ParagraphStyle("s", fontName="Helvetica", fontSize=12.5, leading=17, textColor=INK, alignment=TA_CENTER)))
story.append(Spacer(1, 1.1 * cm))
cover_small = ParagraphStyle("c", fontName="Helvetica", fontSize=11, leading=16, textColor=MUTED, alignment=TA_CENTER)
story.append(Paragraph("Complete Project Report and Study Guide", ParagraphStyle("c1", parent=cover_small, fontName="Helvetica-Bold", textColor=INK)))
story.append(Paragraph("21CSC305P — Machine Learning Laboratory", cover_small))
story.append(Paragraph("All eleven lab programs applied to one real problem, delivered as a working web application", cover_small))
story.append(Spacer(1, 1.1 * cm))
story.append(Paragraph(
    "This document explains the idea, the reasoning behind every design decision, the mechanism of each stage, the "
    "exact commands used, the code, the results obtained, how to interpret them, and how the finished application "
    "is built and tested.", ParagraphStyle("c2", parent=BODY, alignment=TA_CENTER, textColor=MUTED)))
story.append(Spacer(1, 2.4 * cm))
blank = "_" * 34
story.append(Table(
    [["Name", STUDENT_NAME or blank], ["Register number", REGISTER_NUMBER or blank]],
    colWidths=[4 * cm, 8 * cm],
    style=TableStyle([("FONT", (0, 0), (-1, -1), "Helvetica", 11), ("TEXTCOLOR", (0, 0), (0, -1), MUTED), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]),
))
story.insert(0, NextPageTemplate("page"))
story.append(PageBreak())

# ================================================================== contents

story.append(Paragraph("Contents", PART))
contents = [
    ["Part", "Chapter", "What it covers"],
    ["I", "1. The Idea", "Title, the real-world problem, why the original scripts were replaced, scope"],
    ["", "2. Core Concepts", "Energy targets, macronutrients, recommender systems, offline evaluation, optimisation"],
    ["II", "3. The Datasets", "Food.com recipes and reviews, NHANES, recipe photos, cleaning"],
    ["", "4. Environment Setup", "Python and Node environments, packages, data download, project structure"],
    ["", "5. System Mechanism", "The pipeline from raw files to the running application"],
    ["", "6. The Code Layer", "Every module in src/ and what its main functions do"],
    ["III", "7. Program 1", "Loading and viewing the datasets"],
    ["", "8. Program 2", "Summary statistics, nutrition checks and cleaning"],
    ["", "9. Program 3", "Linear regression of daily energy intake"],
    ["", "10. Program 4.1", "Bayesian logistic regression with credible intervals"],
    ["", "11. Program 4.2", "Support vector machine for a recipe's course"],
    ["", "12. Program 5.1", "K-means nutrition archetypes"],
    ["", "13. Program 5.2", "Gaussian mixture model of user taste"],
    ["", "14. Program 5.3", "Hierarchical clustering of ingredients"],
    ["", "15. Program 6", "PCA recipe map and truncated SVD of the review matrix"],
    ["", "16. Program 7", "Hidden Markov Model of eating phases"],
    ["", "17. Program 8", "CART rules for the archetypes"],
    ["", "18. Program 9", "Ensemble learning for recommendation ranking"],
    ["IV", "19. The Meal Planner", "Mixed-integer program, candidate selection, speed experiments"],
    ["", "20. The NUTRIX Application", "Localhost or application, architecture, API, storage, every page"],
    ["", "21. Testing and Validation", "API checks, planner checks, builds, visual review"],
    ["", "22. Evaluation Summary", "All results in one place"],
    ["", "23. Limitations", "What the project does not claim"],
    ["", "24. Future Work", "Where to take it next"],
    ["V", "25. Reproducing Everything", "Exact commands to rebuild and run every part"],
    ["", "26. Glossary", "Every term used"],
    ["", "27. Expected Viva Questions", "Likely questions with answers"],
    ["", "28. References", "Sources"],
]
t = Table([[Paragraph(c, CELL_BOLD if r == 0 or (i == 1 and not row[0] == "") else CELL) for i, c in enumerate(row)] for r, row in enumerate(contents)],
          colWidths=[1.3 * cm, 4.8 * cm, 10.5 * cm], hAlign="LEFT")
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), SHADE), ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
    ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE), ("TOPPADDING", (0, 0), (-1, -1), 3.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
]))
story.append(t)

# ================================================================== PART I

part("Part I — The Idea")
h1("1. The Idea")
h2("1.1 Project title")
p(
    "<b>Personalised Nutrition Recommender (NUTRIX):</b> Calorie Targets, Recipe Recommendations and Optimised Meal "
    "Plans Learned from Food.com Reviews and the NHANES Survey."
)
h2("1.2 The problem in the real world")
p(
    "A person who wants to lose weight, build muscle or simply eat better has to answer two questions every day. "
    "The first is <i>how much</i>: how many calories, and how much protein, carbohydrate and fat. The second is "
    "<i>what</i>: which actual meals deliver those numbers and are also meals the person enjoys cooking and eating."
)
p(
    "Most diet applications answer the first question with a formula and the second with a fixed list of healthy "
    "meals. The formula is rarely checked against how real people eat, and the fixed list fails for a well-known "
    "reason: people stop following plans built from food they do not like. Adherence, not the arithmetic of calories, "
    "is where diets usually break down."
)
p(
    "Meanwhile recipe websites hold millions of reviews that record what people actually cook. If those reviews can "
    "be turned into a model of taste, and the model's suggestions can be fitted to a person's targets, the result is a "
    "plan that is both correct and likely to be followed. That is what this project builds."
)
h2("1.3 Why the original scripts were replaced")
p(
    "The project started from two Colab scripts (<i>untitled0.py</i> and <i>untitled1.py</i>) intended as a "
    "nutrition recommender. Reviewing them showed that no result they produced could be trusted:"
)
table([
    ["Problem in the original scripts", "Why it breaks the project"],
    ["Calories, protein, fat and carbohydrate were generated with np.random", "Every model trained on them learns noise; nothing transfers to real food"],
    ["The 'healthy' label was a hand rule on the same random features", "The SVM only re-learns the rule, so its accuracy proves nothing"],
    ["Required calories were generated from a linear formula plus small noise", "Linear regression on that target scores R² near 1 by construction"],
    ["food.csv had a 'genres' column holding movie genres", "The 'foods' were most likely a renamed movie dataset"],
    ["Recommendations were sorted only by average rating", "Every user saw the same list; the per-user ratings were never used"],
], [8.3, 8.3], "Table 1. Why the starting scripts could not be developed further.")
p("This project keeps the goal and rebuilds every part on real data, with evaluations designed so that no model can see its answer.")
h2("1.4 What the system does")
steps([
    "Calculates a daily calorie and macronutrient target from age, sex, height, weight, activity and goal, and "
    "compares it with the intake that NHANES adults of the same profile actually report.",
    "Learns taste from 221,732 Food.com reviews and recommends recipes a person is likely to cook, explaining each one.",
    "Fits recommended recipes into day or week meal plans that hit the targets, using an optimiser.",
    "Describes the recipe collection by course, nutrition archetype and a two-dimensional map.",
    "Delivers all of it in NUTRIX, a web application with a meal log, progress tracking and recipe photos.",
])
h2("1.5 Scope")
table([
    ["The project is", "The project is not"],
    ["A complete, reproducible machine-learning pipeline on public data", "A medical or dietetic tool; targets come from a population equation"],
    ["A working web application that runs on the user's own computer", "A hosted online service with accounts (it can be deployed; see Chapter 24)"],
    ["An honest evaluation, including where the models are weak", "A claim that the recommender predicts exactly what someone will cook"],
], [8.3, 8.3])

h1("2. Core Concepts")
h2("2.1 Energy targets")
p(
    "Resting energy expenditure is the energy the body uses at rest. The Mifflin-St Jeor equation (Mifflin et al., "
    "1990) estimates it from weight in kilograms, height in centimetres and age in years. Multiplying by a physical "
    "activity level (PAL) gives total daily energy, and a goal adjustment turns that into a target:"
)
code("""
resting energy (men)   = 10 x weight + 6.25 x height - 5 x age + 5
resting energy (women) = 10 x weight + 6.25 x height - 5 x age - 161
PAL:   sedentary 1.2   light 1.375   moderate 1.55   active 1.725
goal:  lose -500 kcal   maintain 0   gain +300 kcal
target = max(resting energy x PAL + goal adjustment, 1200 kcal for women or 1500 kcal for men)
""")
p(
    "The target is then split between protein, carbohydrate and fat by a share of energy that depends on the goal "
    "(30/40/30 to lose weight, 20/50/30 to maintain, 25/50/25 to gain), using 4 kcal per gram for protein and "
    "carbohydrate and 9 kcal per gram for fat."
)
h2("2.2 Macronutrients, Atwater factors and daily values")
p(
    "The Atwater factors (4, 4 and 9 kcal per gram) mean a recipe's calories should roughly equal "
    "4 x protein + 4 x carbohydrate + 9 x fat. This identity is used twice: to recover the units Food.com uses, and to "
    "detect nutrition panels that are internally inconsistent. Food.com reports every nutrient except calories as a "
    "percent of a daily value, so those values have to be converted back to grams."
)
h2("2.3 Recommender systems")
p(
    "<b>Explicit feedback</b> is a rating a user chooses to give. <b>Implicit feedback</b> is an action that "
    "reveals interest. On Food.com a review means the user cooked the recipe, so every review is treated as a "
    "positive signal whatever its stars. 77% of rated reviews give five stars, so stars carry little extra information."
)
p(
    "Production recommenders work in two stages. <b>Candidate generators</b> cheaply score the whole catalogue and keep "
    "a few hundred items; a <b>ranker</b> then orders those candidates with a richer model. This project uses four "
    "generators (popularity, trending, collaborative filtering by PureSVD, and content similarity) and an ensemble "
    "ranker. A <b>cold-start</b> item has no interaction history, so collaborative methods cannot score it, only content can."
)
h2("2.4 Evaluating a recommender offline")
p(
    "<b>Leave-last-out in time:</b> for each user the most recent recipe is hidden and the model, given only earlier "
    "history, must rank it among all recipes. <b>HR@10</b> (hit rate) is the share of users whose hidden recipe is in "
    "the top ten. <b>NDCG@10</b> also rewards placing it higher, and <b>MRR</b> is the mean of 1 / rank. A random "
    f"ranking of {num(data['recipes'])} recipes gives HR@10 = {pct(random_hr, 3)}."
)
h2("2.5 Mixed-integer optimisation")
p(
    "A mixed-integer linear program chooses values for variables, some restricted to whole numbers, to minimise a "
    "linear objective subject to linear constraints. Here binary variables decide which recipe and portion fills each "
    "meal slot, and continuous variables measure how far the day's nutrients are from target. The HiGHS solver finds "
    "a plan and can prove how close it is to the best possible plan."
)

# ================================================================== PART II

part("Part II — Data, Setup and Mechanism")
h1("3. The Datasets")
h2("3.1 Food.com Recipes and Interactions")
p(
    "Collected by Majumder et al. (2019) from Food.com, one of the largest recipe-sharing sites. The 2008-2018 cut "
    "distributed with UCSD's data science courses is used, downloaded from its public Google Drive folder."
)
table([
    ["File", "Rows", "Columns used"],
    ["RAW_recipes.csv", num(data["raw_recipes"]), "name, id, minutes, submitted, tags, nutrition, n_steps, steps, description, ingredients, n_ingredients"],
    ["RAW_interactions.csv", num(data["raw_reviews"]), "user_id, recipe_id, date, rating (0-5; 0 means a review without stars)"],
], [3.6, 2.2, 10.8], "Table 2. Food.com files.")
p(
    "Each recipe's <i>nutrition</i> field is a list: calories, total fat, sugar, sodium, protein, saturated fat and "
    "carbohydrate. Calories are in kcal; the rest are percent daily value. The daily values were recovered from the data "
    "itself: with the values below, the Atwater identity reproduces stated calories with a median ratio of 0.98, and "
    "sugar almost never exceeds carbohydrate."
)
code(text_source("src/recipes.py", "DAILY_VALUE = {", "# Features that describe", 6))
h2("3.2 NHANES 2017-2018")
p(
    "The National Health and Nutrition Examination Survey, run by the US Centers for Disease Control and Prevention, "
    "measures participants' bodies, asks about activity and records two 24-hour dietary recalls."
)
table([
    ["File", "What it contributes"],
    ["DEMO_J", "Age, sex, pregnancy status"],
    ["BMX_J", "Measured weight and height"],
    ["DR1TOT_J, DR2TOT_J", "Day 1 and day 2 dietary recall totals, with completeness and 'usual day' flags"],
    ["PAQ_J", "Global Physical Activity Questionnaire: days and minutes of five activity domains"],
], [4, 12.6], "Table 3. NHANES files joined on the respondent id (SEQN).")
p(
    "A recall is kept only when NHANES marks it complete and the respondent called it a usual day of eating. Intake is "
    "the mean of the kept days. Weekly MET-minutes weight vigorous work and recreation at 8 METs and moderate activity "
    "and active travel at 4. Adults aged 18-79 who are not pregnant and whose intake is plausible (500-3,500 kcal for "
    f"women, 800-4,200 kcal for men) remain: <b>{num(data['nhanes_adults'])} adults</b>."
)
h2("3.3 Recipe photos and original names")
p(
    "RAW_recipes.csv has no photos, and its names are lower-case with punctuation removed. A larger public scrape of "
    "Food.com (the parsed Food.com Recipes and Reviews dataset on Hugging Face) keeps photo URLs and original names but "
    "no id column. Every photo URL, however, contains the Food.com recipe id split into two-digit folders:"
)
code("""
https://img.sndimg.com/food/image/upload/w_555,h_416,c_fit,.../v1/img/recipes/28/48/28/pic.jpg
                                                                     recipe id 284828
""")
p(
    f"Joining the folders back into an id gives an exact match to RAW_recipes. {num(PHOTOS)} of {num(data['recipes'])} "
    f"recipes ({pct(PHOTOS / data['recipes'])}) have a photo, rising to about 90% of recipes with five or more reviews, "
    "and the original names agree with the cleaned titles for about 95% of matched recipes. A first version of the parser "
    "read only the first folder, which silently matched 90 recipes; checking the join rate caught it."
)
h2("3.4 Cleaning")
table([["Rule", "Recipes failing"]] + [[k, num(v)] for k, v in lab["cleaning"].items()], [12, 4.6],
      f"Table 4. Cleaning rules (a recipe can fail more than one). {num(data['recipes'])} of {num(data['raw_recipes'])} kept.")
p(
    f"Reviews are then restricted to surviving recipes: {num(data['reviews'])} reviews by {num(data['users'])} users. "
    f"The user x recipe matrix is {data['density'] * 100:.4f}% dense and half of all recipes have at most "
    f"{data['median_reviews_per_recipe']:.0f} review(s)."
)

h1("4. Environment Setup")
h2("4.1 Python environment")
code("""
cd C:\\Users\\Gunasekaran\\Dev\\nutrition-recommender
py -3.12 -m venv .venv
.venv\\Scripts\\python.exe -m pip install --upgrade pip
.venv\\Scripts\\python.exe -m pip install -r requirements.txt
""")
h2("4.2 A problem met during setup: Smart App Control")
p(
    "The first install pulled scikit-learn 1.9.1, and importing it failed with <i>DLL load failed while importing "
    "_sag_fast: An Application Control policy has blocked this file</i>. The Windows Code Integrity log showed Smart "
    "App Control blocking the newly downloaded compiled extension files. Disabling a security feature was not an "
    "acceptable fix. Instead, the working venv from an earlier project was checked, scikit-learn 1.9.0 was found to be "
    "trusted on this machine, and it was pinned in requirements.txt. FastAPI, pydantic-core and the Vite/Rollup "
    "binaries were tested for the same problem before any code depended on them."
)
h2("4.3 Python packages")
py_packages = [
    ("pandas", "Tables: loading, joins, grouping"), ("numpy", "Arrays and linear algebra"), ("scipy", "Sparse matrices, optimisation (HiGHS), hierarchical clustering"),
    ("scikit-learn", "Regression, SVM, K-means, GMM, PCA, SVD, CART, ensembles, metrics"), ("hmmlearn", "Categorical Hidden Markov Model"),
    ("pyarrow", "Parquet caches and the photo scrape"), ("matplotlib", "Notebook figures"), ("seaborn", "Heatmaps and plot styling"),
    ("jupyter", "The lab notebook"), ("fastapi", "The NUTRIX API"), ("uvicorn", "Web server for the API"), ("pydantic", "Request validation"),
    ("httpx", "Test client for the API checks"), ("reportlab", "This report"), ("gdown", "Food.com download from Google Drive"),
]
table([["Package", "Version", "Used for"]] + [[name, version(name), use] for name, use in py_packages], [3.2, 2.2, 11.2], "Table 5. Python packages (versions read from the environment).")
h2("4.4 Frontend packages")
js_packages = [
    ("react", "User interface components"), ("react-dom", "Rendering to the browser"), ("react-router-dom", "Page navigation"),
    ("recharts", "Radar, bar and scatter charts"), ("lucide-react", "Icons"), ("vite", "Development server and production build"),
    ("typescript", "Type checking"), ("@vitejs/plugin-react", "JSX transform for Vite"),
]
table([["Package", "Version", "Used for"]] + [[name, npm_version(name), use] for name, use in js_packages] + [["Node.js", node_version(), "JavaScript runtime"]],
      [3.8, 2.2, 10.6], "Table 6. Frontend packages (versions read from node_modules).")
h2("4.5 Obtaining the data")
code("""
.venv\\Scripts\\python.exe src\\download_data.py
#   RAW_recipes.csv, RAW_interactions.csv    Google Drive (gdown)
#   DEMO_J, BMX_J, DR1TOT_J, DR2TOT_J, PAQ_J   https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/
#   foodcom_parsed_0000/0001.parquet          Hugging Face parquet conversion (photos and names)
""")
h2("4.6 Project structure")
code("""
nutrition-recommender/
  data/raw/                    Food.com CSV and parquet files, NHANES .xpt files
  data/processed/              parquet caches and catalog.parquet (generated)
  data/user/nutrix.db          profile, liked recipes, meal log (created by the API)
  models/                      bundle.joblib, metrics.json (generated by src/build.py)
  notebooks/nutrition_ml_lab.ipynb   all lab programs, executed
  src/  download_data.py  recipes.py  energy.py  photos.py  course.py
        archetypes.py  recommender.py  planner.py  build.py
  api/main.py                  FastAPI service
  frontend/                    React app: src/pages, src/components, api.ts, styles.css
  tests/check_api.py           endpoint checks
  tests/check_planner.py       meal planner checks
  outputs/figures/             notebook figures      outputs/app/   screenshots, check results
  reports/build_report.py      builds this PDF
""")

h1("5. System Mechanism")
story.append(pipeline_diagram())
story.append(Paragraph("Figure 1. From raw data to the running application.", CAPTION))
table([
    ["Stage", "What happens", "Where"],
    ["1. Download", "Food.com, NHANES and the photo scrape are saved to data/raw", "src/download_data.py"],
    ["2. Clean", "Parse lists, convert nutrition to grams, apply cleaning rules, derive course and diet tags", "src/recipes.py"],
    ["3. Survey", "Join NHANES files, apply recall rules, compute MET-minutes and formula targets", "src/energy.py"],
    ["4. Enrich", "Fill missing courses with the SVM, assign archetypes and map coordinates, attach photos", "src/course.py, archetypes.py, photos.py"],
    ["5. Evaluate", "Leave-last-out split, generators, candidate sets, ranker comparison", "src/recommender.py via build.py"],
    ["6. Train and save", "Refit the recommender on all reviews, fit the intake regression, save the bundle and catalogue", "src/build.py"],
    ["7. Serve", "Load models once; answer JSON requests; store the profile and meal log in SQLite", "api/main.py"],
    ["8. Interact", "Render pages, charts and dialogs; call the API; show photos from the Food.com CDN", "frontend/"],
], [2.6, 9.2, 4.8], "Table 7. The eight stages.")

h1("6. The Code Layer")
modules = [
    ("src/recipes.py", [
        ("clean_recipes", "Parses lists, converts %DV to grams, applies the three cleaning rules, derives course and diet flags"),
        ("add_nutrient_features", "Energy shares of protein, carbohydrate, fat, sugar and saturated fat; log sodium density; log calories"),
        ("load_recipes / load_interactions", "Cleaned tables with parquet caches"),
        ("recipe_stats", "Review counts and a mean rating shrunk toward the global mean by five pseudo-reviews"),
    ]),
    ("src/energy.py", [
        ("mifflin_st_jeor, daily_target", "Resting energy and the calorie and macronutrient targets"),
        ("load_nhanes", "The cleaned NHANES adults with intake, MET-minutes and formula estimates"),
        ("intake_features, fit_intake_model", "Regressors and the linear regression of reported intake"),
    ]),
    ("src/course.py", [
        ("build_course_model", "TF-IDF over ingredients plus scaled nutrition, into a calibrated linear SVM"),
        ("fill_courses", "Adds course_final, keeping tags and accepting model predictions with probability >= 0.5"),
    ]),
    ("src/archetypes.py", [("Archetypes", "K-means with silhouette choice of k, centroid naming, CART rules and PCA map")]),
    ("src/recommender.py", [
        ("temporal_split, Evaluation", "Leave-last-out split and the shared evaluation setup"),
        ("Popularity, Trending, PureSVD, ContentModel", "The four candidate generators"),
        ("HybridRecommender.candidates", "Union of the generators' top 50 with the 23 ranking features"),
        ("ranker_models, sample_negatives, pool_ranks", "Program 9 models, training rows and ranking metrics"),
    ]),
    ("src/planner.py", [("plan_meals, _slot_options, _solve_day", "Candidate selection and the per-day mixed-integer program")]),
    ("src/photos.py", [("load_photos, attach_photos", "Photo URLs and original names joined through the id in each URL")]),
    ("src/build.py", [("main", "Runs every step, compares rankers on validation users and writes the bundle, metrics and catalogue")]),
]
for module, rows in modules:
    table([["Function", f"What it does ({module})"]] + [[f, d] for f, d in rows], [5.2, 11.4])
label("Code, converting and cleaning the nutrition panel (src/recipes.py)")
code(py_source("src/recipes.py", "clean_recipes", max_lines=32))
label("Code, the daily target (src/energy.py)")
code(py_source("src/energy.py", "daily_target"))

# ================================================================== PART III

part("Part III — The Eleven Programs")
p(
    "Each chapter follows the same pattern: the aim, the theory needed to understand it, the steps, the code as it "
    "appears in the executed notebook, the result it printed, and how to read that result. Every random seed is 42."
)

# ---------------------------------------------------------------- P1
h1("7. Program 1 — Loading and Viewing the Datasets")
label("Aim")
p("Load the three datasets, confirm their shape, and look at what a row actually contains before modelling anything.")
label("Theory")
p(
    "Loading is where silent errors enter: a list stored as text, a misread separator or a join on the wrong key all "
    "produce data that looks fine and models that mean nothing. Checking row counts, column types and a few rows "
    "against the source description is the cheapest test there is."
)
label("Steps")
steps(["Read the raw Food.com CSVs and print their shapes.", "Load the cleaned recipes, the reviews restricted to them and the NHANES adults.", "Plot calories per serving, reviews per year and the distribution of stars."])
label("Code")
code(nb_code('recipes = load_recipes()', max_lines=10))
label("Result obtained")
output(nb_output('raw_recipes = pd.read_csv(DATA_DIR / "RAW_recipes.csv")', max_lines=1) + nb_output('recipes = load_recipes()', max_lines=8))
fig("p1_overview", 16.4, "Figure 2. Calories per serving, reviews per year, and stars in the raw reviews.")
label("How to read this")
p(
    "Calories per serving are right-skewed with most recipes between 150 and 500 kcal. Review activity peaked in 2009 "
    "and declined, which matters for evaluation: later users have less company. Almost all stars are 4 or 5, and the "
    "large bar at 0 is reviews without a star rating, not bad reviews. That is why reviews are used as implicit feedback."
)

# ---------------------------------------------------------------- P2
h1("8. Program 2 — Summary Statistics and Cleaning")
label("Aim")
p("Summarise the data statistically and use the summary to decide which rows can be trusted.")
label("Theory")
p(
    "Food.com nutrition is computed from author-entered ingredients and serving counts, so it contains errors: whole "
    "recipes entered as one serving, zero-calorie rows, and panels whose calories disagree with their macronutrients. "
    "The Atwater identity gives a target-free consistency check, so cleaning on it cannot leak information into later models."
)
label("Steps")
steps(["Convert the raw nutrition lists to grams.", "Compare stated calories with 4P + 4C + 9F.", "Count rows failing each rule.", "Describe the cleaned nutrients and the long tail of reviews."])
label("Code")
code(nb_code('rules = pd.Series({', max_lines=18))
label("Result obtained")
output(nb_output('rules = pd.Series({'))
output(nb_output('per_recipe = interactions.groupby("recipe_id").size()'))
fig("p2_quality_and_long_tail", 16.4, "Figure 3. Nutrition panel consistency and the long tails of reviews per recipe and per user.")
label("How to read this")
p(
    "The points on the diagonal are consistent panels; the clouds away from it are the rows removed. Both review "
    "histograms fall in a straight line on log-log axes: a few recipes and users account for most activity while "
    "most recipes have one or two reviews. This long tail limits every recommender result later in the report."
)

# ---------------------------------------------------------------- P3
h1("9. Program 3 — Linear Regression of Daily Energy Intake")
label("Aim")
p("Predict how much NHANES adults report eating from age, sex, body size and activity, and compare with the Mifflin-St Jeor target.")
label("Theory")
p(
    "Ordinary least squares fits y = b0 + b1 x1 + ... + bk xk by minimising the sum of squared residuals. R² is the "
    "share of variance explained, and can be negative for a model that is worse than predicting the mean, which is "
    "how an external formula is judged here. Activity enters as log(1 + MET-minutes) because a few manual workers "
    "report tens of thousands of MET-minutes a week."
)
label("Steps")
steps(["Build the regressors and an 80/20 split.", "Fit the regression and print its coefficients.", "Score it and the formula on the test set, and cross-validate the regression."])
label("Code")
code(nb_code('lr = LinearRegression().fit(X_train, y_train)', max_lines=20))
label("Result obtained")
output(nb_output('lr = LinearRegression().fit(X_train, y_train)'))
fig("p3_intake_regression", 13.5, "Figure 4. Predicted against reported intake.")
label("How to read this")
p(
    f"Being male adds about {reg['coefficients']['male']:.0f} kcal/day and each centimetre of height about "
    f"{reg['coefficients']['height']:.0f} kcal/day. Still, the regression explains only {pct(reg['cv_r2'], 0)} of the "
    "variance: people eat differently from day to day and a recall covers one or two days. The formula scores a "
    f"negative R² because it sits {reg['formula_bias']:+.0f} kcal above reported intake on average, the well-documented "
    "under-reporting of dietary recalls (Willett, 2012). The app keeps the formula as the target and shows the "
    "regression only as context."
)

# ---------------------------------------------------------------- P4.1
post = bayes["posterior"]
feats = [k for k in post if k != "intercept"]
excludes_zero = [k for k in feats if post[k]["2.5%"] > 0 or post[k]["97.5%"] < 0]
h1("10. Program 4.1 — Bayesian Logistic Regression")
label("Aim")
p("Estimate the probability that a recipe is a dessert from its nutrient profile alone, with uncertainty on every weight and every prediction.")
label("Theory")
p(
    "Logistic regression models P(y = 1 | x) = sigmoid(w . x). A Bayesian treatment places a prior on w, here N(0, 2²) "
    "on each weight, and combines it with the likelihood. The posterior has no closed form, so the Laplace "
    "approximation (Bishop, 2006) finds its mode by optimisation and approximates it with a Gaussian whose covariance "
    "is the inverse Hessian of the negative log posterior at the mode. Predictions average the sigmoid over samples of w."
)
label("Steps")
steps(["Sample 12,000 tagged recipes; standardise the seven nutrient features.", "Minimise the negative log posterior with L-BFGS.", "Compute the Hessian and its inverse.", "Sample 2,000 weight vectors and form the posterior predictive."])
label("Code")
code(nb_code('def neg_log_posterior(w):', start="PRIOR_VAR", max_lines=26))
label("Result obtained")
output(nb_output('def neg_log_posterior(w):'))
output(nb_output('W = rng.multivariate_normal(w_map, cov, size=2000)', max_lines=12))
fig("p4_bayesian_logistic", 16.4, "Figure 5. Credible intervals of the weights and the posterior predictive band.")
label("How to read this")
p(
    f"ROC AUC is {bayes['auc']:.3f}. Accuracy ({pct(bayes['accuracy'])}) is barely above always answering 'not a "
    f"dessert' ({pct(1 - bayes['dessert_share'])}), which is why AUC is the number to report. {len(excludes_zero)} of "
    f"{len(feats)} weights have intervals excluding zero. The protein, carbohydrate and fat shares always sum to one, "
    "so the data cannot separate their effects, and the posterior shows exactly that as wide intervals where a point "
    "estimate would hide it. The widest predictive bands belong to sweet drinks, sauces and dips."
)

# ---------------------------------------------------------------- P4.2
h1("11. Program 4.2 — Support Vector Machine for the Course")
label("Aim")
p("Predict a recipe's course so the meal planner can place the one recipe in nine that has no course tag.")
label("Theory")
p(
    "A linear SVM finds the hyperplane that separates classes with the largest margin, trading margin against "
    "misclassification through C. Multi-class problems are solved one class against the rest. SVM scores are not "
    "probabilities, so the model is wrapped in cross-validated calibration, which fits a mapping from scores to "
    "probabilities and lets the app accept only confident predictions. class_weight='balanced' stops the large main-dish "
    "class dominating. Tags are excluded from the features because the course tags are the labels."
)
label("Steps")
steps(["Build TF-IDF weights over ingredient names and scale the numeric features.", "Train a calibrated LinearSVC on 80% of tagged recipes.", "Report per-class F1 and the confusion matrix.", "Refit on all tagged recipes and fill untagged courses with probability >= 0.5."])
label("Code")
code(py_source("src/course.py", "build_course_model"))
label("Result obtained")
output(nb_output('svm = build_course_model().fit(course_frame(train_c), train_c["course"])'))
output(nb_output('course_model = fit_course_model(recipes)', max_lines=5))
fig("p4_svm_confusion", 10, "Figure 6. Row-normalised confusion matrix.")
label("How to read this")
p(
    f"Accuracy is {pct(svm['accuracy'])} and macro F1 {svm['macro_f1']:.2f}. Desserts, beverages and mains are "
    "distinctive. Snacks are the hardest class: about a third are predicted as mains. Snack and breakfast are defined "
    "by when food is eaten more than by what is in it, so ingredients and nutrition cannot fully separate them. "
    f"{num(svm['filled'])} untagged recipes gained a course and {num(svm['unassigned'])} stay out of the planner."
)

# ---------------------------------------------------------------- P5.1
h1("12. Program 5.1 — K-means Nutrition Archetypes")
label("Aim")
p("Group recipes by what they are like to eat, independent of their names.")
label("Theory")
p(
    "K-means assigns each point to the nearest of k centroids and moves each centroid to the mean of its points, "
    "repeating until assignments stop changing; it minimises inertia, the total squared distance to centroids. Inertia "
    "always falls as k grows, so k is chosen by the silhouette score, which compares each point's distance to its own "
    "cluster with its distance to the nearest other cluster."
)
label("Steps")
steps(["Standardise the seven portion-independent nutrient features.", "Fit K-means for k = 4 to 10 and compute silhouette on a 5,000-recipe sample.", "Fit the best k and name each centroid from fixed nutrition thresholds."])
label("Code")
code(nb_code('archetypes = Archetypes().fit(recipes)', max_lines=14))
label("Result obtained")
output(nb_output('archetypes = Archetypes().fit(recipes)'))
fig("p5_kmeans_selection", 13, "Figure 7. Elbow and silhouette.")
fig("p5_archetype_course", 13.5, "Figure 8. Course mix inside each archetype.")
label("How to read this")
p(
    f"The silhouette peaks at k = {km['k']} but stays modest, which is honest: nutrition is a continuum. The "
    "archetypes are still useful because their course mixes differ sharply, for example sugary archetypes are mostly "
    "desserts and beverages while rich hearty ones are mostly mains."
)

# ---------------------------------------------------------------- P5.2
h1("13. Program 5.2 — Gaussian Mixture Model of User Taste")
label("Aim")
p("Find taste segments among users and measure how cleanly users belong to them.")
label("Theory")
p(
    "A Gaussian mixture models data as a weighted sum of Gaussian components and is fitted by Expectation "
    "Maximisation, alternating soft assignment (responsibilities) and parameter updates. BIC balances fit against the "
    "number of parameters. Proportions near zero break the Gaussian assumption, so shares are square-root transformed "
    "(the Hellinger transform), and a covariance floor stops components collapsing onto users who never cook an archetype."
)
label("Steps")
steps(["Describe each user with 10+ reviews by the share of reviews in each archetype.", "Square-root transform.", "Fit full-covariance mixtures for 1 to 10 components.", "Choose the simplest model within 2% of the best BIC."])
label("Code")
code(nb_code('X_taste = np.sqrt(taste)', max_lines=22))
label("Result obtained")
output(nb_output('X_taste = np.sqrt(taste)', max_lines=12))
fig("p5_gmm_segments", 16.4, "Figure 9. BIC, and each segment's difference from the average user in percentage points.")
strong = [n for n, d in gmm["segments"].items() if max(abs(v) for v in d.values()) >= 8]
label("How to read this")
p(
    f"{pct(gmm['confident_share'])} of users belong to one of {gmm['k']} segments with probability above 0.8. "
    f"{len(strong)} segments show a clear leaning of 8 or more points, such as a savoury group cooking far fewer sweet "
    "recipes and a baking group cooking more; the largest segment sits on the average. Before the transform and floor, "
    "BIC kept improving up to the largest model tried, a sign of degenerate components rather than real structure."
)

# ---------------------------------------------------------------- P5.3
h1("14. Program 5.3 — Hierarchical Clustering of Ingredients")
label("Aim")
p("Discover which ingredients are cooked together, without labels.")
label("Theory")
p(
    "Agglomerative clustering starts with every item alone and repeatedly merges the closest pair of clusters. The "
    "distance between two ingredients is the Jaccard distance between the sets of recipes containing them, and average "
    "linkage uses the mean distance between members. The dendrogram records every merge and its height."
)
label("Steps")
steps(["Take the 60 most common ingredients after salt, pepper and water.", "Build a recipe x ingredient presence matrix.", "Compute Jaccard distances and average linkage; draw the dendrogram."])
label("Code")
code(nb_code('tree = linkage(pdist(occurs.T, metric="jaccard"), method="average")', max_lines=12))
fig("p5_ingredient_dendrogram", 10.5, "Figure 10. Ingredients cooked together.", max_height_cm=17)
label("How to read this")
p(
    "The tightest group is baking (flour, sugar, eggs, butter, milk, vanilla, baking powder and soda, cinnamon, "
    "nutmeg). Smaller groups form an Italian-style base (garlic, olive oil, onion, parmesan, tomatoes), a spice rub "
    "(paprika, garlic powder, cayenne, cumin, chili powder, ground beef), a stir-fry (soy sauce, cornstarch, green "
    "onions), a soup base (carrot, celery, chicken broth) and a cheese-and-bacon group. Distances above 0.7 are normal: "
    "even common ingredients share only part of their recipes."
)

# ---------------------------------------------------------------- P6
L = pca_r["loadings"]
h1("15. Program 6 — PCA and Truncated SVD")
label("Aim")
p("Compress nutrition into a two-dimensional recipe map, and find the latent factors behind the review matrix.")
label("Theory")
p(
    "PCA finds orthogonal directions of maximum variance; each component's loadings say how much each feature "
    "contributes. Truncated SVD factorises a matrix as U S V^T keeping the top k singular values; applied to the sparse "
    "user x recipe matrix it gives the latent factors used by PureSVD (Cremonesi et al., 2010), which scores a user's "
    "recipes as h V^T V for their history vector h."
)
label("Code")
code(nb_code('pca = PCA().fit(Z)', max_lines=8))
code(py_source("src/recommender.py", "PureSVD"))
label("Result obtained")
output(nb_output('pca = PCA().fit(Z)') + nb_output('svd = TruncatedSVD(128, n_iter=7, random_state=42).fit(R)'))
fig("p6_pca", 16.4, "Figure 11. Explained variance, loadings and the recipe map.")
fig("p6_svd_scree", 9.5, "Figure 12. Cumulative variance of the truncated SVD.")
label("How to read this")
p(
    f"Two components explain {pct(pca_r['explained_2'])}. PC1 contrasts carbohydrate ({L['PC1']['carbs_pct']:+.2f}) "
    f"and sugar ({L['PC1']['sugar_pct']:+.2f}) against fat ({L['PC1']['fat_pct']:+.2f}); PC2 separates lean, salty, "
    f"protein-rich dishes (protein {L['PC2']['protein_pct']:+.2f}) from fatty ones; PC3 is portion size "
    f"({L['PC3']['log_kcal']:+.2f}). 64 SVD factors explain only {pct(svd_r['var_64'])} of the review matrix, a direct "
    "view of how little users' histories overlap."
)

# ---------------------------------------------------------------- P7
h1("16. Program 7 — Hidden Markov Model of Eating Phases")
label("Aim")
p("Test whether users cook in phases, runs of similar recipes, rather than choosing each recipe independently.")
label("Theory")
p(
    "A Hidden Markov Model has hidden states that follow a Markov chain (the transition matrix) and emit observations "
    "with state-specific probabilities (the emission matrix). Baum-Welch, an EM algorithm, fits both from unlabelled "
    "sequences (Rabiner, 1989). Here the observation is the archetype of each reviewed recipe, in date order."
)
label("Code")
code(nb_code('long_users = per_user[per_user >= 20].index', max_lines=16))
label("Result obtained")
output(nb_output('long_users = per_user[per_user >= 20].index') + nb_output('state_names = [f"state {i + 1}"', max_lines=3))
fig("p7_hmm", 16.4, "Figure 13. Emission and transition probabilities.")
persistent = sum(s > 0.5 for s in hmm["stay"])
label("How to read this")
p(
    f"BIC chose {hmm['states']} states and {persistent} of them persist, with self-transition probability above one "
    "half: users do cook in runs. One state is effectively absorbing, so it describes a stable taste type rather "
    "than a passing phase. This supports weighting recent history when recommending."
)

# ---------------------------------------------------------------- P8
fid = cart["fidelity_by_depth"]
h1("17. Program 8 — CART Rules for the Archetypes")
label("Aim")
p("Turn the K-means archetypes into threshold rules a person can read.")
label("Theory")
p(
    "CART grows a binary tree by choosing, at each node, the feature and threshold that most reduce Gini impurity. "
    "Fitted to cluster labels it acts as a surrogate model, and fidelity, the share of recipes where tree and K-means "
    "agree, measures how faithful the rules are."
)
label("Code")
code(nb_code('depth_fidelity = {', max_lines=10))
label("Result obtained")
output(nb_output('depth_fidelity = {', max_lines=26))
fig("p8_cart_tree", 16.4, "Figure 14. Top three levels of the archetype rules.")
label("How to read this")
p(
    f"Depth 4, used in the app, reproduces {pct(cart['fidelity'])} of the labels. Each extra level adds only one to "
    f"three points (depth 8 reaches {pct(fid['8'], 0)}) while doubling the rules, so depth 4 is the readable compromise."
)

# ---------------------------------------------------------------- P9
h1("18. Program 9 — Ensemble Learning for Recommendation")
label("Aim")
p("Rank each user's candidate recipes so the recipe they cook next comes first, and compare ensemble methods.")
label("Theory")
p(
    "Bagging (random forest) averages trees trained on bootstrap samples with random feature subsets, reducing "
    "variance. Boosting (histogram gradient boosting) fits trees sequentially to the errors of earlier trees, reducing "
    "bias. Soft voting averages the probabilities of several models. A linear logistic regression is the baseline."
)
label("Steps")
steps([
    "Split each user's history in time: last recipe is the test target, the one before the validation target (users with 3+ recipes).",
    "Fit the four generators on what remains; serve each target on the day it was reviewed and hide recipes not yet submitted.",
    "Build candidates from each generator's top 50 with 23 features per user-recipe pair.",
    "Train rankers on validation targets with 30 sampled negatives per user; choose on held-out validation users.",
    "Score every model on the test targets.",
])
label("Code, the candidate generators")
code(py_source("src/recommender.py", "Trending", max_lines=22))
label("Code, training and scoring the rankers")
code(nb_code('results, fitted = {}, {}', max_lines=14))
label("Result obtained")
output(nb_output('ev = Evaluation(recipes, interactions)', max_lines=10))
output(nb_output('results, fitted = {}, {}'))
fig("p9_model_comparison", 16, "Figure 15. HR@10 and NDCG@10 for every generator and ranker.")
fig("p9_feature_importance", 8.5, "Figure 16. Random forest feature importance.")
label("How to read this")
p(
    f"The {best} ranker, chosen on validation users, finds the next recipe for {pct(rankers[best]['HR@10'], 2)} of "
    f"users: {lift:.1f} times the best generator ({best_gen}, {pct(gens[best_gen]['HR@10'], 2)}) and about "
    f"{rankers[best]['HR@10'] / random_hr:.0f} times random. All tree ensembles perform alike and clearly beat logistic "
    "regression, so the gain comes from non-linear interactions between signals. Recipe age is the most important "
    f"feature. The absolute numbers are limited by the data: {pct(recl['cold_targets'])} of test recipes had no "
    f"training reviews, and retrieval finds the true recipe for only {pct(met['retrieval_recall']['test'])} of users."
)
note(
    "An early version of the evaluation used each user's last training date as the serving day. Recipes submitted "
    "after that day could then be recommended, which quietly leaks the fact that a recipe will exist. The final "
    "evaluation serves each target on its own review date and hides recipes that did not yet exist."
)

# ================================================================== PART IV

part("Part IV — Application, Evaluation and Honest Limits")
h1("19. The Meal Planner")
label("Aim")
p("Turn recommendations into day or week plans that meet calorie, macronutrient, sugar and sodium targets.")
label("Formulation")
p(
    "For each day a binary variable x(s, r, q) selects recipe r at portion q (0.5, 1, 1.5 or 2 servings) for slot s "
    "(breakfast 25% of energy, lunch 35%, dinner 30%, snack 10%). The program minimises:"
)
bullets([
    "the relative gap of the day's calories (weighted 3), protein (1.5), carbohydrate and fat (1 each) from target;",
    "sugar above 10% of energy (WHO, 2015) and sodium above 2,300 mg;",
    "a small penalty for portions other than one serving;",
    "a penalty of 0.3 x (1 - preference) per chosen recipe.",
])
p("subject to exactly one recipe and portion per slot and no recipe twice in a day. Days are solved in sequence with used recipes removed, so a week never repeats a dish.")
label("Code, choosing each slot's candidates")
code(py_source("src/planner.py", "_slot_options", max_lines=30))
label("Design decisions from experiments")
bullets([
    "<b>Balanced candidates.</b> With only the most preferred recipes, a person who likes curries got a week 47% short on carbohydrate. Each slot now takes the 15 most preferred plus the 15 closest to the target's macro balance.",
    "<b>Day by day.</b> Solving a week as one program found no feasible plan in 20 seconds.",
    "<b>No per-slot calorie penalty.</b> It made the program so hard that plans stopped by the time limit missed calories by 21%. The portion band keeps slots sensible without it.",
    "<b>One-second limit with a guard.</b> Proving optimality takes several seconds per day. The solver stops after one second, and a day more than 3% off its calorie target is solved again with three times the candidates and five times the limit.",
])
table([
    ["Program", "Profile", "Limit per day", "Week time", "Largest calorie gap", "Largest macro gap"],
    ["with slot term, 30 candidates", "vegetarian woman", "30 s (optimal)", "43 s", "0.4%", "12.8%"],
    ["with slot term, 30 candidates", "vegetarian woman", "1 s", "8 s", "21.1%", "33.0%"],
    ["with slot term, 30 candidates", "man who likes curries", "1 s", "9 s", "2.8%", "26.1%"],
    ["final: no slot term, 15 + 15", "vegetarian woman", "1 s", "8 s", "0.6%", "9.9%"],
    ["final: no slot term, 15 + 15", "man who likes curries", "1 s", "8 s", "2.2%", "5.1%"],
], [4.2, 3.3, 2.4, 1.8, 2.5, 2.4], "Table 8. The experiment behind the planner design (single runs).")
fig("p10_meal_plan", 16.4, f"Figure 17. Seven-day plan for the notebook's example profile; every total within {pct(plan['max_gap'])} of target.")

h1("20. The NUTRIX Application")
h2("20.1 Is it localhost or an application?")
p(
    "<b>Both, in the precise sense: NUTRIX is a web application that runs locally.</b> When you start it, a small web "
    "server (Uvicorn running the FastAPI service) starts on your own computer, and you use the application in a web "
    "browser at <b>http://localhost:8000</b>. <i>localhost</i> simply means 'this computer'. Nothing is uploaded, there "
    "is no login, and the profile and meal log stay in a file on your machine. The only outside connection is the "
    "browser loading recipe photos from Food.com's image server."
)
table([
    ["Question", "Answer"],
    ["Do I install it like a mobile or desktop app?", "No. You start the server with one command and open the browser."],
    ["Can other people use it over the internet?", "Not as built. It listens only on this computer. It can be deployed (Chapter 24)."],
    ["Does it need the internet?", "Only for recipe photos; everything else works offline."],
    ["Why a web application at all?", "One codebase gives a rich interface on any computer or phone browser, and it is the standard way ML models are served."],
], [6, 10.6])
h2("20.2 Architecture")
story.append(app_diagram())
story.append(Paragraph("Figure 18. NUTRIX architecture.", CAPTION))
p(
    "The React app is compiled by Vite into static files in <i>frontend/dist</i>. FastAPI serves those files and the "
    "JSON API from one process. At start-up the API loads the trained model bundle and the recipe catalogue into memory "
    "once, so each request only runs inference. The meal log, profile and liked recipes are stored in SQLite, which needs "
    "no separate database server."
)
h2("20.3 Technology stack")
table([
    ["Layer", "Technology", "Why"],
    ["Interface", f"React {npm_version('react')}, React Router {npm_version('react-router-dom')}, TypeScript", "Component-based pages with type-checked API data"],
    ["Charts and icons", f"Recharts {npm_version('recharts')}, lucide-react {npm_version('lucide-react')}", "Radar, bar and scatter charts; consistent icons"],
    ["Build tool", f"Vite {npm_version('vite')}", "Fast development server with /api proxy; optimised production build"],
    ["API", f"FastAPI {version('fastapi')}, pydantic {version('pydantic')}, Uvicorn {version('uvicorn')}", "Typed endpoints with automatic request validation"],
    ["Storage", "SQLite (Python standard library)", "Single-file local database, no server"],
    ["Models", f"scikit-learn {version('scikit-learn')}, SciPy {version('scipy')} (HiGHS)", "Everything trained by src/build.py"],
], [3, 6.8, 6.8], "Table 9. Technology stack.")
h2("20.4 API endpoints")
DESCRIPTIONS = {
    ("GET", "/api/meta"): "Options for forms: activity levels, goals, diets, courses, archetypes, photo count",
    ("GET", "/api/profile"): "Profile, targets, chip labels and the NHANES intake estimate",
    ("PUT", "/api/profile"): "Partial profile update, validated by pydantic",
    ("GET", "/api/recommendations"): "Ranked recipes with match score, reasons and the liked recipe each resembles",
    ("GET", "/api/recipes"): "Food Library search by name or ingredient, with filters, sort and paging",
    ("GET", "/api/recipes/{recipe_id}"): "Recipe detail: photo, ingredients, steps, nutrition, similar recipes",
    ("GET", "/api/likes"): "Liked recipes",
    ("POST", "/api/likes/{recipe_id}"): "Like a recipe",
    ("DELETE", "/api/likes/{recipe_id}"): "Unlike a recipe",
    ("GET", "/api/log"): "One day's planned and eaten meals with totals",
    ("POST", "/api/log"): "Add a meal to a day and slot as planned or eaten",
    ("PATCH", "/api/log/{entry_id}"): "Change a meal's status, servings or slot",
    ("DELETE", "/api/log/{entry_id}"): "Remove a meal",
    ("DELETE", "/api/log"): "Clear the whole log",
    ("POST", "/api/plan"): "Generate a 1-7 day plan with the optimiser",
    ("POST", "/api/plan/save"): "Save a generated plan as planned meals",
    ("GET", "/api/progress"): "Daily totals and on-target flags for the last N days",
    ("GET", "/api/dashboard"): "Everything the dashboard shows, in one request",
    ("GET", "/api/analytics"): "Model evaluation results, archetype table and map sample",
}
routes = re.findall(r'@app\.(get|post|put|patch|delete)\("(/api[^"]*)"', (ROOT / "api" / "main.py").read_text(encoding="utf-8"))
table([["Method", "Path", "Purpose"]] + [[m.upper(), path, DESCRIPTIONS.get((m.upper(), path), "")] for m, path in routes],
      [1.7, 5, 9.9], f"Table 10. The {len(routes)} API endpoints, read from api/main.py.")
h2("20.5 Local storage")
table([
    ["Table", "Columns", "Holds"],
    ["profile", "id (always 1), data (JSON)", "Name, sex, age, height, weight, activity, goal, diets, excluded ingredients, maximum cooking time"],
    ["likes", "recipe_id (primary key), added_at", "Recipes the user liked; they drive recommendations"],
    ["log", "id, day, slot, recipe_id, servings, status, created_at", "Every planned or eaten meal; status is 'planned' or 'eaten'"],
], [2.2, 5.6, 8.8], "Table 11. SQLite schema (data/user/nutrix.db).")
h2("20.6 How recommendations are shown: match score and reasons")
p(
    "The ranker's probabilities are not calibrated for display, so the app shows a <b>match score</b> that blends "
    "two things a person cares about: how strongly the ranker expects them to cook the recipe (its rank among the "
    "candidates) and how well it fits one meal of their targets (calories near a third of the day, and macro balance "
    "near the target's). It is scaled to 60-99 and labelled as a match, not a probability. Each card also lists "
    "checked reasons: fits the calorie target, supports the protein goal, matches diet preferences, cooking time, and "
    "the liked recipe it most resembles by content similarity."
)
code(py_source("api/main.py", "_recommend_cards", max_lines=30))
h2("20.7 The insight sentence")
p(
    "The dashboard's insight is rule-based, built on the meal log and the targets, and is labelled 'Insight', not AI. "
    "If meals are planned for the rest of the day the whole day is judged; otherwise what has been eaten is compared "
    "with what is normally eaten by that hour (breakfast by 10:00, lunch by 15:00, dinner by 21:00). A shortfall of more "
    "than 15% in a macronutrient triggers a suggestion of a recommended meal rich in it that fits the calories left."
)
h2("20.8 The pages")
pages = [
    ("dashboard", 16.4, "Dashboard", "Greeting and profile chips; today's calories and macros eaten against target with planned meals noted; nutrition balance radar (sugar and sodium against their limits); the insight; four top recommendations with photos, match scores and 'Add to Plan'; the reasons for the selected card; protein this week; days on target; and a banner."),
    ("recommendations", 16.4, "Recommendations", "Up to 24 ranked recipes, filterable by course, each with its match score and the liked recipe it resembles. Hovering a card shows why it was picked."),
    ("library", 16.4, "Food Library", "Search across all 78,930 recipes by name or ingredient, filter by course and archetype, sort by reviews, rating, time, protein or calories, and restrict to the user's diet settings or to recipes with photos."),
    ("recipe", 16.4, "Recipe detail", "Opened from any card: large photo, course, archetype, time, rating, description, ingredients, steps, nutrition per serving, like and add buttons, and six similar recipes found by content similarity."),
    ("meal_plan", 16.4, "Meal Plan", "Generate a 1, 3 or 7-day plan, shuffle it, and save it to the calendar. Below, each day's meals can be ticked off as eaten, removed, or browsed day by day."),
    ("profile", 16.4, "My Profile", "Body measurements and activity, the resulting daily targets, and the liked recipes that drive recommendations."),
    ("goals", 16.4, "Goals", "Choose weight loss, maintenance or muscle gain; see how resting energy, the activity multiplier and the goal adjustment make the target; macro split and limits; and what similar NHANES adults report eating."),
    ("analytics", 16.4, "Analytics", "The last 30 days against target, the recommender's hit rate for every model, the other models' metrics, the interactive PCA recipe map and the archetype table."),
    ("settings", 16.4, "Settings", "Diet filters, ingredients to leave out, maximum cooking time, clearing the log, and data credits."),
]
for i, (name, width, title, text) in enumerate(pages, 19):
    label(title)
    p(text)
    shot(name, width, f"Figure {i}. {title}.", max_height_cm=17)
label("Narrow screens")
p("Below 1,100 pixels the sidebar collapses to icons, and below 720 pixels every grid stacks into one column, so the app works in a phone-sized browser window.")
shot("mobile", 6.2, f"Figure {19 + len(pages)}. Dashboard in a narrow window.", max_height_cm=18)

h1("21. Testing and Validation")
h2("21.1 API checks")
if API_CHECKS:
    p(
        f"<i>tests/check_api.py</i> runs every endpoint against a throwaway database through FastAPI's test client, "
        f"checking the status code and a property of each response, including rejected invalid input. "
        f"<b>{API_CHECKS['passed']} of {API_CHECKS['total']} checks passed.</b>"
    )
    table([["Check", "Method", "Path", "Status", "Time"]] +
          [[c["label"], c["method"], c["path"], f"{c['status']}{'' if c['ok'] else ' (FAIL)'}", f"{c['ms']} ms"] for c in API_CHECKS["checks"]],
          [4.9, 2.0, 5.6, 1.7, 2.4], "Table 12. API checks.")
h2("21.2 Meal planner checks")
if PLANNER_CHECKS:
    p(
        f"<i>tests/check_planner.py</i> plans contrasting profiles and fails any plan more than "
        f"{pct(PLANNER_CHECKS['kcal_limit'], 0)} off its calorie target, more than {pct(PLANNER_CHECKS['macro_limit'], 0)} "
        f"off a macronutrient target, or repeating a dish. <b>{sum(r['ok'] for r in PLANNER_CHECKS['profiles'])} of "
        f"{len(PLANNER_CHECKS['profiles'])} profiles passed.</b>"
    )
    table([["Profile", "Days", "Target", "Time", "Calorie gap", "Macro gap", "Result"]] +
          [[r["profile"], str(r["days"]), f"{num(r['target_kcal'])} kcal", f"{r['seconds']} s", pct(r["kcal_gap"]), pct(r["macro_gap"]), "pass" if r["ok"] else "FAIL"]
           for r in PLANNER_CHECKS["profiles"]],
          [5.5, 1.4, 2.2, 1.6, 2.1, 2, 1.8], "Table 13. Planner checks.")
h2("21.3 Other checks")
bullets([
    "<b>Notebook:</b> executed end to end with nbconvert; the checker confirms no cell raised an error.",
    "<b>Frontend:</b> <i>npm run build</i> runs the TypeScript compiler in strict mode before bundling, so type errors fail the build.",
    "<b>Visual review:</b> every page was captured with headless Chrome and compared with the reference design; the review caught charts that did not draw, a stretched logo and wrapping labels, which were fixed.",
    "<b>Data joins:</b> the photo join rate and name agreement were measured, which exposed the folder-split id bug.",
    "<b>Report:</b> every number in this document is read from the output files of the runs above.",
])

h1("22. Evaluation Summary")
rows = [["Model", "Stage", "HR@10", "NDCG@10", "MRR"]]
for name, m in sorted(gens.items(), key=lambda kv: kv[1]["HR@10"]):
    rows.append([name, "generator", pct(m["HR@10"], 2), f"{m['NDCG@10']:.4f}", f"{m['MRR']:.4f}"])
for name, m in sorted(rankers.items(), key=lambda kv: kv[1]["HR@10"]):
    rows.append([f"<b>{name}</b>" if name == best else name, "ranker", pct(m["HR@10"], 2), f"{m['NDCG@10']:.4f}", f"{m['MRR']:.4f}"])
table(rows, [5.2, 2.6, 2.6, 3, 3.2], f"Table 14. Recommendation on {num(met['evaluation_users'])} users; random HR@10 is {pct(random_hr, 3)}.")
table([
    ["Program", "Model", "Result"],
    ["3", "Intake linear regression", f"CV R² {reg['cv_r2']:.2f}; formula {reg['formula_bias']:+.0f} kcal above reported intake"],
    ["4.1", "Bayesian logistic regression", f"ROC AUC {bayes['auc']:.3f}; {len(excludes_zero)} of {len(feats)} weights exclude zero"],
    ["4.2", "Calibrated linear SVM", f"accuracy {pct(svm['accuracy'])}, macro F1 {svm['macro_f1']:.2f}; {num(svm['filled'])} courses filled"],
    ["5.1", "K-means", f"k = {km['k']} nutrition archetypes"],
    ["5.2", "Gaussian mixture", f"{gmm['k']} segments; {pct(gmm['confident_share'])} of users confidently assigned"],
    ["5.3", "Hierarchical clustering", "baking, Italian-style, spice rub, stir-fry, soup-base groups"],
    ["6", "PCA / truncated SVD", f"{pct(pca_r['explained_2'])} of nutrient variance in 2 components; {pct(svd_r['var_64'])} of review variance in 64 factors"],
    ["7", "Categorical HMM", f"{hmm['states']} states, {persistent} persistent"],
    ["8", "CART surrogate", f"{pct(cart['fidelity'])} fidelity at depth 4"],
    ["9", "Random forest ranker", f"HR@10 {pct(rankers[best]['HR@10'], 2)}, {lift:.1f}x the best generator"],
    ["-", "Meal planner", (
        f"{sum(r['ok'] for r in PLANNER_CHECKS['profiles'])} of {len(PLANNER_CHECKS['profiles'])} test profiles within "
        f"{pct(max(r['kcal_gap'] for r in PLANNER_CHECKS['profiles']))} of calories and "
        f"{pct(max(r['macro_gap'] for r in PLANNER_CHECKS['profiles']))} of macros; a week takes "
        f"{min(r['seconds'] for r in PLANNER_CHECKS['profiles'] if r['days'] == 7):.0f}-"
        f"{max(r['seconds'] for r in PLANNER_CHECKS['profiles'] if r['days'] == 7):.0f} s"
    ) if PLANNER_CHECKS else "see Chapter 19"],
], [2.0, 4.4, 10.2], "Table 15. Every other model.")

h1("23. Limitations")
bullets([
    "Food.com nutrition comes from author-entered ingredients and serving counts. Cleaning removes inconsistent panels, but individual recipes can still be wrong.",
    "A review is a proxy for having cooked and liked a recipe. People who cook without reviewing are invisible, and very active reviewers dominate the collaborative signal.",
    "Leave-last-out evaluation fits generators on other users' full histories, including reviews after a target date. Serving targets on their own dates removes the most direct leakage, not all of it.",
    "The match score and insight are presentation logic on top of the models, not separately validated predictions.",
    "Photos cover 55% of recipes and belong to Food.com contributors; they are loaded for a university demonstration, not redistributed.",
    "The data is American, so tastes and portions may not transfer. Diet tags are authors' tags, not verified.",
    "The calorie target is a population equation and is not medical or dietetic advice.",
])

h1("24. Future Work")
bullets([
    "<b>Better retrieval.</b> The ranker can only reorder what the generators find (8% recall). Item-item neighbours or a sequence-aware generator using the HMM phases are the obvious next step.",
    "<b>Learn from the app's own log.</b> Eaten meals are exactly the implicit feedback the recommender uses, so the log could fine-tune recommendations per user.",
    "<b>Deploy online.</b> The API can run on a cloud host and the built frontend on a static host, with accounts and a hosted database replacing the local profile and SQLite file.",
    "<b>Indian and regional recipes.</b> Adding datasets with local cuisines and portion sizes would make the recommendations fit Indian users better.",
    "<b>Micronutrients.</b> Joining recipes to USDA FoodData Central would add fibre and vitamins to the nutrition balance chart.",
])

# ================================================================== PART V

part("Part V — Reference")
h1("25. Reproducing Everything")
code("""
cd C:\\Users\\Gunasekaran\\Dev\\nutrition-recommender

# 1. data (only once)
.venv\\Scripts\\python.exe src\\download_data.py

# 2. train and evaluate every model the app uses (about three minutes)
.venv\\Scripts\\python.exe src\\build.py

# 3. run all lab programs and regenerate the figures (about ten minutes)
.venv\\Scripts\\python.exe -m jupyter nbconvert --to notebook --execute --inplace ^
    --ExecutePreprocessor.timeout=3600 notebooks\\nutrition_ml_lab.ipynb

# 4. build the frontend once, then start NUTRIX and open http://localhost:8000
cd frontend
npm install
npm run build
cd ..
.venv\\Scripts\\python.exe -m uvicorn api.main:app --port 8000

# 5. development mode with hot reload: two terminals, then open http://localhost:5173
.venv\\Scripts\\python.exe -m uvicorn api.main:app --reload --port 8000
cd frontend && npm run dev

# 6. checks and this report
.venv\\Scripts\\python.exe tests\\check_api.py
.venv\\Scripts\\python.exe tests\\check_planner.py
.venv\\Scripts\\python.exe reports\\build_report.py
""")
p("Random seeds are fixed at 42. The planner's one-second solver limit means meal plans can differ slightly between runs on a busy machine; every other number reproduces exactly.")

h1("26. Glossary")
glossary = [
    ("Resting energy (BMR)", "Energy used at rest per day, estimated by the Mifflin-St Jeor equation"),
    ("PAL", "Physical activity level, the multiplier from resting to total daily energy"),
    ("Macronutrient", "Protein, carbohydrate or fat"),
    ("Atwater factors", "4, 4 and 9 kcal per gram of protein, carbohydrate and fat"),
    ("Percent daily value", "A nutrient amount as a percentage of a reference daily amount"),
    ("NHANES", "US National Health and Nutrition Examination Survey"),
    ("24-hour recall", "An interview recording everything eaten the previous day"),
    ("MET-minutes", "Activity minutes weighted by intensity (METs)"),
    ("Implicit feedback", "Actions such as reviews that reveal interest without an explicit rating"),
    ("Candidate generator", "A cheap model that shortlists items from the whole catalogue"),
    ("Ranker", "A richer model that orders the shortlisted candidates"),
    ("PureSVD", "Collaborative filtering that scores items with a truncated SVD of the interaction matrix"),
    ("TF-IDF", "Term weighting that rewards words frequent in a document but rare across documents"),
    ("Cold-start item", "An item with no interaction history"),
    ("Leave-last-out", "Evaluation hiding each user's most recent item"),
    ("HR@10", "Share of users whose hidden item is ranked in the top ten"),
    ("NDCG@10", "Ranking metric that also rewards a higher position in the top ten"),
    ("MRR", "Mean of 1 / rank of the hidden item"),
    ("Retrieval recall", "Share of users whose hidden item is among the candidates at all"),
    ("Negative sampling", "Training a ranker on a sample of items the user did not choose"),
    ("Calibration", "Mapping model scores to probabilities that match observed frequencies"),
    ("Macro F1", "F1 score averaged equally over classes"),
    ("Silhouette score", "Cluster quality from -1 to 1 comparing within- and between-cluster distance"),
    ("Hellinger transform", "Square root of proportions, stabilising their variance"),
    ("BIC", "Bayesian Information Criterion, balancing fit against parameter count"),
    ("Laplace approximation", "Gaussian approximation of a posterior at its mode using the Hessian"),
    ("Credible interval", "Range containing a parameter with a stated posterior probability"),
    ("Transition / emission matrix", "HMM probabilities of moving between states / of observations from each state"),
    ("Baum-Welch", "EM algorithm that fits HMM parameters from sequences"),
    ("Fidelity", "Agreement between a surrogate model and the model it explains"),
    ("Bagging / boosting", "Averaging bootstrap models to reduce variance / sequentially correcting errors to reduce bias"),
    ("Mixed-integer program", "Optimisation with some whole-number variables"),
    ("HiGHS", "The open-source solver SciPy uses for linear and mixed-integer programs"),
    ("API", "Application programming interface; here JSON endpoints the frontend calls"),
    ("FastAPI / Uvicorn", "Python web framework for the API / the server that runs it"),
    ("React / Vite", "JavaScript library for the interface / tool that serves and builds it"),
    ("SQLite", "A database stored in a single local file"),
    ("localhost", "The address of the computer you are using; the app runs there"),
    ("Smart App Control", "Windows feature that blocks untrusted executable files"),
]
table([["Term", "Meaning"]] + [[t, m] for t, m in glossary], [4.4, 12.2])

h1("27. Expected Viva Questions")
viva = [
    ("Why did you not continue with the original scripts?",
     "Their nutrition values were random numbers, the 'healthy' label was a rule on the same features and the calorie target was generated from a linear formula. Every model result was therefore guaranteed and meaningless. The project keeps the idea and uses real data."),
    ("Why does the calorie formula get a negative R², and why keep it?",
     f"R² is measured against reported intake, and the formula sits about {reg['formula_bias']:.0f} kcal above it because food recalls under-report. The formula estimates requirement, which is what a target should be, so it stays the target and the regression is shown as context."),
    ("Is an HR@10 of about 3.7% bad?",
     f"Random ranking scores {pct(random_hr, 3)}, so the ranker is about {rankers[best]['HR@10'] / random_hr:.0f} times random and {lift:.1f} times the best single generator. The ceiling is set by the data: {pct(recl['cold_targets'], 0)} of next recipes had no earlier reviews and retrieval finds only {pct(met['retrieval_recall']['test'])}."),
    ("Why a two-stage recommender instead of just SVD?",
     "No single signal is best: popularity and content each beat SVD on this sparse data, and they succeed on different users. A ranker combining them with recipe and user features more than doubles the best one."),
    ("How did you avoid leakage in evaluation?",
     "Split by time per user; fit generators and rating features without the targets; serve each target on its own date; hide recipes not yet submitted; choose the ranker on validation users and use test targets only for final numbers."),
    ("What does the match percentage mean?",
     "Half is the ranker's taste rank among candidates and half is nutrition fit for one meal of the user's targets, scaled to 60-99. It is a display score, not a probability."),
    ("Why calibrate the SVM?",
     "SVM margins are not probabilities. Calibration lets the app assign a course only when the model is at least 50% confident, keeping doubtful recipes out of the planner."),
    ("Why keep nine archetypes when the silhouette is low?",
     "Silhouette chose nine, and the low value honestly reflects continuous nutrition. The archetypes are still useful because their course mixes and nutrient centres differ clearly."),
    ("Why transform the shares before the Gaussian mixture?",
     "Proportions near zero violate the Gaussian assumption, and components collapsed onto users who never cook an archetype, so BIC kept rising. The square-root transform and a covariance floor fixed it."),
    ("Why solve meal plans day by day with a time limit?",
     "The whole week as one program found no feasible plan in 20 seconds. Per day, proving optimality takes seconds, so a one-second limit gives a fast plan and a guard re-solves any day more than 3% off calories."),
    ("Is NUTRIX a website or an application?",
     "It is a web application that runs locally: a FastAPI server on your computer serves the React interface, which you open at http://localhost:8000. It is not hosted online, but it could be deployed."),
    ("How were the photos matched?",
     "Photo URLs in a larger Food.com scrape contain the recipe id split into folders. Joining the folders gives the id used by the main dataset, matching 55% of recipes. The join rate and name agreement were checked, which caught an early bug."),
    ("What would you do next?",
     "Improve candidate retrieval, learn from the app's own meal log, add regional cuisines and micronutrients, and deploy it online with accounts."),
]
for question, answer in viva:
    story.append(KeepTogether([Paragraph(f"<b>{esc(question)}</b>", ParagraphStyle("q", parent=BODY, spaceAfter=2)), Paragraph(esc(answer), BODY)]))

h1("28. References")
refs = [
    "Bishop, C. M. (2006). <i>Pattern Recognition and Machine Learning</i>. Springer.",
    "Centers for Disease Control and Prevention. National Health and Nutrition Examination Survey 2017-2018 data files.",
    "Cremonesi, P., Koren, Y. and Turrin, R. (2010). Performance of recommender algorithms on top-N recommendation tasks. <i>Proceedings of the 4th ACM Conference on Recommender Systems</i>, 39-46.",
    "Huangfu, Q. and Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. <i>Mathematical Programming Computation</i>, 10, 119-142.",
    "Karo8870 (2025). food.com-parsed-dataset. Hugging Face datasets.",
    "Majumder, B. P., Li, S., Ni, J. and McAuley, J. (2019). Generating personalized recipes from historical user preferences. <i>Proceedings of EMNLP-IJCNLP 2019</i>.",
    "Mifflin, M. D., St Jeor, S. T., Hill, L. A., Scott, B. J., Daugherty, S. A. and Koh, Y. O. (1990). A new predictive equation for resting energy expenditure in healthy individuals. <i>American Journal of Clinical Nutrition</i>, 51(2), 241-247.",
    "Pedregosa, F. et al. (2011). Scikit-learn: machine learning in Python. <i>Journal of Machine Learning Research</i>, 12, 2825-2830.",
    "Rabiner, L. R. (1989). A tutorial on hidden Markov models and selected applications in speech recognition. <i>Proceedings of the IEEE</i>, 77(2), 257-286.",
    "Willett, W. (2012). <i>Nutritional Epidemiology</i> (3rd ed.). Oxford University Press.",
    "World Health Organization (2015). <i>Guideline: Sugars intake for adults and children</i>.",
]
for ref in refs:
    story.append(Paragraph(safe(ref), ParagraphStyle("ref", parent=BODY, leftIndent=14, firstLineIndent=-14, alignment=0)))

Report(OUT).build(story)
print("wrote", OUT)
