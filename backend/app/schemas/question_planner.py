from typing import Any, Literal

from pydantic import BaseModel, Field


class PlannedQuestion(BaseModel):
    """One clinician question identified by the pre-flight planner."""

    text: str
    intent: str = "general"
    focus_class_ids: list[str] = Field(default_factory=list)
    required_data_fields: list[str] = Field(default_factory=list)
    priority: int = 1


class QuestionPlan(BaseModel):
    """Chain-of-thought plan produced before running the clinical pipeline."""

    source: Literal["llm", "fallback"] = "fallback"
    reasoning: str = ""
    is_multi_question: bool = False
    questions: list[PlannedQuestion] = Field(default_factory=list)
    active_question_index: int = 0

    @property
    def active_question(self) -> PlannedQuestion | None:
        if not self.questions:
            return None
        idx = min(max(self.active_question_index, 0), len(self.questions) - 1)
        return self.questions[idx]

    def question_texts(self) -> list[str]:
        return [item.text for item in self.questions if item.text.strip()]
