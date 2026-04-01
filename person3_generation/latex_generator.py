"""
latex_generator.py - LaTeX Resume Generation
Person 3 - ResumeAI Project

Takes the assembled resume data and generates a professional PDF using:
- Jinja2 for templating
- Jake's Resume LaTeX template (standard for tech resumes)
- pdflatex for PDF compilation

Author: [Your Name]
CS 5100 - Foundations of AI
"""

import os
import json
import subprocess
import tempfile
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

# Check if Jinja2 is available
try:
    from jinja2 import Environment, FileSystemLoader, BaseLoader
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    print("Warning: Jinja2 not installed. Run: pip install jinja2")


# =============================================================================
# LATEX TEMPLATE (Jake's Resume - embedded for portability)
# =============================================================================

RESUME_TEMPLATE = r"""
%-------------------------
% Resume in LaTeX
% Based on Jake's Resume Template
% License: MIT
%-------------------------

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
\input{glyphtounicode}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

% Adjust margins
\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}

\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

% Section formatting
\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

% Ensure PDF is machine readable
\pdfgentounicode=1

%-------------------------
% Custom commands
\newcommand{\resumeItem}[1]{
  \item\small{
    {#1 \vspace{-2pt}}
  }
}

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

\newcommand{\resumeSubItem}[1]{\resumeItem{#1}\vspace{-4pt}}

\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

%-------------------------------------------
%%%%%%  RESUME STARTS HERE  %%%%%%%%%%%%%%%%%%%%%%%%%%%%

\begin{document}

%----------HEADING----------
\begin{center}
    \textbf{\Huge \scshape <<contact.name|default('Your Name')>>} \\ \vspace{1pt}
    \small 
    <<contact.phone|default('')>>
    <<'$|$' if contact.phone and contact.email else ''>>
    \href{mailto:<<contact.email|default('')>>}{\underline{<<contact.email|default('')>>}}
    <<'$|$' if contact.email and contact.linkedin else ''>>
    <<'\\href{https://linkedin.com/in/' + contact.linkedin + '}{\\underline{linkedin.com/in/' + contact.linkedin + '}}' if contact.linkedin else ''>>
    <<'$|$' if contact.linkedin and contact.github else ''>>
    <<'\\href{https://github.com/' + contact.github + '}{\\underline{github.com/' + contact.github + '}}' if contact.github else ''>>
\end{center}

<<% for section in section_order %>>
<<% if section == 'education' and education %>>
%-----------EDUCATION-----------
\section{Education}
  \resumeSubHeadingListStart
    <<% for edu in education %>>
    \resumeSubheading
      {<<edu.school|escape_latex>>}{<<edu.dates|default('')|escape_latex>>}
      {<<edu.degree|escape_latex>>}{}
      <<% if edu.details %>>
      \resumeItemListStart
        <<% for detail in edu.details %>>
        \resumeItem{<<detail|escape_latex>>}
        <<% endfor %>>
      \resumeItemListEnd
      <<% endif %>>
    <<% endfor %>>
  \resumeSubHeadingListEnd
<<% endif %>>

<<% if section == 'experience' and experience %>>
%-----------EXPERIENCE-----------
\section{Experience}
  \resumeSubHeadingListStart
    <<% for exp in experience %>>
    \resumeSubheading
      {<<exp.title|escape_latex>>}{<<exp.dates|default('')|escape_latex>>}
      {<<exp.company|escape_latex>>}{<<exp.location|default('')|escape_latex>>}
      \resumeItemListStart
        <<% for bullet in exp.bullets %>>
        \resumeItem{<<bullet.text|escape_latex>>}
        <<% endfor %>>
      \resumeItemListEnd
    <<% endfor %>>
  \resumeSubHeadingListEnd
<<% endif %>>

<<% if section == 'projects' and projects %>>
%-----------PROJECTS-----------
\section{Projects}
    \resumeSubHeadingListStart
      <<% for proj in projects %>>
      \resumeProjectHeading
          {\textbf{<<proj.name|escape_latex>>} $|$ \emph{<<proj.description|escape_latex>>}}{}
          \resumeItemListStart
            <<% for bullet in proj.bullets %>>
            \resumeItem{<<bullet|escape_latex>>}
            <<% endfor %>>
          \resumeItemListEnd
      <<% endfor %>>
    \resumeSubHeadingListEnd
<<% endif %>>

<<% if section == 'skills' and skills %>>
%-----------SKILLS-----------
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Languages \& Tools}{: <<skills|join(', ')|escape_latex>>}
    }}
 \end{itemize}
<<% endif %>>
<<% endfor %>>

%-------------------------------------------
\end{document}
"""


