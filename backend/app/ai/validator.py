import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.schemas.actions import FillAction
from app.schemas.form import FormField, PageScanResult

logger = logging.getLogger("voiceform.ai.validator")

ALLOWED_ACTIONS = {"fill_field", "clear_field", "select_option"}

class ValidationResult:
    def __init__(
        self,
        is_valid: bool,
        action: Optional[FillAction] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None
    ) -> None:
        self.is_valid = is_valid
        self.action = action
        self.error = error
        self.error_code = error_code

class ActionValidator:
    """
    Action Validation Layer between LLM output and M2 DOM Filler.
    Enforces strict safety, schema existence, fillability constraints, and type checks.
    Guarantees the LLM never directly provides DOM selectors or script injections.
    """

    @staticmethod
    def _build_field_map(schema: PageScanResult) -> Dict[str, FormField]:
        field_map: Dict[str, FormField] = {}
        for form in schema.forms:
            for f in form.fields:
                field_map[f.id] = f
                if f.type == "radio" and f.radioOptions:
                    for r in f.radioOptions:
                        if r.id and r.id not in field_map:
                            field_map[r.id] = f
        for f in schema.orphanFields:
            field_map[f.id] = f
            if f.type == "radio" and f.radioOptions:
                for r in f.radioOptions:
                    if r.id and r.id not in field_map:
                        field_map[r.id] = f
        return field_map

    def validate_action(
        self, raw_action: Dict[str, Any], schema: PageScanResult
    ) -> ValidationResult:
        # 1. Structure check
        if not isinstance(raw_action, dict):
            return ValidationResult(
                is_valid=False,
                error="Action must be a JSON object",
                error_code="MALFORMED_ACTION"
            )

        act_type = str(raw_action.get("action", "")).strip().lower()
        if act_type not in ALLOWED_ACTIONS:
            return ValidationResult(
                is_valid=False,
                error=f"Disallowed action type '{act_type}'. Allowed: {sorted(ALLOWED_ACTIONS)}",
                error_code="DISALLOWED_ACTION_TYPE"
            )

        field_id = str(raw_action.get("field_id", "")).strip()
        if not field_id:
            return ValidationResult(
                is_valid=False,
                error="Action missing required 'field_id'",
                error_code="MISSING_FIELD_ID"
            )

        # 2. Schema existence check
        field_map = self._build_field_map(schema)
        if field_id not in field_map:
            return ValidationResult(
                is_valid=False,
                error=f"Field ID '{field_id}' does not exist in current form schema",
                error_code="FIELD_NOT_FOUND"
            )

        field = field_map[field_id]

        # 3. Fillability guards (disabled / readOnly rejection)
        if field.disabled:
            return ValidationResult(
                is_valid=False,
                error=f"Field '{field_id}' is disabled and cannot be modified",
                error_code="FIELD_DISABLED"
            )

        if field.readOnly:
            return ValidationResult(
                is_valid=False,
                error=f"Field '{field_id}' is read-only and cannot be modified",
                error_code="FIELD_READONLY"
            )

        # 4. Handle clear_field
        if act_type == "clear_field":
            clear_val = False if field.type == "checkbox" else ""
            return ValidationResult(
                is_valid=True,
                action=FillAction(
                    action="clear_field",
                    field_id=field.id,
                    selector=field.selector,  # Use trusted selector from schema
                    name=field.name,
                    value=clear_val
                )
            )

        # 5. Value normalization and type checking
        raw_val = raw_action.get("value")
        if raw_val is None:
            return ValidationResult(
                is_valid=False,
                error=f"Action '{act_type}' on field '{field_id}' missing value",
                error_code="MISSING_VALUE"
            )

        norm_val: Any = raw_val

        if field.type == "number":
            try:
                # Strip non-numeric formatting if string
                str_val = str(raw_val).strip().replace(",", "")
                norm_val = float(str_val) if "." in str_val else int(str_val)
            except (ValueError, TypeError):
                return ValidationResult(
                    is_valid=False,
                    error=f"Value '{raw_val}' cannot be parsed as a number for field '{field_id}'",
                    error_code="INVALID_NUMBER_TYPE"
                )

        elif field.type == "email":
            str_email = str(raw_val).strip()
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str_email):
                return ValidationResult(
                    is_valid=False,
                    error=f"Value '{raw_val}' is not a valid email address for field '{field_id}'",
                    error_code="INVALID_EMAIL_FORMAT"
                )
            norm_val = str_email

        elif field.type == "checkbox":
            if isinstance(raw_val, bool):
                norm_val = raw_val
            else:
                str_bool = str(raw_val).strip().lower()
                norm_val = str_bool in ("true", "1", "yes", "check", "checked", "on")

        elif field.type == "select":
            # Match against options by value or label
            options = field.options or []
            matched_option = None
            str_target = str(raw_val).strip().lower()

            for opt in options:
                if opt.value.lower() == str_target or opt.label.lower() == str_target:
                    matched_option = opt
                    break

            if not matched_option:
                valid_opts = [f"'{o.label}' ({o.value})" for o in options]
                return ValidationResult(
                    is_valid=False,
                    error=f"Value '{raw_val}' not found in available options for field '{field_id}'. Valid options: {valid_opts}",
                    error_code="INVALID_SELECT_OPTION"
                )
            norm_val = matched_option.value  # Normalize to option value

        elif field.type == "radio":
            # Match against radioOptions by value or label
            radio_opts = field.radioOptions or []
            matched_radio = None
            str_target = str(raw_val).strip().lower()

            for ro in radio_opts:
                if ro.value.lower() == str_target or ro.label.lower() == str_target:
                    matched_radio = ro
                    break

            if not matched_radio:
                valid_opts = [f"'{r.label}' ({r.value})" for r in radio_opts]
                return ValidationResult(
                    is_valid=False,
                    error=f"Value '{raw_val}' not found in available radio options for field '{field_id}'. Valid options: {valid_opts}",
                    error_code="INVALID_RADIO_OPTION"
                )
            norm_val = matched_radio.value  # Normalize to radio value

        else:
            norm_val = str(raw_val).strip()

        # Construct safe FillAction using trusted schema selector
        return ValidationResult(
            is_valid=True,
            action=FillAction(
                action="fill_field",
                field_id=field.id,
                selector=field.selector,
                name=field.name,
                value=norm_val
            )
        )

    def validate_actions(
        self, raw_actions: List[Dict[str, Any]], schema: PageScanResult
    ) -> Tuple[List[FillAction], List[Dict[str, Any]]]:
        """
        Validates a batch of raw LLM actions against the form schema.
        Returns (valid_actions, rejected_errors).
        """
        valid_actions: List[FillAction] = []
        errors: List[Dict[str, Any]] = []

        for raw_act in raw_actions:
            result = self.validate_action(raw_act, schema)
            if result.is_valid and result.action:
                valid_actions.append(result.action)
            else:
                logger.warning(
                    f"Action validation rejected: {result.error} (code={result.error_code})"
                )
                errors.append({
                    "action": raw_act,
                    "error": result.error,
                    "error_code": result.error_code
                })

        return valid_actions, errors
