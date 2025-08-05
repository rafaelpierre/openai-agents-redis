from typing import Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Example context models


class IntentContext(BaseModel):
    """Context for storing user intent information."""
    label: str
    confidence: Optional[float] = None
    timestamp: Optional[float] = Field(default_factory=lambda: datetime.now().timestamp())
    entities: Dict[str, Any] = Field(default_factory=dict)

class ProfileContext(BaseModel):
    """Context for storing user profile information."""
    label: str
    user_id: Optional[str] = None
    additional_data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[float] = Field(default_factory=lambda: datetime.now().timestamp())

class ConversationContext(BaseModel):
    """Context for storing conversation information."""
    message: str
    response: str
    timestamp: Optional[float] = Field(default_factory=lambda: datetime.now().timestamp())

class AgentMemoryContext(BaseModel):
    """
    Comprehensive context object that combines local context with memory.
    This is what you pass to openai-agents Runner.run(..., context=this_object).
    """
    
    # Local context (user info, session data)
    user_id: str
    session_id: str
    name: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    
    # Memory contexts (your nested approach)
    intent_context: Optional[IntentContext] = None
    profile_context: Optional[ProfileContext] = None
    conversation_summary: Optional[str] = None
    
    # Metadata
    created_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_updated: float = Field(default_factory=lambda: datetime.now().timestamp())
    total_interactions: int = 0
    
    # Helper methods for updating contexts
    def update_intent(self, label: str, confidence: float, entities: Optional[Dict] = None) -> None:
        """Update intent context."""
        self.intent_context = IntentContext(
            label=label,
            confidence=confidence,
            entities=entities or {}
        )
        self._touch()
    
    def update_profile(self, label: str, additional_data: Optional[Dict] = None) -> None:
        """Update profile context."""
        self.profile_context = ProfileContext(
            label=label,
            user_id=self.user_id,
            additional_data=additional_data or {}
        )
        self._touch()
    
    def add_conversation_summary(self, summary: str) -> None:
        """Update conversation summary."""
        self.conversation_summary = summary
        self._touch()
    
    def increment_interactions(self) -> None:
        """Increment interaction counter."""
        self.total_interactions += 1
        self._touch()
    
    def _touch(self) -> None:
        """Update the last_updated timestamp."""
        self.last_updated = datetime.now().timestamp()
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get a summary of the current context state."""
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "name": self.name,
            "total_interactions": self.total_interactions,
            "has_intent": self.intent_context is not None,
            "has_profile": self.profile_context is not None,
            "has_conversation_summary": self.conversation_summary is not None,
            "latest_intent": self.intent_context.label if self.intent_context else None,
            "latest_profile": self.profile_context.label if self.profile_context else None,
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "last_updated": datetime.fromtimestamp(self.last_updated).isoformat(),
        }