"""
latex_generator.py
------------------
Stage 3 — LaTeX Resume Generation.

Uses Jinja2 to fill a Jake's-style LaTeX resume template with assembled
resume data, then calls pdflatex via subprocess to produce a PDF.

If pdflatex is unavailable on the system (e.g., CI environment without
TeX Live), the module falls back to reportlab-based PDF generation so
the pipeline never hard-fails.

Public API:
    from person3_generation.latex_generator import generate_resume_pdf

Usage:
    pdf_path = generate_resume_pdf(assembled_data, output_dir="results")
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
# LaTeX TEMPLATE  (Jake's Resume style — single-column, ATS-friendly)
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

%--- Custom Commands ---
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

%--- HEADING ---
\begin{center}
    \textbf{\Huge \scshape {{ contact.name | default('') | latex_escape }} } \\[3pt]
    \small
    {{ contact.phone | default('') | latex_escape }}
    {% if contact.phone and contact.email %} $|$ {% endif %}
    \href{mailto:{{ contact.email | default('') }}}{\underline{ {{ contact.email | default('') | latex_escape }} }}
\end{center}

%--- EDUCATION ---
\section{Education}
  \resumeSubHeadingListStart
    {% for edu in education %}
    \resumeSubheading
      { {{ edu.school | default('') | latex_escape }} }
      { {{ edu.dates | default('') | latex_escape }} }
      { {{ edu.degree | default('') | latex_escape }} }
      { {{ edu.details | join(', ') | latex_escape if edu.details else '' }} }
    {% endfor %}
  \resumeSubHeadingListEnd

%--- EXPERIENCE ---
\section{Experience}
  \resumeSubHeadingListStart
    {% for exp in experience %}
    \resumeSubheading
      { {{ exp.company | default('') | latex_escape }} }
      { {{ exp.dates | default('') | latex_escape }} }
      { {{ exp.title | default('') | latex_escape }} }
      { {{ exp.location | default('') | latex_escape }} }
      \resumeItemListStart
        {% for bullet in exp.bullets %}
        \resumeItem{ {{ bullet | latex_escape }} }
        {% endfor %}
      \resumeItemListEnd
    {% endfor %}
  \resumeSubHeadingListEnd

{% if projects %}
%--- PROJECTS ---
\section{Projects}
    \resumeSubHeadingListStart
      {% for proj in projects %}
      \resumeProjectHeading
          {\textbf{ {{ proj.name | default('') | latex_escape }} }
          {% if proj.description %} $|$ \emph{\small {{ proj.description | latex_escape }} } {% endif %} }{}
          \resumeItemListStart
            {% for bullet in proj.bullets %}
            \resumeItem{ {{ bullet | latex_escape }} }
            {% endfor %}
          \resumeItemListEnd
      {% endfor %}
    \resumeSubHeadingListEnd
{% endif %}

%--- TECHNICAL SKILLS ---
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Skills}{ : {{ skills | join(', ') | latex_escape }} }
    }}
 \end{itemize}

\vspace{4pt}
\noindent\small\textit{Tailored for: {{ jd_meta.title | default('') | latex_escape }}
{% if jd_meta.company %} at {{ jd_meta.company | latex_escape }} {% endif %} ---
Semantic match score: {{ "%.0f"|format(overall_scores.semantic * 100) }}\%}

\end{document}
"""


# ─────────────────────────────────────────────────────────────────────────────
# LATEX ESCAPE HELPER
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
    + "|".join(
        re.escape(k) for k in sorted(_LATEX_SPECIAL.keys(), key=len, reverse=True)
    )
    + ")"
)


def _latex_escape(text: str) -> str:
    """Escape special LaTeX characters in a plain-text string."""
    if not text:
        return ""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL[m.group(0)], str(text))


# ─────────────────────────────────────────────────────────────────────────────
# JINJA2 ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────


def _build_jinja_env() -> Environment:
    """
    Build a Jinja2 environment with LaTeX-safe delimiters.

    LaTeX command definitions use {#1}, {#2} for arguments, which collide
    with Jinja2's default {# ... #} comment syntax.  Changing the comment
    delimiters to ##( ... )## sidesteps the conflict completely while keeping
    the familiar {{ }} and {% %} for variables and blocks.
    """
    env = Environment(
        loader=BaseLoader(),
        variable_start_string="{{",
        variable_end_string="}}",
        block_start_string="{%",
        block_end_string="%}",
        comment_start_string="##(",  # never appears in LaTeX source
        comment_end_string=")##",
        autoescape=False,
    )
    env.filters["latex_escape"] = _latex_escape
    return env


# ─────────────────────────────────────────────────────────────────────────────
# REPORTLAB FALLBACK
# ─────────────────────────────────────────────────────────────────────────────


