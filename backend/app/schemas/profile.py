from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProfileSource(str, Enum):
    USER_SPOKEN = "USER_SPOKEN"
    USER_ENTERED = "USER_ENTERED"
    USER_CONFIRMED = "USER_CONFIRMED"
    IMPORTED = "IMPORTED"


class FieldMatchStatus(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    AMBIGUOUS = "AMBIGUOUS"


class ProfileFieldSchema(BaseModel):
    id: str
    profile_id: str
    canonical_key: str
    value: str
    source: ProfileSource = ProfileSource.USER_SPOKEN
    confidence: float = 1.0
    created_at: datetime
    updated_at: datetime


class UserProfileSchema(BaseModel):
    id: str
    is_enabled: bool = True
    fields: Dict[str, ProfileFieldSchema] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ProfileCandidate(BaseModel):
    canonical_key: str
    value: str
    confidence: float = 1.0
    source: ProfileSource = ProfileSource.USER_SPOKEN


class ProfileMatchCandidate(BaseModel):
    field_id: str
    canonical_key: Optional[str] = None
    status: FieldMatchStatus = FieldMatchStatus.UNKNOWN
    value: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[ProfileSource] = None


class UpsertProfileFieldRequest(BaseModel):
    canonical_key: str
    value: str
    source: ProfileSource = ProfileSource.USER_CONFIRMED
    confidence: float = 1.0


class BatchUpsertProfileRequest(BaseModel):
    fields: List[UpsertProfileFieldRequest]


class ProfileSettingsRequest(BaseModel):
    is_enabled: bool


class ProfileResponse(BaseModel):
    profile_id: str
    is_enabled: bool
    fields: Dict[str, Dict[str, Any]]
    field_count: int
