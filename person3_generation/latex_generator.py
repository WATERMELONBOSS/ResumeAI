"""
latex_generator.py
------------------
Stage 3 — Resume Generation.

Tries pdflatex (Jake's Resume LaTeX template via Jinja2) first.
Falls back to reportlab if pdflatex is unavailable or fails.

The reportlab path renders ALL sections from the assembled resume:
  - Contact with LinkedIn and location
  - Education with courses
  - Experience with full bullets
  - Projects
  - Categorized skills
  - Extra sections: publications, leadership, achievements

Public API:
    from person3_generation.latex_generator import generate_resume_pdf
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from jinja2 import Environment, BaseLoader

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LaTeX TEMPLATE  (Jake's Resume style)
# ─────────────────────────────────────────────────────────────────────────────

_LATEX_TEMPLATE = r"""
\documentclass[letterpaper,11pt]{article}
\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}
\usepackage[T1]{fontenc}
\input{glyphtounicode}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

\pdfgentounicode=1

\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-2pt}}}
\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}
\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}
\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

\begin{document}

\begin{center}
    \textbf{\Huge \scshape {{ contact.name | default('') | le }} } \\[3pt]
    \small
    {{ contact.phone | default('') | le }}
    {% if contact.phone and contact.email %} $|$ {% endif %}
    \href{mailto:{{ contact.email | default('') }}}{\underline{ {{ contact.email | default('') | le }} }}
    {% if contact.linkedin %} $|$ \href{https://{{ contact.linkedin | default('') }}}{\underline{ {{ contact.linkedin | default('') | le }} }} {% endif %}
    {% if contact.location %} $|$ {{ contact.location | default('') | le }} {% endif %}
\end{center}

\section{Education}
  \resumeSubHeadingListStart
    {% for edu in education %}
    \resumeSubheading
      { {{ edu.school | default('') | le }} }{ {{ edu.dates | default('') | le }} }
      { {{ edu.degree | default('') | le }} }{ {{ edu.details | join(', ') | le if edu.details else '' }} }
    {% if edu.courses %}
    \resumeItemListStart
      \resumeItem{\textit{Courses: {{ edu.courses | le }} }}
    \resumeItemListEnd
    {% endif %}
    {% endfor %}
  \resumeSubHeadingListEnd

\section{Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
    {% for cat in skills.categorized %}
     \textbf{ {{ cat.category | le }} }{: {{ cat.skills | join(', ') | le }} } \\
    {% endfor %}
    }}
 \end{itemize}

\section{Experience}
  \resumeSubHeadingListStart
    {% for exp in experience %}
    \resumeSubheading
      { {{ exp.company | default('') | le }} }{ {{ exp.dates | default('') | le }} }
      { {{ exp.title | default('') | le }} }{ {{ exp.location | default('') | le }} }
      \resumeItemListStart
        {% for bullet in exp.bullets %}
        \resumeItem{ {{ bullet | le }} }
        {% endfor %}
      \resumeItemListEnd
    {% endfor %}
  \resumeSubHeadingListEnd

{% if projects %}
\section{Projects}
    \resumeSubHeadingListStart
      {% for proj in projects %}
      \resumeProjectHeading
          {\textbf{ {{ proj.name | default('') | le }} }{% if proj.description %} $|$ \emph{\small {{ proj.description | le }} }{% endif %} }{}
          \resumeItemListStart
            {% for bullet in proj.bullets %}
            \resumeItem{ {{ bullet | le }} }
            {% endfor %}
          \resumeItemListEnd
      {% endfor %}
    \resumeSubHeadingListEnd
{% endif %}

