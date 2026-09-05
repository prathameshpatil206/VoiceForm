from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field

class SelectOption(BaseModel):
    value: str
    label: str
    selected: bool = False
    disabled: bool = False

class RadioOption(BaseModel):
    id: str
    value: str
    label: str
    checked: bool = False
    disabled: bool = False
    selector: str

class ValidationRules(BaseModel):
    required: bool = False
    pattern: Optional[str] = None
    minLength: Optional[int] = None
    maxLength: Optional[int] = None
    min: Optional[Union[str, int, float]] = None
    max: Optional[Union[str, int, float]] = None
    step: Optional[Union[str, int, float]] = None

class AriaInfo(BaseModel):
    label: Optional[str] = None
    labelledBy: Optional[str] = None
    describedBy: Optional[str] = None
    required: Optional[bool] = None
    invalid: Optional[bool] = None

class FormField(BaseModel):
    id: str
    name: str
    type: str
    label: str
    placeholder: str = ""
    currentValue: Any = ""
    validation: ValidationRules = Field(default_factory=ValidationRules)
    autocomplete: Optional[str] = None
    aria: AriaInfo = Field(default_factory=AriaInfo)
    options: Optional[List[SelectOption]] = None
    radioOptions: Optional[List[RadioOption]] = None
    selector: str
    isVisible: bool = True
    disabled: bool = False
    readOnly: bool = False
    tagName: str = "INPUT"
    formId: Optional[str] = None

class DetectedForm(BaseModel):
    formId: str
    name: Optional[str] = None
    action: Optional[str] = None
    method: Optional[str] = None
    selector: str
    title: Optional[str] = None
    fields: List[FormField] = Field(default_factory=list)
    fieldCount: int = 0
    lastScannedAt: int = 0

class PageScanResult(BaseModel):
    url: str
    title: str
    forms: List[DetectedForm] = Field(default_factory=list)
    orphanFields: List[FormField] = Field(default_factory=list)
    totalFieldCount: int = 0
    scannedAt: int = 0
