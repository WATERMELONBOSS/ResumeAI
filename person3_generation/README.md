# Person 3: Resume Assembly & Generation

**Owner:** [Your Name]  
**CS 5100 - Foundations of AI**

## Overview

This module handles Stage 3 of the ResumeAI pipeline:
1. **Assembly** - Select best experiences/bullets based on Person 2's scores
2. **LaTeX Generation** - Produce professional PDF resumes
3. **Multi-JD Comparison** - Analyze bullets across multiple job descriptions

## Files

| File | Description |
|------|-------------|
| `assembler.py` | Core logic for selecting experiences and allocating bullets |
| `latex_generator.py` | Jinja2 templating + pdflatex PDF generation |
| `multi_jd_compare.py` | Compare resume against 10-15 JDs, generate heatmap |
| `pipeline.py` | **Full pipeline** - wire Stages 1, 2, 3 together (copy to repo root) |

## Installation

```bash
# Required packages
pip install jinja2 matplotlib seaborn pandas numpy

# For semantic similarity in multi_jd_compare (optional)
pip install sentence-transformers

# For PDF generation (system package)
# Ubuntu/Debian:
sudo apt install texlive-latex-base texlive-fonts-recommended texlive-latex-extra

# macOS:
brew install --cask mactex
```

## Usage

### Option 1: Standalone (with Person 2's output)

```bash
# Person 2's output doesn't include contact info, so pass original resume with -r
python assembler.py path/to/scored.json -r path/to/original_resume.json -o assembled.json

# Generate PDF from assembled resume
python latex_generator.py assembled.json -o tailored_resume.pdf
```

### Option 2: Full Pipeline (all 3 stages)

Copy `pipeline.py` to the repo root and run:

```bash
python pipeline.py --resume data/sample_resumes/milan.pdf --jd data/sample_jds/jd1.txt --output results/
```

This runs all 3 stages and outputs:
- `parsed_resume.json` (Stage 1)
- `parsed_jd.json` (Stage 1)  
- `scored_resume.json` (Stage 2)
- `assembled_resume.json` (Stage 3)
- `tailored_resume.pdf` (Stage 3)

### Multi-JD Comparison

```bash
python multi_jd_compare.py path/to/resume.json path/to/jd_folder/ -o comparison_output/
```

## Key Thresholds

| Threshold | Value | Description |
|-----------|-------|-------------|
| `MIN_EXPERIENCE_AVG_SCORE` | 0.25 | Cut entire experience if avg score below this |
| `BULLET_SCORE_THRESHOLD` | 0.35 | Only include bullets above this score |
| `MAX_EXPERIENCES` | 3 | Maximum experiences in tailored resume |
| `BULLET_ALLOCATION` | [4, 3, 2] | Max bullets for rank 1, 2, 3 experiences |

*Note: Thresholds adjusted based on Person 2's actual score distributions (overall ~0.46)*

## Integration with Person 2

**Important:** Person 2's `scored_resume.json` does NOT include contact info.

Two ways to handle this:

1. **Pass original resume** (recommended):
   ```bash
   python assembler.py scored.json -r original_resume.json -o assembled.json
   ```

2. **Use full pipeline** (handles automatically):
   ```bash
   python pipeline.py --resume resume.pdf --jd jd.txt
   ```

## JSON Contracts

### Input: Scored Resume JSON (from Person 2)

```json
{
  "scored_sections": {
    "experience": [{
      "company": "...",
      "title": "...",
      "dates": "...",
      "location": "...",
      "section_weight": 1.5,
      "avg_relevance": 0.52,
      "bullets": [{
        "text": "...",
        "semantic_score": 0.70,
        "keyword_score": 0.37,
        "best_match_requirement": "..."
      }]
    }],
    "projects": [...],
    "education": [...],
    "skills": [...]
  },
  "skills_analysis": {
    "covered": ["JavaScript", "React"],
    "missing": ["Angular"],
    "partial_match": []
  },
  "overall_semantic_score": 0.46,
  "overall_keyword_score": 0.08
}
```

### Output: Assembled Resume JSON

```json
{
  "contact": {"name": "...", "email": "...", "phone": "..."},
  "section_order": ["experience", "projects", "skills", "education"],
  "experience": [{
    "company": "...",
    "bullets": [{"text": "...", "semantic_score": 0.70}]
  }],
  "skills": ["JavaScript", "React", "Git"],
  "gap_report": {
    "missing": ["Angular"],
    "recommendations": [...]
  }
}
```

## For the Paper

The multi-JD comparison generates:
- `jd_comparison_heatmap.png` - Visual for Results section
- `classification_summary.png` - Bar chart of bullet classifications
- `comparison_report.json` - Raw data for analysis

These outputs directly support the **Evaluation** section requirements.
