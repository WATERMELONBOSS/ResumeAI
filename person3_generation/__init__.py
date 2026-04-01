"""
person3_generation - Resume Assembly and Generation Module
ResumeAI Project - CS 5100 Foundations of AI

This module handles Stage 3 of the pipeline:
- assembler.py: Select and rank resume content based on scores
- latex_generator.py: Generate PDF resumes using LaTeX
- multi_jd_compare.py: Compare resume against multiple JDs

Usage:
    from person3_generation import assembler, latex_generator, multi_jd_compare
    
    # Assemble tailored resume
    scored_data = assembler.load_scored_data('path/to/scored.json')
    assembled = assembler.assemble(scored_data)
    
    # Generate PDF
    latex_generator.generate(assembled, 'output/resume.pdf')
    
    # Multi-JD comparison
    result = multi_jd_compare.compare('resume.json', 'jd_folder/', 'output/')
"""

from . import assembler
from . import latex_generator
from . import multi_jd_compare

__version__ = '1.0.0'
__author__ = 'Person 3 - ResumeAI Team'

__all__ = [
    'assembler',
    'latex_generator', 
    'multi_jd_compare'
]