\end{document}
"""


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX ESCAPE
# ─────────────────────────────────────────────────────────────────────────────

_LATEX_SPECIAL = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\^{}",
    "\\": r"\textbackslash{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
}
_LATEX_ESCAPE_RE = re.compile(
    "("
    + "|".join(re.escape(k) for k in sorted(_LATEX_SPECIAL, key=len, reverse=True))
    + ")"
)


def _latex_escape(text: str) -> str:
    if not text:
        return ""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL[m.group(0)], str(text))


def _build_jinja_env() -> Environment:
    env = Environment(
        loader=BaseLoader(),
        variable_start_string="{{",
        variable_end_string="}}",
        block_start_string="{%",
        block_end_string="%}",
        comment_start_string="##(",
        comment_end_string=")##",  # avoids {#1} clash
        autoescape=False,
    )
    env.filters["le"] = _latex_escape  # short alias for template readability
    env.filters["latex_escape"] = _latex_escape
    return env


# ─────────────────────────────────────────────────────────────────────────────
# REPORTLAB STYLES HELPER
# ─────────────────────────────────────────────────────────────────────────────


def _build_styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    styles = getSampleStyleSheet()
    return {
        "name": ParagraphStyle(
            "RName",
            parent=styles["Title"],
            fontSize=16,
            spaceBefore=0,
            spaceAfter=2,
            alignment=TA_CENTER,
        ),
        "contact": ParagraphStyle(
            "RContact",
            parent=styles["Normal"],
            fontSize=9,
            alignment=TA_CENTER,
            spaceBefore=0,
            spaceAfter=3,
        ),
        "section": ParagraphStyle(
            "RSection",
            parent=styles["Heading2"],
            fontSize=11,
            spaceAfter=2,
            spaceBefore=4,
            textColor=colors.black,
        ),
        "entry": ParagraphStyle(
            "REntry", parent=styles["Normal"], fontSize=10, spaceAfter=1
        ),
        "sub": ParagraphStyle(
            "RSub",
            parent=styles["Normal"],
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=1,
        ),
        "bullet": ParagraphStyle(
            "RBullet",
            parent=styles["Normal"],
            fontSize=9.5,
            leftIndent=12,
            spaceAfter=1,
            bulletIndent=4,
        ),
        "courses": ParagraphStyle(
            "RCourses",
            parent=styles["Normal"],
            fontSize=8.5,
            textColor=colors.HexColor("#444444"),
            leftIndent=8,
            spaceAfter=1,
            italics=True,
        ),
        "footer": ParagraphStyle(
            "RFooter",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceBefore=8,
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPORTLAB GENERATOR
# ─────────────────────────────────────────────────────────────────────────────


def _generate_with_reportlab(assembled_data: dict, output_pdf: Path) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    contact = assembled_data.get("contact", {})
    experience = assembled_data.get("experience", [])
    projects = assembled_data.get("projects", [])
    education = assembled_data.get("education", [])
    skills_data = assembled_data.get("skills", {})
    extra = assembled_data.get("extra_sections", {})
    jd_meta = assembled_data.get("jd_meta", {})
    scores = assembled_data.get("overall_scores", {})

    # skills may be old flat list or new dict — handle both
    if isinstance(skills_data, dict):
        skills_flat = skills_data.get("flat", [])
        skills_categorized = skills_data.get("categorized", [])
    else:
        skills_flat = skills_data
        skills_categorized = [{"category": "Skills", "skills": skills_data}]

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.40 * inch,
        bottomMargin=0.50 * inch,
    )
    S = _build_styles()
    story = []

    def _hr(thick=0.5):
        story.append(
            HRFlowable(width="100%", thickness=thick, color=colors.black, spaceAfter=2)
        )

    def _section_header(title: str):
        story.append(Paragraph(title, S["section"]))
        _hr(0.3)

    def _gap(pts=3):
        story.append(Spacer(1, pts))

    # ── HEADER ──────────────────────────────────────────────────────────────
    story.append(Paragraph(contact.get("name", ""), S["name"]))

    contact_parts = []
    if contact.get("phone"):
        contact_parts.append(contact["phone"])
    if contact.get("email"):
        contact_parts.append(contact["email"])
    if contact.get("linkedin"):
        contact_parts.append(contact["linkedin"])
    if contact.get("location"):
        contact_parts.append(contact["location"])
    if contact_parts:
        story.append(Paragraph(" | ".join(contact_parts), S["contact"]))
    _hr(0.5)

    # ── EDUCATION ───────────────────────────────────────────────────────────
    _section_header("EDUCATION")
    for edu in education:
        details_str = " | ".join(edu.get("details", []))
        story.append(
            Paragraph(
                f"<b>{edu.get('school', '')}</b> &nbsp;&nbsp;&nbsp; {edu.get('dates', '')}",
                S["entry"],
            )
        )
        deg_line = edu.get("degree", "")
        if details_str:
            deg_line += f"  ({details_str})"
        story.append(Paragraph(deg_line, S["sub"]))
        if edu.get("courses"):
            story.append(Paragraph(f"Courses: {edu['courses']}", S["courses"]))
    _gap()

    # ── SKILLS ──────────────────────────────────────────────────────────────
    _section_header("SKILLS")
    for cat in skills_categorized:
        cat_name = cat.get("category", "Skills")
        cat_skills = ", ".join(cat.get("skills", []))
        story.append(Paragraph(f"<b>{cat_name}</b>: {cat_skills}", S["bullet"]))
    _gap()

    # ── EXPERIENCE ──────────────────────────────────────────────────────────
    _section_header("EXPERIENCE")
    for exp in experience:
        loc = exp.get("location", "")
        title_loc = exp.get("title", "")
        if loc:
            title_loc += f"  –  {loc}"
        story.append(
            Paragraph(
                f"<b>{exp.get('company', '')}</b> &nbsp;&nbsp;&nbsp; {exp.get('dates', '')}",
                S["entry"],
            )
        )
        story.append(Paragraph(title_loc, S["sub"]))
        for bullet in exp.get("bullets", []):
            story.append(Paragraph(f"\u2022 {bullet}", S["bullet"]))
    _gap()

    # ── PROJECTS ────────────────────────────────────────────────────────────
    if projects:
        _section_header("PROJECTS")
        for proj in projects:
            heading = f"<b>{proj.get('name', '')}</b>"
            if proj.get("description"):
                heading += f" | <i>{proj['description']}</i>"
            story.append(Paragraph(heading, S["entry"]))
            for bullet in proj.get("bullets", []):
                story.append(Paragraph(f"\u2022 {bullet}", S["bullet"]))
        _gap()

    # ── EXTRA SECTIONS ──────────────────────────────────────────────────────
    EXTRA_LABELS = {
        "publications": "RESEARCH & PUBLICATIONS",
        "leadership": "LEADERSHIP AND TEACHING EXPERIENCE",
        "achievements": "ACHIEVEMENTS & EXTRACURRICULAR ACTIVITIES",
        "certifications": "CERTIFICATIONS",
    }

    for key, label in EXTRA_LABELS.items():
        section_text = extra.get(key, "").strip()
        if not section_text:
            continue
        _section_header(label)
        for line in section_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Detect bullet lines vs heading lines
            if line.startswith(("•", "-", "–", "*", "·")):
                clean = line.lstrip("•–-*· ").strip()
                story.append(Paragraph(f"\u2022 {clean}", S["bullet"]))
            elif len(line) < 90 and not line.endswith("."):
                # Likely a sub-heading within the section
                story.append(Paragraph(f"<b>{line}</b>", S["entry"]))
            else:
                story.append(Paragraph(line, S["bullet"]))
        _gap()

    # ── FOOTER ──────────────────────────────────────────────────────────────
    semantic_pct = int(scores.get("semantic", 0.0) * 100)
    jd_label = jd_meta.get("title", "")
    if jd_meta.get("company"):
        jd_label += f" at {jd_meta['company']}"
    story.append(
        Paragraph(
            f"Tailored for: {jd_label} — Semantic match: {semantic_pct}%",
            S["footer"],
        )
    )

    doc.build(story)
    log.info("reportlab PDF written to: %s", output_pdf)


# ─────────────────────────────────────────────────────────────────────────────
# PDFLATEX GENERATOR
# ─────────────────────────────────────────────────────────────────────────────


def _generate_with_pdflatex(assembled_data: dict, output_pdf: Path) -> None:
    env = _build_jinja_env()
    template = env.from_string(_LATEX_TEMPLATE)

    # Flatten skills for LaTeX template
    skills_data = assembled_data.get("skills", {})
    if isinstance(skills_data, dict):
        latex_data = dict(assembled_data)
        latex_data["skills"] = skills_data
    else:
        latex_data = dict(assembled_data)
        latex_data["skills"] = {
            "flat": skills_data,
            "categorized": [{"category": "Skills", "skills": skills_data}],
        }

    latex_source = template.render(**latex_data)

    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = Path(tmpdir) / "resume.tex"
        tex_path.write_text(latex_source, encoding="utf-8")
        result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-output-directory",
                tmpdir,
                str(tex_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        compiled_pdf = Path(tmpdir) / "resume.pdf"
        if result.returncode != 0 or not compiled_pdf.exists():
            raise RuntimeError(f"pdflatex exited with code {result.returncode}")
        shutil.copy2(str(compiled_pdf), str(output_pdf))

    log.info("pdflatex compiled successfully → %s", output_pdf)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────


def generate_resume_pdf(
    assembled_data: dict,
    output_dir: str = "results",
    filename_stem: str = "tailored_resume",
    force_reportlab: bool = False,
) -> str:
    """
    Generate a tailored resume PDF from assembled resume data.

    Tries pdflatex first; falls back to reportlab automatically.

    Returns absolute path to the generated PDF.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = out_dir / f"{filename_stem}.pdf"

    pdflatex_available = shutil.which("pdflatex") is not None

    if not force_reportlab and pdflatex_available:
        try:
            _generate_with_pdflatex(assembled_data, output_pdf)
            log.info("PDF generated via pdflatex: %s", output_pdf)
            return str(output_pdf.resolve())
        except Exception as exc:
            log.warning("pdflatex failed (%s) — falling back to reportlab", exc)

    try:
        _generate_with_reportlab(assembled_data, output_pdf)
        log.info("PDF generated via reportlab: %s", output_pdf)
        return str(output_pdf.resolve())
    except Exception as exc:
        raise RuntimeError(f"Both PDF generation methods failed: {exc}") from exc
