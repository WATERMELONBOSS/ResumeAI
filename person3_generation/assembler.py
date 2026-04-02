"""
assembler.py
------------
Stage 3 — Resume Assembly Logic.

Takes the scored JSON from Person 2 and applies the structural decision rules
defined in the project action plan:

  1. Experience Selection  — cut entries with avg_relevance < 0.3
  2. Bullet Allocation     — top entry gets 4 bullets, 2nd gets 3, 3rd gets 2;
                             only bullets with semantic_score >= 0.45 qualify
  3. Section Ordering      — driven by section_weight; Experience first for most
                             SWE roles
  4. Skills Curation       — JD-matched skills first, then remaining resume skills
  5. Gap Report            — missing + partial_match skills with actionable notes

Public API:
    from person3_generation.assembler import assemble_resume
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS (tuned per action plan thresholds)
# ─────────────────────────────────────────────────────────────────────────────

EXPERIENCE_CUT_THRESHOLD: float = 0.25  # avg_relevance below this → cut entry
BULLET_SCORE_THRESHOLD: float = 0.30  # semantic_score below this → skip bullet

# Max bullets per experience rank (index 0 = most relevant entry)
BULLETS_BY_RANK: list[int] = [4, 3, 2, 1]


# ─────────────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def _select_and_trim_experiences(
    scored_experience: list[dict],
) -> list[dict]:
    """
    1. Filter out entries with avg_relevance < EXPERIENCE_CUT_THRESHOLD.
    2. Sort survivors by avg_relevance descending.
    3. For each entry, keep only the top-N bullets (by semantic_score)
       that are also above BULLET_SCORE_THRESHOLD.
       If no bullets pass the threshold, take the top-1 so the entry
       is never empty.
    """
    # Keep entries above threshold; retain at least the top-2 even if all are low
    eligible = [
        e
        for e in scored_experience
        if e.get("avg_relevance", 0.0) >= EXPERIENCE_CUT_THRESHOLD
    ]

    if not eligible:
        # Fallback: take top-2 by avg_relevance so the resume isn't empty
        eligible = sorted(
            scored_experience, key=lambda e: e.get("avg_relevance", 0.0), reverse=True
        )[:2]
        log.warning(
            "No experience entries passed threshold %.2f — using top-2 fallback",
            EXPERIENCE_CUT_THRESHOLD,
        )

    eligible.sort(key=lambda e: e.get("avg_relevance", 0.0), reverse=True)

    assembled: list[dict] = []
    for rank, entry in enumerate(eligible):
        max_bullets = BULLETS_BY_RANK[rank] if rank < len(BULLETS_BY_RANK) else 1

        # Sort bullets by semantic_score descending
        sorted_bullets = sorted(
            entry.get("bullets", []),
            key=lambda b: b.get("semantic_score", 0.0),
            reverse=True,
        )

        # Keep bullets above threshold, up to max_bullets
        passing = [
            b
            for b in sorted_bullets
            if b.get("semantic_score", 0.0) >= BULLET_SCORE_THRESHOLD
        ]

        if not passing:
            # Take top-1 regardless of score so entry has at least one bullet
            passing = sorted_bullets[:1]

        selected_bullets = passing[:max_bullets]

        assembled_entry = {
            "company": entry.get("company", ""),
            "title": entry.get("title", ""),
            "dates": entry.get("dates", ""),
            "location": entry.get("location", ""),
            "bullets": [b["text"] for b in selected_bullets],
            "avg_relevance": entry.get("avg_relevance", 0.0),
            "section_weight": entry.get("section_weight", 1.0),
        }
        assembled.append(assembled_entry)
        log.info(
            "Experience entry '%s' @ '%s': rank=%d, avg=%.3f, bullets=%d/%d",
            entry.get("title", "?"),
            entry.get("company", "?"),
            rank,
            entry.get("avg_relevance", 0.0),
            len(selected_bullets),
            len(sorted_bullets),
        )

    return assembled


def _select_and_trim_projects(
    scored_projects: list[dict],
    max_projects: int = 2,
) -> list[dict]:
    """
    Sort projects by avg_relevance, keep top max_projects.
    For each, keep top-3 bullets above threshold (or top-1 fallback).
    """
    sorted_projects = sorted(
        scored_projects,
        key=lambda p: p.get("avg_relevance", 0.0),
        reverse=True,
    )

    assembled: list[dict] = []
    for proj in sorted_projects[:max_projects]:
        sorted_bullets = sorted(
            proj.get("bullets", []),
            key=lambda b: b.get("semantic_score", 0.0),
            reverse=True,
        )
        passing = [
            b
            for b in sorted_bullets
            if b.get("semantic_score", 0.0) >= BULLET_SCORE_THRESHOLD
        ]
        if not passing:
            passing = sorted_bullets[:1]

        assembled.append(
            {
                "name": proj.get("name", ""),
                "description": proj.get("description", ""),
                "bullets": [b["text"] for b in passing[:3]],
                "avg_relevance": proj.get("avg_relevance", 0.0),
            }
        )

    return assembled


def _curate_skills(
    resume_skills: list[str],
    skills_analysis: dict,
) -> list[str]:
    """
    Return a curated skill list with JD-matched skills first.

    Order:
      1. Covered skills (present in resume AND required/preferred by JD)
      2. Remaining resume skills (not mentioned in JD but still valid)
    """
    covered_lower = {s.lower() for s in skills_analysis.get("covered", [])}
    resume_skills_lower_map = {s.lower(): s for s in resume_skills}

    # JD-matched skills first (preserve original casing from resume)
    jd_matched: list[str] = []
    remaining: list[str] = []

    for skill in resume_skills:
        if skill.lower() in covered_lower:
            jd_matched.append(skill)
        else:
            remaining.append(skill)

    return jd_matched + remaining


def _build_gap_report(skills_analysis: dict, jd: dict) -> dict:
    """
    Produce the actionable gap report that goes alongside (not inside) the resume.

    Returns:
        {
          "missing_skills":  [str],
          "partial_matches": [{"jd_skill": str, "closest_bullet": str,
                               "similarity": float, "note": str}],
          "jd_title":        str,
          "jd_company":      str,
          "recommendation":  str
        }
    """
    missing = skills_analysis.get("missing", [])
    partial = skills_analysis.get("partial_match", [])

    lines: list[str] = []
    if missing:
        lines.append(
            f"Missing skills ({len(missing)}): add these to your resume if you have them: {', '.join(missing)}."
        )
    if partial:
        lines.append(
            f"Partial matches ({len(partial)}): you likely have these but need clearer wording — "
            + "; ".join(f'"{p["jd_skill"]}"' for p in partial)
            + "."
        )
    if not missing and not partial:
        lines.append(
            "Your resume covers all detected required and preferred skills for this role."
        )

    return {
        "missing_skills": missing,
        "partial_matches": partial,
        "jd_title": jd.get("title", ""),
        "jd_company": jd.get("company", ""),
        "recommendation": " ".join(lines),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────


def assemble_resume(scored_output: dict, jd: dict) -> dict:
    """
    Convert Person 2's scored JSON into an assembled resume dict ready for
    LaTeX/PDF generation.

    Args:
        scored_output: The full dict returned by person2_scoring.scorer.score_resume().
        jd:            The parsed JD dict from person1_parsing.jd_parser.parse_jd().

    Returns:
        {
          "contact":          dict  (pass-through from original resume if available),
          "experience":       [assembled experience entries],
          "projects":         [assembled project entries],
          "education":        [education entries — pass-through],
          "skills":           [curated skill list],
          "gap_report":       dict,
          "overall_scores":   {"semantic": float, "keyword": float},
          "jd_meta":          {"title": str, "company": str}
        }
    """
    scored_sections = scored_output.get("scored_sections", {})
    skills_analysis = scored_output.get(
        "skills_analysis", {"covered": [], "missing": [], "partial_match": []}
    )

    experience = _select_and_trim_experiences(scored_sections.get("experience", []))
    projects = _select_and_trim_projects(scored_sections.get("projects", []))
    education = scored_sections.get("education", [])
    raw_skills = scored_sections.get("skills", [])
    curated_skills = _curate_skills(raw_skills, skills_analysis)
    gap_report = _build_gap_report(skills_analysis, jd)

    assembled = {
        "contact": scored_output.get("contact", {}),
        "experience": experience,
        "projects": projects,
        "education": education,
        "skills": curated_skills,
        "gap_report": gap_report,
        "overall_scores": {
            "semantic": scored_output.get("overall_semantic_score", 0.0),
            "keyword": scored_output.get("overall_keyword_score", 0.0),
        },
        "jd_meta": {
            "title": jd.get("title", ""),
            "company": jd.get("company", ""),
        },
    }

    log.info(
        "Assembly complete: %d experiences, %d projects, %d skills; "
        "missing=%d, partial=%d",
        len(experience),
        len(projects),
        len(curated_skills),
        len(gap_report["missing_skills"]),
        len(gap_report["partial_matches"]),
    )

    return assembled