def _generate_with_reportlab(assembled_data: dict, output_pdf: Path) -> None:
    """
    Fallback PDF generator using reportlab when pdflatex is unavailable.
    Produces a clean, readable PDF — not as typographically polished as LaTeX
    but fully functional for evaluation purposes.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    contact = assembled_data.get("contact", {})
    experience = assembled_data.get("experience", [])
    projects = assembled_data.get("projects", [])
    education = assembled_data.get("education", [])
    skills = assembled_data.get("skills", [])
    jd_meta = assembled_data.get("jd_meta", {})
    scores = assembled_data.get("overall_scores", {})

    doc = SimpleDocTemplate(
        str(output_pdf),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.40 * inch,
        bottomMargin=0.50 * inch,
    )
    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "Name",
        parent=styles["Title"],
        fontSize=16,
        spaceBefore=0,
        spaceAfter=2,
        alignment=TA_CENTER,
    )
    contact_style = ParagraphStyle(
        "Contact",
        parent=styles["Normal"],
        fontSize=9,
        alignment=TA_CENTER,
        spaceBefore=0,
        spaceAfter=3,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=11,
        spaceAfter=2,
        spaceBefore=4,
        textColor=colors.black,
        borderPad=0,
    )
    entry_style = ParagraphStyle(
        "Entry", parent=styles["Normal"], fontSize=10, spaceAfter=1
    )
    sub_style = ParagraphStyle(
        "Sub", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=2
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=styles["Normal"],
        fontSize=9.5,
        leftIndent=12,
        spaceAfter=1,
        bulletIndent=4,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER,
        spaceBefore=12,
    )

    story = []

    # Name
    story.append(Paragraph(contact.get("name", ""), name_style))

    # Contact line
    parts = [p for p in [contact.get("phone", ""), contact.get("email", "")] if p]
    if parts:
        story.append(Paragraph(" | ".join(parts), contact_style))

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))

    # Education
    if education:
        story.append(Paragraph("EDUCATION", section_style))
        story.append(HRFlowable(width="100%", thickness=0.3, color=colors.black))
        for edu in education:
            story.append(
                Paragraph(
                    f"<b>{edu.get('school', '')}</b> &nbsp;&nbsp; {edu.get('dates', '')}",
                    entry_style,
                )
            )
            story.append(Paragraph(edu.get("degree", ""), sub_style))
            for detail in edu.get("details", []):
                story.append(Paragraph(f"  {detail}", sub_style))

    # Experience
    if experience:
        story.append(Spacer(1, 3))
        story.append(Paragraph("EXPERIENCE", section_style))
        story.append(HRFlowable(width="100%", thickness=0.3, color=colors.black))
        for exp in experience:
            story.append(
                Paragraph(
                    f"<b>{exp.get('company', '')}</b> &nbsp;&nbsp; {exp.get('dates', '')}",
                    entry_style,
                )
            )
            story.append(
                Paragraph(
                    f"{exp.get('title', '')}  {exp.get('location', '')}",
                    sub_style,
                )
            )
            for bullet in exp.get("bullets", []):
                story.append(Paragraph(f"\u2022 {bullet}", bullet_style))

    # Projects
    if projects:
        story.append(Spacer(1, 3))
        story.append(Paragraph("PROJECTS", section_style))
        story.append(HRFlowable(width="100%", thickness=0.3, color=colors.black))
        for proj in projects:
            desc = proj.get("description", "")
            heading = f"<b>{proj.get('name', '')}</b>"
            if desc:
                heading += f" | <i>{desc}</i>"
            story.append(Paragraph(heading, entry_style))
            for bullet in proj.get("bullets", []):
                story.append(Paragraph(f"\u2022 {bullet}", bullet_style))

    # Skills
    if skills:
        story.append(Spacer(1, 3))
        story.append(Paragraph("TECHNICAL SKILLS", section_style))
        story.append(HRFlowable(width="100%", thickness=0.3, color=colors.black))
        story.append(Paragraph(", ".join(skills), bullet_style))

    # Footer
    semantic_pct = int(scores.get("semantic", 0.0) * 100)
    jd_label = jd_meta.get("title", "")
    if jd_meta.get("company"):
        jd_label += f" at {jd_meta['company']}"
    story.append(
        Paragraph(
            f"Tailored for: {jd_label} — Semantic match: {semantic_pct}%",
            footer_style,
        )
    )

    doc.build(story)
    log.info("reportlab PDF written to: %s", output_pdf)


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

    Tries pdflatex first (best quality); falls back to reportlab if
    pdflatex is not installed or compilation fails.

    Args:
        assembled_data:  Output of assembler.assemble_resume().
        output_dir:      Directory where the PDF will be saved.
        filename_stem:   Base name for the output file (no extension).
        force_reportlab: Skip pdflatex and use reportlab directly.

    Returns:
        Absolute path to the generated PDF file.

    Raises:
        RuntimeError: If both pdflatex and reportlab fail.
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

    # Fallback
    try:
        _generate_with_reportlab(assembled_data, output_pdf)
        log.info("PDF generated via reportlab: %s", output_pdf)
        return str(output_pdf.resolve())
    except Exception as exc:
        raise RuntimeError(f"Both PDF generation methods failed: {exc}") from exc


def _generate_with_pdflatex(assembled_data: dict, output_pdf: Path) -> None:
    """
    Render the Jinja2 LaTeX template and compile it with pdflatex.
    All intermediate files are written to a temp directory and cleaned up.
    """
    env = _build_jinja_env()
    template = env.from_string(_LATEX_TEMPLATE)
    latex_source = template.render(**assembled_data)

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
            log.debug("pdflatex stdout:\n%s", result.stdout[-2000:])
            log.debug("pdflatex stderr:\n%s", result.stderr[-1000:])
            raise RuntimeError(f"pdflatex exited with code {result.returncode}")

        shutil.copy2(str(compiled_pdf), str(output_pdf))

    log.info("pdflatex compiled successfully → %s", output_pdf)
