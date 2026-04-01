"""
assembler.py - Resume Assembly Logic
Person 3 - ResumeAI Project

Takes the scored resume JSON from Person 2 and makes structural decisions:
- Which experiences to include (cut if avg_relevance < 0.3)
- How many bullets per experience (top: 3-4, second: 2-3, third: 1-2)
- Section ordering based on weights
- Skills curation (only JD-relevant skills)
- Gap report generation

Author: [Your Name]
CS 5100 - Foundations of AI
"""

import json
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass


# =============================================================================
# CONFIGURATION - Thresholds from project spec
# Adjusted based on Person 2's actual score distributions
# =============================================================================

MIN_EXPERIENCE_AVG_SCORE = 0.25   # Cut entire experience if avg below this
BULLET_SCORE_THRESHOLD = 0.35     # Only include bullets scoring above this
MAX_EXPERIENCES = 3               # Maximum experiences to include
BULLET_ALLOCATION = [4, 3, 2]     # Max bullets for rank 1, 2, 3 experiences


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class GapReport:
    """Skills gap analysis for user feedback."""
    covered_skills: List[str]
    missing_skills: List[str]
    partial_matches: List[Dict[str, Any]]
    recommendations: List[str]


# =============================================================================
# CORE ASSEMBLY FUNCTIONS
# =============================================================================

