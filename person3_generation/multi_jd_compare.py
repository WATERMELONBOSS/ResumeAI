"""
multi_jd_compare.py - Multi-JD Resume Comparison
Person 3 - ResumeAI Project

Compares one master resume against multiple job descriptions to identify:
- Universal bullets: Strong across most JDs (keep on every resume version)
- Role-specific bullets: High for certain roles (tailoring levers)
- Weak bullets: Low across all JDs (consider removing/rewriting)

Outputs a heatmap visualization for the paper and actionable insights.

Author: [Your Name]
CS 5100 - Foundations of AI
"""

import os
import json
import numpy as np
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from pathlib import Path

# Optional visualization imports
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    import pandas as pd
    VIZ_AVAILABLE = True
except ImportError:
    VIZ_AVAILABLE = False
    print("Warning: matplotlib/seaborn not installed. Heatmap generation disabled.")
    print("Install with: pip install matplotlib seaborn pandas")


# =============================================================================
# CONFIGURATION
# =============================================================================

UNIVERSAL_THRESHOLD = 0.6      # Avg score above this = universal bullet
ROLE_SPECIFIC_STD = 0.25       # Std dev above this = role-specific
ROLE_SPECIFIC_MAX = 0.7        # Must have at least one score above this
WEAK_THRESHOLD = 0.35          # Avg score below this = weak bullet


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BulletAnalysis:
    """Analysis result for a single bullet point."""
    text: str
    scores: List[float]          # Score for each JD
    avg_score: float
    std_score: float
    max_score: float
    min_score: float
    classification: str          # 'universal', 'role_specific', or 'weak'
    best_jd_index: int           # Index of JD where this bullet scores highest
    

@dataclass
class ComparisonResult:
    """Complete comparison result."""
    bullets: List[BulletAnalysis]
    jd_names: List[str]
    score_matrix: np.ndarray     # rows = bullets, cols = JDs
    universal_count: int
    role_specific_count: int
    weak_count: int


# =============================================================================
# SCORING FUNCTIONS
# =============================================================================

def load_jds(jd_folder: str) -> List[Dict[str, Any]]:
    """
    Load all JD JSON files from a directory.
    
    Args:
        jd_folder: Path to folder containing JD JSON files
        
    Returns:
        List of JD dictionaries
    """
    jds = []
    jd_path = Path(jd_folder)
    
    for json_file in sorted(jd_path.glob('*.json')):
        with open(json_file, 'r', encoding='utf-8') as f:
            jd = json.load(f)
            jd['_filename'] = json_file.stem  # Store filename for reference
            jds.append(jd)
    
    print(f"Loaded {len(jds)} job descriptions")
    return jds


