from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.schemas.form import PageScanResult

class LLMActionResult(BaseModel):
    """
    Structured extraction result from an LLM provider.
    """
    actions: List[Dict[str, Any]] = Field(default_factory=list)
    response: Optional[str] = None  # Milestone 5: Spoken conversational response
    ask_user: Optional[str] = None
    reasoning: Optional[str] = None


class LLMProvider(ABC):
    """
    Abstract interface for LLM reasoning and semantic form value extraction.
    """

    @abstractmethod
    async def extract_actions(
        self,
        transcript: str,
        schema: PageScanResult,
        current_values: Dict[str, Any],
        conversation_history: List[Dict[str, Any]],
        profile_context: Optional[Dict[str, Any]] = None
    ) -> LLMActionResult:
        """
        Processes user speech transcript in the context of the scanned form schema and optional profile context,
        returning structured fill actions and/or clarification questions.
        """
        pass