def load_scored_data(filepath: str) -> Dict[str, Any]:
    """
    Load the scored resume JSON from Person 2.
    
    Args:
        filepath: Path to the scored JSON file
        
    Returns:
        Dictionary containing scored resume data
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def select_experiences(
    scored_experiences: List[Dict[str, Any]], 
    min_avg_score: float = MIN_EXPERIENCE_AVG_SCORE,
    max_experiences: int = MAX_EXPERIENCES
) -> List[Dict[str, Any]]:
    """
    Select which experiences to include based on relevance scores.
    
    Experiences with avg_relevance below the threshold are cut entirely.
    Returns top N experiences sorted by average relevance.
    
    Args:
        scored_experiences: List of experience dicts with scores from Person 2
        min_avg_score: Minimum average score to include an experience
        max_experiences: Maximum number of experiences to return
        
    Returns:
        Filtered and sorted list of experiences
    """
    # Filter out experiences below the threshold
    qualified = [
        exp for exp in scored_experiences 
        if exp.get('avg_relevance', 0) >= min_avg_score
    ]
    
    # Sort by average relevance (highest first)
    qualified.sort(key=lambda x: x.get('avg_relevance', 0), reverse=True)
    
    # Return top N
    return qualified[:max_experiences]


def allocate_bullets(
    experience: Dict[str, Any],
    rank: int,
    threshold: float = BULLET_SCORE_THRESHOLD,
    allocation: List[int] = None
) -> List[Dict[str, Any]]:
    """
    Select bullets for a single experience based on rank and scores.
    
    The most relevant experience gets more bullets (3-4), second gets 2-3, etc.
    Only bullets above the score threshold are considered.
    
    Args:
        experience: Experience dict containing scored bullets
        rank: 0-indexed rank of this experience (0 = most relevant)
        threshold: Minimum semantic score to include a bullet
        allocation: List of max bullets per rank [rank0, rank1, rank2, ...]
        
    Returns:
        List of selected bullet dicts
    """
    if allocation is None:
        allocation = BULLET_ALLOCATION
        
    bullets = experience.get('bullets', [])
    
    # Filter bullets above threshold
    qualified_bullets = [
        b for b in bullets 
        if b.get('semantic_score', 0) >= threshold
    ]
    
    # Sort by semantic score (highest first)
    qualified_bullets.sort(key=lambda x: x.get('semantic_score', 0), reverse=True)
    
    # Get max bullets for this rank
    max_bullets = allocation[rank] if rank < len(allocation) else allocation[-1]
    
    return qualified_bullets[:max_bullets]


def order_sections(
    sections: Dict[str, Any], 
    section_weights: Dict[str, float]
) -> List[Tuple[str, Any]]:
    """
    Order resume sections based on weights from Person 2's analysis.
    
    Higher weighted sections appear first (after contact info).
    
    Args:
        sections: Dict of section_name -> section_data
        section_weights: Dict of section_name -> weight score
        
    Returns:
        List of (section_name, section_data) tuples in order
    """
    # Default weights if not provided
    default_weights = {
        'experience': 1.5,
        'projects': 1.2,
        'skills': 1.0,
        'education': 0.8
    }
    
    # Merge with defaults
    weights = {**default_weights, **section_weights}
    
    # Sort sections by weight
    ordered = sorted(
        sections.items(),
        key=lambda x: weights.get(x[0], 0.5),
        reverse=True
    )
    
    return ordered


def curate_skills(
    resume_skills: List[str],
    jd_required: List[str],
    jd_preferred: List[str],
    covered: List[str]
) -> List[str]:
    """
    Curate the skills section to prioritize JD-relevant skills.
    
    Order: Required matches first, then preferred matches, then other relevant skills.
    
    Args:
        resume_skills: All skills from the master resume
        jd_required: Required skills from JD
        jd_preferred: Preferred skills from JD  
        covered: Skills marked as covered by Person 2's analysis
        
    Returns:
        Ordered list of skills for the tailored resume
    """
    # Normalize for comparison
    resume_lower = {s.lower(): s for s in resume_skills}
    required_lower = {s.lower() for s in jd_required}
    preferred_lower = {s.lower() for s in jd_preferred}
    covered_lower = {s.lower() for s in covered}
    
    curated = []
    
    # First: Required skills that we have
    for skill_lower, skill in resume_lower.items():
        if skill_lower in required_lower:
            curated.append(skill)
    
    # Second: Preferred skills that we have
    for skill_lower, skill in resume_lower.items():
        if skill_lower in preferred_lower and skill not in curated:
            curated.append(skill)
    
    # Third: Other covered skills
    for skill_lower, skill in resume_lower.items():
        if skill_lower in covered_lower and skill not in curated:
            curated.append(skill)
    
    return curated


def generate_gap_report(skills_analysis: Dict[str, Any]) -> GapReport:
    """
    Generate actionable gap report from Person 2's skills analysis.
    
    Args:
        skills_analysis: Dict with covered, missing, partial_match from Person 2
        
    Returns:
        GapReport with recommendations
    """
    covered = skills_analysis.get('covered', [])
    missing = skills_analysis.get('missing', [])
    partial = skills_analysis.get('partial_match', [])
    
    recommendations = []
    
    # Generate recommendations for missing skills
    for skill in missing:
        recommendations.append(
            f"MISSING: '{skill}' - Consider adding relevant experience or coursework"
        )
    
    # Generate recommendations for partial matches
    for match in partial:
        jd_skill = match.get('jd_skill', '')
        closest = match.get('closest_bullet', '')
        similarity = match.get('similarity', 0)
        
        if similarity >= 0.4:
            recommendations.append(
                f"REWORD: Your bullet about '{closest[:50]}...' partially matches "
                f"'{jd_skill}' (similarity: {similarity:.0%}). "
                f"Consider rewording to include the keyword."
            )
    
    return GapReport(
        covered_skills=covered,
        missing_skills=missing,
        partial_matches=partial,
        recommendations=recommendations
    )


# =============================================================================
# MAIN ASSEMBLY FUNCTION
# =============================================================================

def assemble(
    scored_data: Dict[str, Any], 
    jd_data: Optional[Dict[str, Any]] = None,
    original_resume: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main assembly function - orchestrates the entire resume tailoring process.
    
    Takes Person 2's scored output and produces an assembled resume structure
    ready for LaTeX generation.
    
    Args:
        scored_data: Complete scored JSON from Person 2
        jd_data: Optional JD data for skills curation (if not embedded in scored_data)
        original_resume: Optional original resume JSON from Person 1 (for contact info)
        
    Returns:
        Assembled resume dict ready for latex_generator.py
    """
    scored_sections = scored_data.get('scored_sections', {})
    
    # Get contact info - Person 2's output doesn't include it, so get from original resume
    contact = scored_data.get('contact')
    if not contact and original_resume:
        contact = original_resume.get('contact', {})
    if not contact:
        contact = {'name': '', 'email': '', 'phone': ''}
    skills_analysis = scored_data.get('skills_analysis', {})
    
    # -------------------------------------------------------------------------
    # 1. SELECT AND PROCESS EXPERIENCES
    # -------------------------------------------------------------------------
    scored_experiences = scored_sections.get('experience', [])
    selected_experiences = select_experiences(scored_experiences)
    
    assembled_experiences = []
    for rank, exp in enumerate(selected_experiences):
        # Allocate bullets based on rank
        selected_bullets = allocate_bullets(exp, rank)
        
        # Skip experiences with no bullets above threshold
        if not selected_bullets:
            continue
        
        assembled_exp = {
            'company': exp.get('company', ''),
            'title': exp.get('title', ''),
            'dates': exp.get('dates', ''),
            'location': exp.get('location', ''),
            'bullets': [
                {
                    'text': b.get('text', ''),
                    'semantic_score': b.get('semantic_score', 0),
                    'best_match': b.get('best_match_requirement')
                }
                for b in selected_bullets
            ]
        }
        assembled_experiences.append(assembled_exp)
    
    # -------------------------------------------------------------------------
    # 2. PROCESS EDUCATION (keep all, usually not filtered)
    # -------------------------------------------------------------------------
    education = scored_sections.get('education', [])
    assembled_education = []
    for edu in education:
        assembled_education.append({
            'school': edu.get('school', ''),
            'degree': edu.get('degree', ''),
            'dates': edu.get('dates', ''),
            'details': edu.get('details', [])
        })
    
    # -------------------------------------------------------------------------
    # 3. PROCESS PROJECTS (similar to experiences but usually keep more)
    # -------------------------------------------------------------------------
    scored_projects = scored_sections.get('projects', [])
    assembled_projects = []
    
    # Sort projects by avg relevance if available
    sorted_projects = sorted(
        scored_projects,
        key=lambda x: x.get('avg_relevance', 0.5),
        reverse=True
    )[:3]  # Keep top 3 projects
    
    for proj in sorted_projects:
        bullets = proj.get('bullets', [])
        # Filter and sort bullets if they have scores
        if bullets and isinstance(bullets[0], dict):
            qualified_bullets = sorted(
                [b for b in bullets if b.get('semantic_score', 0.5) >= BULLET_SCORE_THRESHOLD],
                key=lambda x: x.get('semantic_score', 0),
                reverse=True
            )[:3]
            bullet_texts = [b.get('text', '') for b in qualified_bullets]
        else:
            # Bullets are plain strings
            bullet_texts = bullets[:3]
        
        # Skip projects with no qualifying bullets
        if not bullet_texts:
            continue
        
        assembled_projects.append({
            'name': proj.get('name', ''),
            'description': proj.get('description', ''),
            'bullets': bullet_texts
        })
    
    # -------------------------------------------------------------------------
    # 4. CURATE SKILLS
    # -------------------------------------------------------------------------
    resume_skills = scored_sections.get('skills', [])
    
    # Get JD skills if available
    jd_required = []
    jd_preferred = []
    if jd_data:
        requirements = jd_data.get('requirements', {})
        jd_required = requirements.get('required_skills', [])
        jd_preferred = requirements.get('preferred_skills', [])
    
    covered_skills = skills_analysis.get('covered', [])
    
    curated_skills = curate_skills(
        resume_skills, 
        jd_required, 
        jd_preferred,
        covered_skills
    )
    
    # If no JD data, just use the original skills
    if not curated_skills:
        curated_skills = resume_skills
    
    # -------------------------------------------------------------------------
    # 5. DETERMINE SECTION ORDER
    # -------------------------------------------------------------------------
    # Extract section weights from experiences (Person 2 provides these)
    section_weights = {}
    if selected_experiences:
        section_weights['experience'] = selected_experiences[0].get('section_weight', 1.5)
    
    # Default ordering based on typical importance
    section_order = ['experience', 'projects', 'skills', 'education']
    
    # -------------------------------------------------------------------------
    # 6. GENERATE GAP REPORT
    # -------------------------------------------------------------------------
    gap_report = generate_gap_report(skills_analysis)
    
    # -------------------------------------------------------------------------
    # 7. COMPILE FINAL ASSEMBLED RESUME
    # -------------------------------------------------------------------------
    assembled_resume = {
        'contact': contact,
        'section_order': section_order,
        'experience': assembled_experiences,
        'education': assembled_education,
        'projects': assembled_projects,
        'skills': curated_skills,
        'metadata': {
            'overall_semantic_score': scored_data.get('overall_semantic_score', 0),
            'overall_keyword_score': scored_data.get('overall_keyword_score', 0),
            'experiences_included': len(assembled_experiences),
            'total_bullets': sum(len(e['bullets']) for e in assembled_experiences)
        },
        'gap_report': {
            'covered': gap_report.covered_skills,
            'missing': gap_report.missing_skills,
            'partial_matches': gap_report.partial_matches,
            'recommendations': gap_report.recommendations
        }
    }
    
    return assembled_resume


