"""
example_usage.py — ResumeAI · Person 1: Parsing Layer
Demonstrates how to use ResumeParser and JDParser independently.

Run:
    # Parse a real PDF resume
    python test_cmdParser.py --resume ../data/sample_resumes/yourresume.pdf

    # Parse a JD file
    python test_cmdParser.py --jd ../data/sample_jds/yourjd.txt

    # Run offline demo with inline sample data (no files needed)
    python test_cmdParser.py --demo
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap

# ── make sibling modules importable when run from repo root ──────────────────
sys.path.insert(0, os.path.dirname(__file__))

from jd_parser import JDParser
from resume_parser import ResumeParser

# ─────────────────────────────────────────────────────────────────────────────
# Inline sample JD  (used by --demo mode; no file I/O required)
# ─────────────────────────────────────────────────────────────────────────────

SAMPLE_JD = textwrap.dedent(
    """\
    Backend Software Engineer
    Amazon

    About the Role
    We are looking for a Backend Software Engineer to join our Payments
    Infrastructure team. You will build and maintain scalable backend services
    handling millions of requests per day.

    Requirements
    - 3+ years of experience in backend software development
    - Strong proficiency in Python and familiarity with at least one other language
    - Experience designing and consuming REST APIs in production environments
    - Hands-on experience with AWS services such as EC2, S3, Lambda, and RDS
    - PostgreSQL experience required; must be comfortable writing complex queries
    - Experience with containerisation using Docker is required
    - Collaborate with cross-functional teams including product, design, and data

    Preferred
    - Knowledge of Kubernetes or container orchestration is a plus
    - Familiarity with CI/CD pipelines (GitHub Actions, Jenkins) preferred
    - Experience with event-driven architectures and Kafka is a nice-to-have
    - Infrastructure-as-code experience with Terraform is a bonus
    """
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _print_json(label: str, data: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print("=" * 60)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def parse_resume(path: str) -> None:
    print(f"\n[ResumeParser] Parsing: {path}")
    parser = ResumeParser()
    result = parser.parse(path)
    _print_json("RESUME JSON OUTPUT", result)


def parse_jd(source: str) -> None:
    print(f"\n[JDParser] Parsing JD source (length={len(source)} chars)")
    parser = JDParser()
    result = parser.parse(source)
    _print_json("JD JSON OUTPUT", result)


def run_demo() -> None:
    """Offline demo: parse the built-in sample JD string."""
    print("\n" + "=" * 60)
    print("  DEMO MODE — no external files required")
    print("  Parsing inline sample JD string …")
    print("=" * 60)

    jd_parser = JDParser()
    jd_result = jd_parser.parse(SAMPLE_JD)
    _print_json("JD JSON OUTPUT (demo)", jd_result)

    print(
        "\n[INFO] To parse a real PDF resume, run:\n"
        "       python example_usage.py --resume path/to/resume.pdf\n"
        "\n[INFO] To parse a JD text file, run:\n"
        "       python example_usage.py --jd path/to/jd.txt"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Validation helpers (lightweight contract check)
# ─────────────────────────────────────────────────────────────────────────────


def _validate_resume_json(data: dict) -> None:
    """Assert the output matches the agreed Resume JSON contract."""
    assert "contact" in data, "Missing key: contact"
    assert "name" in data["contact"], "Missing key: contact.name"
    assert "email" in data["contact"], "Missing key: contact.email"
    assert "phone" in data["contact"], "Missing key: contact.phone"

    assert "sections" in data, "Missing key: sections"
    secs = data["sections"]
    for key in ("experience", "education", "skills", "projects"):
        assert key in secs, f"Missing section: sections.{key}"

    assert "all_skills_detected" in data, "Missing key: all_skills_detected"
    assert isinstance(data["all_skills_detected"], list)

    if secs["experience"]:
        exp = secs["experience"][0]
        for field in ("company", "title", "dates", "location", "bullets"):
            assert field in exp, f"Missing field in experience entry: {field}"

    print("\n[VALIDATION] Resume JSON structure: ✓ All contract keys present")


def _validate_jd_json(data: dict) -> None:
    """Assert the output matches the agreed JD JSON contract."""
    assert "title" in data, "Missing key: title"
    assert "company" in data, "Missing key: company"
    assert "requirements" in data, "Missing key: requirements"
    req = data["requirements"]
    for key in ("required_skills", "preferred_skills", "experience_years", "requirement_sentences"):
        assert key in req, f"Missing key: requirements.{key}"
    assert "raw_text" in data, "Missing key: raw_text"

    if req["requirement_sentences"]:
        sent = req["requirement_sentences"][0]
        assert "text" in sent, "Missing field in requirement_sentences: text"
        assert "type" in sent, "Missing field in requirement_sentences: type"
        assert sent["type"] in ("required", "preferred"), (
            f"Invalid type value: {sent['type']}"
        )

    print("[VALIDATION] JD JSON structure:     ✓ All contract keys present")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description="ResumeAI Person 1 — Parsing Layer demo"
    )
    ap.add_argument("--resume", metavar="PDF_PATH", help="Path to a resume PDF")
    ap.add_argument(
        "--jd",
        metavar="JD_PATH_OR_TEXT",
        help="Path to a JD text file, or inline JD text",
    )
    ap.add_argument(
        "--demo",
        action="store_true",
        help="Run offline demo with built-in sample data",
    )
    ap.add_argument(
        "--validate",
        action="store_true",
        help="Validate output structure against JSON contract",
    )
    args = ap.parse_args()

    if args.demo or (not args.resume and not args.jd):
        run_demo()
        if args.validate:
            jd_parser = JDParser()
            jd_result = jd_parser.parse(SAMPLE_JD)
            _validate_jd_json(jd_result)
        return

    if args.resume:
        parse_resume(args.resume)
        if args.validate:
            parser = ResumeParser()
            result = parser.parse(args.resume)
            _validate_resume_json(result)

    if args.jd:
        parse_jd(args.jd)
        if args.validate:
            jd_parser = JDParser()
            jd_result = jd_parser.parse(args.jd)
            _validate_jd_json(jd_result)


if __name__ == "__main__":
    main()