# =============================================================================
# LATEX ESCAPING
# =============================================================================

def escape_latex(text: str) -> str:
    """
    Escape special LaTeX characters to prevent compilation errors.
    
    Args:
        text: Raw text string
        
    Returns:
        LaTeX-safe string
    """
    if not text:
        return ""
    
    # Order matters! Backslash must be first
    replacements = [
        ('\\', r'\textbackslash{}'),
        ('&', r'\&'),
        ('%', r'\%'),
        ('$', r'\$'),
        ('#', r'\#'),
        ('_', r'\_'),
        ('{', r'\{'),
        ('}', r'\}'),
        ('~', r'\textasciitilde{}'),
        ('^', r'\textasciicircum{}'),
    ]
    
    result = str(text)
    for old, new in replacements:
        result = result.replace(old, new)
    
    return result


# =============================================================================
# TEMPLATE RENDERING
# =============================================================================

def create_jinja_env() -> 'Environment':
    """Create Jinja2 environment with custom delimiters for LaTeX compatibility."""
    if not JINJA2_AVAILABLE:
        raise ImportError("Jinja2 is required. Install with: pip install jinja2")
    
    # Use << >> instead of {{ }} to avoid LaTeX conflicts
    env = Environment(
        loader=BaseLoader(),
        block_start_string='<<%',
        block_end_string='%>>',
        variable_start_string='<<',
        variable_end_string='>>',
        comment_start_string='<<#',
        comment_end_string='#>>',
        autoescape=False
    )
    
    # Add custom filter for LaTeX escaping
    env.filters['escape_latex'] = escape_latex
    
    return env


def render_resume(assembled_data: Dict[str, Any], template_str: str = None) -> str:
    """
    Render the assembled resume data into a LaTeX document.
    
    Args:
        assembled_data: Assembled resume dict from assembler.py
        template_str: Optional custom template string
        
    Returns:
        Complete LaTeX document as string
    """
    env = create_jinja_env()
    template = env.from_string(template_str or RESUME_TEMPLATE)
    
    # Render template with data
    latex_content = template.render(**assembled_data)
    
    return latex_content


# =============================================================================
# PDF COMPILATION
# =============================================================================

def compile_pdf(tex_content: str, output_path: str, keep_tex: bool = False) -> bool:
    """
    Compile LaTeX content to PDF using pdflatex.
    
    Args:
        tex_content: LaTeX document content
        output_path: Desired output PDF path
        keep_tex: Whether to keep the .tex file after compilation
        
    Returns:
        True if compilation succeeded, False otherwise
    """
    # Create temporary directory for compilation
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, 'resume.tex')
        
        # Write LaTeX content
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(tex_content)
        
        # Run pdflatex (twice for proper formatting)
        for _ in range(2):
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', '-output-directory', tmpdir, tex_path],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print("LaTeX compilation error:")
                print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
                return False
        
        # Move PDF to output location
        pdf_path = os.path.join(tmpdir, 'resume.pdf')
        if os.path.exists(pdf_path):
            # Ensure output directory exists
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            shutil.copy(pdf_path, output_path)
            
            # Optionally keep the .tex file
            if keep_tex:
                tex_output = output_path.replace('.pdf', '.tex')
                shutil.copy(tex_path, tex_output)
                print(f"LaTeX source saved to: {tex_output}")
            
            return True
        else:
            print("PDF file was not generated")
            return False


