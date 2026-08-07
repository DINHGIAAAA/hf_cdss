"""English system prompts for scraper semantic LLM extraction steps."""

from scraper.prompts.claim_extraction import CLAIM_EXTRACTION_SYSTEM_PROMPT
from scraper.prompts.condition_refinement import CONDITION_REFINEMENT_SYSTEM_PROMPT
from scraper.prompts.dose_extraction import STRUCTURED_DOSE_EXTRACTION_SYSTEM_PROMPT
from scraper.prompts.gdmt_policy_extraction import STRUCTURED_GDMT_POLICY_EXTRACTION_SYSTEM_PROMPT
from scraper.prompts.interaction_extraction import STRUCTURED_INTERACTION_EXTRACTION_SYSTEM_PROMPT
from scraper.prompts.section_importance import SECTION_IMPORTANCE_SYSTEM_PROMPT

__all__ = [
    "CLAIM_EXTRACTION_SYSTEM_PROMPT",
    "CONDITION_REFINEMENT_SYSTEM_PROMPT",
    "SECTION_IMPORTANCE_SYSTEM_PROMPT",
    "STRUCTURED_DOSE_EXTRACTION_SYSTEM_PROMPT",
    "STRUCTURED_GDMT_POLICY_EXTRACTION_SYSTEM_PROMPT",
    "STRUCTURED_INTERACTION_EXTRACTION_SYSTEM_PROMPT",
]