def extract_bullets_from_resume(resume_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all bullet points from resume data.
    
    Args:
        resume_data: Parsed resume JSON from Person 1
        
    Returns:
        List of bullet dicts with text and source info
    """
    bullets = []
    sections = resume_data.get('sections', {})
    
    # Extract from experience
    for exp in sections.get('experience', []):
        company = exp.get('company', 'Unknown')
        for bullet_text in exp.get('bullets', []):
            bullets.append({
                'text': bullet_text,
                'source': f"Experience: {company}",
                'type': 'experience'
            })
    
    # Extract from projects
    for proj in sections.get('projects', []):
        name = proj.get('name', 'Unknown')
        for bullet_text in proj.get('bullets', []):
            bullets.append({
                'text': bullet_text,
                'source': f"Project: {name}",
                'type': 'project'
            })
    
    return bullets


def compute_similarity_simple(bullet_text: str, jd_data: Dict[str, Any]) -> float:
    """
    Simple keyword-based similarity (fallback when sentence-transformers unavailable).
    
    Uses Jaccard similarity between bullet words and JD keywords.
    
    Args:
        bullet_text: The bullet point text
        jd_data: JD dictionary with requirements
        
    Returns:
        Similarity score between 0 and 1
    """
    # Extract JD keywords
    requirements = jd_data.get('requirements', {})
    jd_keywords = set()
    
    for skill in requirements.get('required_skills', []):
        jd_keywords.update(skill.lower().split())
    for skill in requirements.get('preferred_skills', []):
        jd_keywords.update(skill.lower().split())
    for req in requirements.get('requirement_sentences', []):
        jd_keywords.update(req.get('text', '').lower().split())
    
    # Extract bullet keywords
    bullet_words = set(bullet_text.lower().split())
    
    # Remove common stop words
    stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                  'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
                  'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                  'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
                  'that', 'this', 'these', 'those', 'i', 'we', 'you', 'he', 'she', 'it'}
    
    bullet_words -= stop_words
    jd_keywords -= stop_words
    
    if not jd_keywords or not bullet_words:
        return 0.0
    
    # Jaccard similarity
    intersection = len(bullet_words & jd_keywords)
    union = len(bullet_words | jd_keywords)
    
    return intersection / union if union > 0 else 0.0


def compute_similarity_semantic(bullet_text: str, jd_data: Dict[str, Any], model) -> float:
    """
    Semantic similarity using sentence-transformers (if available).
    
    Args:
        bullet_text: The bullet point text
        jd_data: JD dictionary with requirements
        model: Loaded SentenceTransformer model
        
    Returns:
        Similarity score between 0 and 1
    """
    from sentence_transformers import util
    
    # Combine JD requirements into searchable text
    requirements = jd_data.get('requirements', {})
    jd_texts = []
    
    jd_texts.extend(requirements.get('required_skills', []))
    jd_texts.extend(requirements.get('preferred_skills', []))
    for req in requirements.get('requirement_sentences', []):
        jd_texts.append(req.get('text', ''))
    
    if not jd_texts:
        return 0.0
    
    # Encode texts
    bullet_embedding = model.encode(bullet_text, convert_to_tensor=True)
    jd_embeddings = model.encode(jd_texts, convert_to_tensor=True)
    
    # Compute similarities and take max
    similarities = util.cos_sim(bullet_embedding, jd_embeddings)
    max_similarity = float(similarities.max())
    
    return max_similarity


def score_against_all(
    bullets: List[Dict[str, Any]], 
    jds: List[Dict[str, Any]],
    use_semantic: bool = True
) -> np.ndarray:
    """
    Score all bullets against all JDs.
    
    Args:
        bullets: List of bullet dicts with 'text' field
        jds: List of JD dictionaries
        use_semantic: Whether to use semantic similarity (requires sentence-transformers)
        
    Returns:
        Score matrix of shape (num_bullets, num_jds)
    """
    num_bullets = len(bullets)
    num_jds = len(jds)
    
    # Try to load sentence-transformers
    model = None
    if use_semantic:
        try:
            from sentence_transformers import SentenceTransformer
            print("Loading sentence-transformer model...")
            model = SentenceTransformer('all-MiniLM-L6-v2')
            print("Using semantic similarity")
        except ImportError:
            print("sentence-transformers not available, using keyword matching")
            use_semantic = False
    
    # Compute scores
    scores = np.zeros((num_bullets, num_jds))
    
    print(f"Scoring {num_bullets} bullets against {num_jds} JDs...")
    for i, bullet in enumerate(bullets):
        for j, jd in enumerate(jds):
            if use_semantic and model:
                scores[i, j] = compute_similarity_semantic(bullet['text'], jd, model)
            else:
                scores[i, j] = compute_similarity_simple(bullet['text'], jd)
        
        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{num_bullets} bullets")
    
    return scores


# =============================================================================
# CLASSIFICATION
# =============================================================================

def classify_bullet(scores: np.ndarray) -> str:
    """
    Classify a bullet based on its scores across JDs.
    
    Args:
        scores: 1D array of scores for this bullet across all JDs
        
    Returns:
        Classification: 'universal', 'role_specific', or 'weak'
    """
    avg = np.mean(scores)
    std = np.std(scores)
    max_score = np.max(scores)
    
    # Universal: High average score across most JDs
    if avg >= UNIVERSAL_THRESHOLD:
        return 'universal'
    
    # Role-specific: High variance with at least one strong match
    if std >= ROLE_SPECIFIC_STD and max_score >= ROLE_SPECIFIC_MAX:
        return 'role_specific'
    
    # Weak: Low scores across the board
    if avg < WEAK_THRESHOLD:
        return 'weak'
    
    # Default: role_specific (moderate performance)
    return 'role_specific'


def analyze_bullets(
    bullets: List[Dict[str, Any]], 
    scores: np.ndarray,
    jd_names: List[str]
) -> List[BulletAnalysis]:
    """
    Analyze and classify all bullets.
    
    Args:
        bullets: List of bullet dicts
        scores: Score matrix (bullets x JDs)
        jd_names: Names of each JD
        
    Returns:
        List of BulletAnalysis objects
    """
    analyses = []
    
    for i, bullet in enumerate(bullets):
        bullet_scores = scores[i, :]
        
        analysis = BulletAnalysis(
            text=bullet['text'],
            scores=bullet_scores.tolist(),
            avg_score=float(np.mean(bullet_scores)),
            std_score=float(np.std(bullet_scores)),
            max_score=float(np.max(bullet_scores)),
            min_score=float(np.min(bullet_scores)),
            classification=classify_bullet(bullet_scores),
            best_jd_index=int(np.argmax(bullet_scores))
        )
        analyses.append(analysis)
    
    return analyses


# =============================================================================
# VISUALIZATION
# =============================================================================

def generate_heatmap(
    score_matrix: np.ndarray,
    bullet_labels: List[str],
    jd_labels: List[str],
    output_path: str,
    title: str = "Resume-JD Relevance Heatmap"
) -> str:
    """
    Generate a heatmap visualization of bullet-JD scores.
    
    Args:
        score_matrix: Matrix of shape (num_bullets, num_jds)
        bullet_labels: Short labels for each bullet
        jd_labels: Labels for each JD
        output_path: Path to save the heatmap image
        title: Title for the heatmap
        
    Returns:
        Path to saved image
    """
    if not VIZ_AVAILABLE:
        print("Visualization libraries not available. Skipping heatmap.")
        return None
    
    # Truncate labels for readability
    bullet_labels_short = [
        (label[:40] + '...') if len(label) > 40 else label 
        for label in bullet_labels
    ]
    jd_labels_short = [
        (label[:20] + '...') if len(label) > 20 else label 
        for label in jd_labels
    ]
    
    # Create figure
    fig_height = max(8, len(bullet_labels) * 0.3)
    fig_width = max(10, len(jd_labels) * 0.8)
    
    plt.figure(figsize=(fig_width, fig_height))
    
    # Create heatmap
    sns.heatmap(
        score_matrix,
        xticklabels=jd_labels_short,
        yticklabels=bullet_labels_short,
        cmap='RdYlGn',
        vmin=0,
        vmax=1,
        annot=True,
        fmt='.2f',
        cbar_kws={'label': 'Relevance Score'}
    )
    
    plt.title(title, fontsize=14, fontweight='bold')
    plt.xlabel('Job Descriptions', fontsize=12)
    plt.ylabel('Resume Bullets', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    
    # Save
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Heatmap saved to: {output_path}")
    return output_path


def generate_summary_chart(
    result: ComparisonResult,
    output_path: str
) -> str:
    """
    Generate a summary bar chart of bullet classifications.
    
    Args:
        result: ComparisonResult object
        output_path: Path to save the chart
        
    Returns:
        Path to saved image
    """
    if not VIZ_AVAILABLE:
        return None
    
    categories = ['Universal', 'Role-Specific', 'Weak']
    counts = [result.universal_count, result.role_specific_count, result.weak_count]
    colors = ['#2ecc71', '#f1c40f', '#e74c3c']
    
    plt.figure(figsize=(8, 5))
    bars = plt.bar(categories, counts, color=colors, edgecolor='black', linewidth=1.2)
    
    # Add count labels on bars
    for bar, count in zip(bars, counts):
        plt.text(
            bar.get_x() + bar.get_width()/2, 
            bar.get_height() + 0.5,
            str(count),
            ha='center',
            va='bottom',
            fontsize=14,
            fontweight='bold'
        )
    
    plt.title('Bullet Point Classification Summary', fontsize=14, fontweight='bold')
    plt.ylabel('Number of Bullets', fontsize=12)
    plt.ylim(0, max(counts) * 1.2)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✓ Summary chart saved to: {output_path}")
    return output_path


# =============================================================================
# MAIN COMPARISON FUNCTION
# =============================================================================

def compare(
    resume_path: str,
    jd_folder: str,
    output_folder: str,
    use_semantic: bool = True
) -> ComparisonResult:
    """
    Main function - compare one resume against multiple JDs.
    
    Args:
        resume_path: Path to parsed resume JSON from Person 1
        jd_folder: Path to folder containing JD JSON files
        output_folder: Folder to save outputs (heatmap, report)
        use_semantic: Whether to use semantic similarity
        
    Returns:
        ComparisonResult with all analysis data
    """
    # Create output folder
    os.makedirs(output_folder, exist_ok=True)
    
    # Load data
    print(f"Loading resume from: {resume_path}")
    with open(resume_path, 'r', encoding='utf-8') as f:
        resume_data = json.load(f)
    
    jds = load_jds(jd_folder)
    
    if not jds:
        raise ValueError(f"No JD files found in {jd_folder}")
    
    # Extract bullets
    bullets = extract_bullets_from_resume(resume_data)
    print(f"Found {len(bullets)} bullet points in resume")
    
    if not bullets:
        raise ValueError("No bullets found in resume")
    
    # Score against all JDs
    score_matrix = score_against_all(bullets, jds, use_semantic)
    
    # Get JD names for labeling
    jd_names = [
        jd.get('title', jd.get('_filename', f'JD {i+1}')) 
        for i, jd in enumerate(jds)
    ]
    
    # Analyze and classify
    analyses = analyze_bullets(bullets, score_matrix, jd_names)
    
    # Count classifications
    universal_count = sum(1 for a in analyses if a.classification == 'universal')
    role_specific_count = sum(1 for a in analyses if a.classification == 'role_specific')
    weak_count = sum(1 for a in analyses if a.classification == 'weak')
    
    result = ComparisonResult(
        bullets=analyses,
        jd_names=jd_names,
        score_matrix=score_matrix,
        universal_count=universal_count,
        role_specific_count=role_specific_count,
        weak_count=weak_count
    )
    
    # Generate visualizations
    bullet_labels = [b['text'] for b in bullets]
    
    heatmap_path = os.path.join(output_folder, 'jd_comparison_heatmap.png')
    generate_heatmap(score_matrix, bullet_labels, jd_names, heatmap_path)
    
    summary_path = os.path.join(output_folder, 'classification_summary.png')
    generate_summary_chart(result, summary_path)
    
    # Save detailed report as JSON
    report_path = os.path.join(output_folder, 'comparison_report.json')
    report = {
        'summary': {
            'total_bullets': len(bullets),
            'total_jds': len(jds),
            'universal_bullets': universal_count,
            'role_specific_bullets': role_specific_count,
            'weak_bullets': weak_count
        },
        'jd_names': jd_names,
        'bullets': [
            {
                'text': a.text,
                'classification': a.classification,
                'avg_score': round(a.avg_score, 3),
                'std_score': round(a.std_score, 3),
                'max_score': round(a.max_score, 3),
                'min_score': round(a.min_score, 3),
                'best_jd': jd_names[a.best_jd_index],
                'scores_by_jd': {
                    jd_names[i]: round(s, 3) 
                    for i, s in enumerate(a.scores)
                }
            }
            for a in analyses
        ]
    }
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f"✓ Detailed report saved to: {report_path}")
    
    # Print summary
    print("\n" + "="*60)
    print("MULTI-JD COMPARISON SUMMARY")
    print("="*60)
    print(f"Total bullets analyzed: {len(bullets)}")
    print(f"Total JDs compared: {len(jds)}")
    print(f"\n📊 Classification Results:")
    print(f"   🌟 Universal bullets: {universal_count} (strong across all JDs)")
    print(f"   🎯 Role-specific:     {role_specific_count} (high variance)")
    print(f"   ⚠️  Weak bullets:      {weak_count} (consider rewriting)")
    
    # Top universal bullets
    universal_bullets = [a for a in analyses if a.classification == 'universal']
    if universal_bullets:
        print(f"\n🌟 Top Universal Bullets (keep on every resume):")
        for a in sorted(universal_bullets, key=lambda x: x.avg_score, reverse=True)[:3]:
            print(f"   • {a.text[:60]}... (avg: {a.avg_score:.2f})")
    
    # Weakest bullets
    weak_bullets = [a for a in analyses if a.classification == 'weak']
    if weak_bullets:
        print(f"\n⚠️  Weakest Bullets (consider removing/rewriting):")
        for a in sorted(weak_bullets, key=lambda x: x.avg_score)[:3]:
            print(f"   • {a.text[:60]}... (avg: {a.avg_score:.2f})")
    
    return result


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Compare a resume against multiple job descriptions"
    )
    parser.add_argument(
        'resume_json',
        help='Path to parsed resume JSON from Person 1'
    )
    parser.add_argument(
        'jd_folder',
        help='Folder containing JD JSON files'
    )
    parser.add_argument(
        '-o', '--output',
        default='comparison_output',
        help='Output folder for results (default: comparison_output)'
    )
    parser.add_argument(
        '--no-semantic',
        action='store_true',
        help='Use keyword matching instead of semantic similarity'
    )
    
    args = parser.parse_args()
    
    result = compare(
        resume_path=args.resume_json,
        jd_folder=args.jd_folder,
        output_folder=args.output,
        use_semantic=not args.no_semantic
    )
