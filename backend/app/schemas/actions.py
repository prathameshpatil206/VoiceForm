from typing import Any, Optional
from pydantic import BaseModel

class FillAction(BaseModel):
    action: str = "fill_field"
    field_id: Optional[str] = None
    selector: Optional[str] = None
    name: Optional[str] = None
    value: Any

class FillResult(BaseModel):
    success: bool
    field_id: Optional[str] = None
    selector: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    details: Optional[str] = None
    previousValue: Optional[Any] = None
    newValue: Optional[Any] = None