def save_assembled(assembled_data: Dict[str, Any], output_path: str) -> None:
    """Save assembled resume to JSON file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(assembled_data, f, indent=2, ensure_ascii=False)
    print(f"Assembled resume saved to: {output_path}")


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Assemble a tailored resume from scored data"
    )
    parser.add_argument(
        'scored_json',
        help='Path to scored resume JSON from Person 2'
    )
    parser.add_argument(
        '-o', '--output',
        default='assembled_resume.json',
        help='Output path for assembled resume JSON'
    )
    parser.add_argument(
        '-j', '--jd',
        help='Optional: Path to JD JSON for skills curation'
    )
    parser.add_argument(
        '-r', '--resume',
        help='Optional: Path to original resume JSON from Person 1 (for contact info)'
    )
    
    args = parser.parse_args()
    
    # Load scored data
    print(f"Loading scored data from: {args.scored_json}")
    scored_data = load_scored_data(args.scored_json)
    
    # Load JD if provided
    jd_data = None
    if args.jd:
        print(f"Loading JD data from: {args.jd}")
        with open(args.jd, 'r') as f:
            jd_data = json.load(f)
    
    # Load original resume if provided (for contact info)
    original_resume = None
    if args.resume:
        print(f"Loading original resume from: {args.resume}")
        with open(args.resume, 'r') as f:
            original_resume = json.load(f)
    
    # Assemble
    print("Assembling tailored resume...")
    assembled = assemble(scored_data, jd_data, original_resume)
    
    # Save
    save_assembled(assembled, args.output)
    
    # Print summary
    print("\n" + "="*50)
    print("ASSEMBLY SUMMARY")
    print("="*50)
    print(f"Contact: {assembled['contact'].get('name', 'N/A')}")
    print(f"Experiences included: {assembled['metadata']['experiences_included']}")
    print(f"Total bullets: {assembled['metadata']['total_bullets']}")
    print(f"Skills included: {len(assembled['skills'])}")
    print(f"Overall match score: {assembled['metadata']['overall_semantic_score']:.0%}")
    
    if assembled['gap_report']['missing']:
        print(f"\n⚠️  Missing skills: {', '.join(assembled['gap_report']['missing'])}")
    
    if assembled['gap_report']['recommendations']:
        print("\n📋 Recommendations:")
        for rec in assembled['gap_report']['recommendations'][:3]:
            print(f"   • {rec}")