def check_pdflatex() -> bool:
    """Check if pdflatex is available on the system."""
    try:
        result = subprocess.run(['pdflatex', '--version'], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


# =============================================================================
# MAIN GENERATION FUNCTION
# =============================================================================

def generate(
    assembled_data: Dict[str, Any], 
    output_path: str,
    template_str: str = None,
    keep_tex: bool = False
) -> bool:
    """
    Main function - generate PDF resume from assembled data.
    
    Args:
        assembled_data: Assembled resume dict from assembler.py
        output_path: Output path for the PDF
        template_str: Optional custom LaTeX template
        keep_tex: Whether to keep the .tex source file
        
    Returns:
        True if generation succeeded, False otherwise
    """
    # Check for pdflatex
    if not check_pdflatex():
        print("Error: pdflatex not found. Install TeX Live:")
        print("  Ubuntu/Debian: sudo apt install texlive-latex-base texlive-fonts-recommended")
        print("  macOS: brew install --cask mactex")
        print("  Windows: Install MiKTeX from https://miktex.org/")
        
        # Fall back to saving just the .tex file
        print("\nFalling back to .tex output only...")
        tex_content = render_resume(assembled_data, template_str)
        tex_output = output_path.replace('.pdf', '.tex')
        with open(tex_output, 'w', encoding='utf-8') as f:
            f.write(tex_content)
        print(f"LaTeX source saved to: {tex_output}")
        print("You can compile it manually or use Overleaf.")
        return False
    
    print("Rendering LaTeX template...")
    tex_content = render_resume(assembled_data, template_str)
    
    print("Compiling PDF...")
    success = compile_pdf(tex_content, output_path, keep_tex)
    
    if success:
        print(f"✓ Resume generated: {output_path}")
    
    return success


def generate_tex_only(assembled_data: Dict[str, Any], output_path: str) -> str:
    """
    Generate only the .tex file without PDF compilation.
    Useful when pdflatex is not available.
    
    Args:
        assembled_data: Assembled resume dict from assembler.py
        output_path: Output path for the .tex file
        
    Returns:
        Path to the generated .tex file
    """
    tex_content = render_resume(assembled_data)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(tex_content)
    
    print(f"✓ LaTeX source saved: {output_path}")
    return output_path


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate a PDF resume from assembled data"
    )
    parser.add_argument(
        'assembled_json',
        help='Path to assembled resume JSON from assembler.py'
    )
    parser.add_argument(
        '-o', '--output',
        default='tailored_resume.pdf',
        help='Output path for the PDF (default: tailored_resume.pdf)'
    )
    parser.add_argument(
        '--tex-only',
        action='store_true',
        help='Generate only .tex file without PDF compilation'
    )
    parser.add_argument(
        '--keep-tex',
        action='store_true',
        help='Keep the .tex source file after PDF generation'
    )
    
    args = parser.parse_args()
    
    # Load assembled data
    print(f"Loading assembled data from: {args.assembled_json}")
    with open(args.assembled_json, 'r', encoding='utf-8') as f:
        assembled_data = json.load(f)
    
    if args.tex_only:
        tex_output = args.output.replace('.pdf', '.tex')
        generate_tex_only(assembled_data, tex_output)
    else:
        success = generate(assembled_data, args.output, keep_tex=args.keep_tex)
        
        if success:
            # Print gap report summary
            gap = assembled_data.get('gap_report', {})
            if gap.get('missing'):
                print(f"\n⚠️  Skills gap detected: {', '.join(gap['missing'])}")
            if gap.get('recommendations'):
                print("\n📋 Recommendations for improvement:")
                for rec in gap['recommendations'][:3]:
                    print(f"   • {rec}")
