import { FormField, PageScanResult } from '../../types/schema';
import { FormAction, FillResult } from './types';
import {
  normalizeBooleanValue,
  setNativeCheckboxValue,
  setNativeInputValue,
  setNativeRadioChecked,
  setNativeSelectValue
} from './value-setter';

/**
 * Main DOM Form Filler Engine (Milestone 2).
 * Modifies live form controls safely across modern web frameworks (React, Vue, etc.)
 * with zero hardcoded form dependencies and strict safety constraints.
 */

export function executeFillAction(
  action: FormAction,
  schema?: PageScanResult
): FillResult {
  const fieldId = action.field_id;

  // 1. Locate field in schema if provided
  let schemaField: FormField | undefined;
  if (schema && fieldId) {
    schemaField = findFieldInSchema(schema, fieldId);
  }

  // 2. Handle Radio Group special case
  if (schemaField && schemaField.type === 'radio') {
    return fillRadioGroup(schemaField, action);
  }

  // 3. Resolve target DOM element
  const element = resolveTargetElement(action, schemaField);
  if (!element) {
    return {
      success: false,
      field_id: fieldId,
      selector: action.selector,
      error: 'FIELD_NOT_FOUND',
      details: `Could not locate DOM element for field "${fieldId || action.selector || action.name}"`
    };
  }

  // 4. Pre-fill safety validations: disabled & read-only
  if (isElementDisabled(element)) {
    return {
      success: false,
      field_id: fieldId,
      selector: action.selector,
      error: 'FIELD_DISABLED',
      details: `Field is disabled and cannot be edited.`
    };
  }

  if (isElementReadOnly(element)) {
    return {
      success: false,
      field_id: fieldId,
      selector: action.selector,
      error: 'FIELD_READONLY',
      details: `Field is marked as read-only.`
    };
  }

  const tagName = element.tagName.toUpperCase();
  const inputType = (element.getAttribute('type') || 'text').toLowerCase();

  // 5. Handle Clear Field Action
  if (action.action === 'clear_field') {
    return handleClearField(element, fieldId);
  }

  // 6. Handle Checkbox Elements
  if (tagName === 'INPUT' && inputType === 'checkbox') {
    const checkbox = element as HTMLInputElement;
    const previousValue = checkbox.checked;
    const targetChecked = normalizeBooleanValue(action.value);

    setNativeCheckboxValue(checkbox, targetChecked);

    if (checkbox.checked !== targetChecked) {
      return {
        success: false,
        field_id: fieldId,
        error: 'MUTATION_FAILED',
        details: 'Checkbox DOM state did not reflect target checked state.'
      };
    }

    return {
      success: true,
      field_id: fieldId,
      message: `Checkbox ${targetChecked ? 'checked' : 'unchecked'} successfully`,
      previousValue,
      newValue: targetChecked
    };
  }

  // 7. Handle Select Dropdowns
  if (tagName === 'SELECT') {
    const select = element as HTMLSelectElement;
    const previousValue = select.value;
    const targetVal = String(action.value);

    const res = setNativeSelectValue(select, targetVal);
    if (!res.success) {
      return {
        success: false,
        field_id: fieldId,
        error: 'INVALID_OPTION',
        details: `Option "${targetVal}" not found or is disabled in select dropdown.`
      };
    }

    return {
      success: true,
      field_id: fieldId,
      message: `Selected "${res.selectedLabel}" [${res.selectedValue}]`,
      previousValue,
      newValue: res.selectedValue
    };
  }

  // 8. Handle Direct Radio Input
  if (tagName === 'INPUT' && inputType === 'radio') {
    const radio = element as HTMLInputElement;
    const previousValue = radio.checked;
    setNativeRadioChecked(radio);

    if (!radio.checked) {
      return {
        success: false,
        field_id: fieldId,
        error: 'MUTATION_FAILED',
        details: 'Radio input DOM checked state failed to update.'
      };
    }

    return {
      success: true,
      field_id: fieldId,
      message: `Selected radio option "${radio.value}"`,
      previousValue,
      newValue: radio.value
    };
  }

  // 9. Handle Standard Inputs and Textareas
  if (tagName === 'INPUT' || tagName === 'TEXTAREA') {
    const input = element as HTMLInputElement | HTMLTextAreaElement;
    const previousValue = input.value;
    const stringValue = String(action.value);

    // Normalize date/time if applicable
    const normalizedValue = normalizeDateTimeValue(stringValue, inputType);

    setNativeInputValue(input, normalizedValue);

    // Verify DOM state
    if (input.value !== normalizedValue) {
      return {
        success: false,
        field_id: fieldId,
        error: 'MUTATION_FAILED',
        details: `DOM value "${input.value}" does not match target value "${normalizedValue}"`
      };
    }

    return {
      success: true,
      field_id: fieldId,
      message: `Filled field successfully`,
      previousValue,
      newValue: normalizedValue
    };
  }

  return {
    success: false,
    field_id: fieldId,
    error: 'UNSUPPORTED_TYPE',
    details: `Unsupported element tag "${tagName}"`
  };
}

/**
 * Executes a batch of fill actions sequentially.
 */
export function executeFillActions(
  actions: FormAction[],
  schema?: PageScanResult
): FillResult[] {
  return actions.map(action => executeFillAction(action, schema));
}

function resolveTargetElement(
  action: FormAction,
  schemaField?: FormField
): HTMLElement | null {
  // 1. Check direct selector from action
  if (action.selector) {
    try {
      const el = document.querySelector<HTMLElement>(action.selector);
      if (el) return el;
    } catch {
      // Invalid selector
    }
  }

  // 2. Check selector from schema field
  if (schemaField && schemaField.selector) {
    try {
      const el = document.querySelector<HTMLElement>(schemaField.selector);
      if (el) return el;
    } catch {
      // Invalid selector
    }
  }

  // 3. Check element by field_id
  if (action.field_id) {
    const el = document.getElementById(action.field_id);
    if (el) return el;
  }

  // 4. Check element by name attribute
  const name = action.name || (schemaField && schemaField.name);
  if (name) {
    try {
      const escaped = CSS.escape(name);
      const el = document.querySelector<HTMLElement>(`[name="${escaped}"]`);
      if (el) return el;
    } catch {
      // ignore
    }
  }

  return null;
}

function fillRadioGroup(
  radioField: FormField,
  action: FormAction
): FillResult {
  const options = radioField.radioOptions || [];
  const targetVal = String(action.value).trim().toLowerCase();

  // Find matching option by value, label, or id
  let matchedOption = options.find(o => o.value.trim().toLowerCase() === targetVal);

  if (!matchedOption) {
    matchedOption = options.find(o => o.label.trim().toLowerCase() === targetVal);
  }

  if (!matchedOption) {
    matchedOption = options.find(o =>
      o.label.toLowerCase().includes(targetVal) ||
      targetVal.includes(o.label.toLowerCase())
    );
  }

  if (!matchedOption) {
    return {
      success: false,
      field_id: radioField.id,
      error: 'INVALID_OPTION',
      details: `No radio option matching "${action.value}" in group "${radioField.label || radioField.name}"`
    };
  }

  // Query the actual radio input element using the option's stable selector
  let radioEl: HTMLInputElement | null = null;
  if (matchedOption.selector) {
    try {
      radioEl = document.querySelector<HTMLInputElement>(matchedOption.selector);
    } catch {
      // ignore
    }
  }
  if (!radioEl && matchedOption.id) {
    radioEl = document.getElementById(matchedOption.id) as HTMLInputElement;
  }
  if (!radioEl) {
    // Fallback: search by name and value
    try {
      const escapedName = CSS.escape(radioField.name);
      const escapedVal = CSS.escape(matchedOption.value);
      radioEl = document.querySelector<HTMLInputElement>(`input[type="radio"][name="${escapedName}"][value="${escapedVal}"]`);
    } catch {
      // ignore
    }
  }

  if (!radioEl) {
    return {
      success: false,
      field_id: radioField.id,
      error: 'FIELD_NOT_FOUND',
      details: `Could not locate radio DOM input for option "${matchedOption.label}"`
    };
  }

  if (isElementDisabled(radioEl)) {
    return {
      success: false,
      field_id: radioField.id,
      error: 'FIELD_DISABLED',
      details: `Radio option "${matchedOption.label}" is disabled.`
    };
  }

  setNativeRadioChecked(radioEl);

  if (!radioEl.checked) {
    return {
      success: false,
      field_id: radioField.id,
      error: 'MUTATION_FAILED',
      details: 'Radio input DOM checked state failed to update.'
    };
  }

  return {
    success: true,
    field_id: radioField.id,
    selector: matchedOption.selector,
    message: `Selected radio option "${matchedOption.label}" (${matchedOption.value})`,
    newValue: matchedOption.value
  };
}

function handleClearField(element: HTMLElement, fieldId?: string): FillResult {
  const tagName = element.tagName.toUpperCase();
  const inputType = (element.getAttribute('type') || 'text').toLowerCase();

  if (tagName === 'INPUT' && inputType === 'checkbox') {
    setNativeCheckboxValue(element as HTMLInputElement, false);
    return {
      success: true,
      field_id: fieldId,
      message: 'Cleared checkbox (unchecked)',
      newValue: false
    };
  }

  if (tagName === 'SELECT') {
    const select = element as HTMLSelectElement;
    if (select.options.length > 0) {
      // Set to first option (usually empty prompt or default)
      setNativeSelectValue(select, select.options[0].value);
    }
    return {
      success: true,
      field_id: fieldId,
      message: 'Reset select dropdown to initial option',
      newValue: select.value
    };
  }

  if (tagName === 'INPUT' || tagName === 'TEXTAREA') {
    setNativeInputValue(element as HTMLInputElement | HTMLTextAreaElement, '');
    return {
      success: true,
      field_id: fieldId,
      message: 'Cleared input field',
      newValue: ''
    };
  }

  return {
    success: false,
    field_id: fieldId,
    error: 'UNSUPPORTED_TYPE',
    details: 'Cannot clear field of this type'
  };
}

function findFieldInSchema(schema: PageScanResult, fieldId: string): FormField | undefined {
  const allFields = [...schema.forms.flatMap(form => form.fields), ...schema.orphanFields];

  // Direct match by ID or name
  const directMatch = allFields.find(field => field.id === fieldId || field.name === fieldId);
  if (directMatch) return directMatch;

  // Check if fieldId matches an individual radio option inside a radio group
  const radioGroupMatch = allFields.find(field =>
    field.type === 'radio' &&
    field.radioOptions?.some(opt => opt.id === fieldId || opt.selector === fieldId)
  );
  if (radioGroupMatch) return radioGroupMatch;

  return undefined;
}

function isElementDisabled(element: HTMLElement): boolean {
  if ('disabled' in element && (element as any).disabled) return true;
  if (element.hasAttribute('disabled')) return true;
  if (element.getAttribute('aria-disabled') === 'true') return true;
  return false;
}

function isElementReadOnly(element: HTMLElement): boolean {
  if ('readOnly' in element && (element as any).readOnly) return true;
  if (element.hasAttribute('readonly')) return true;
  return false;
}

function normalizeDateTimeValue(val: string, inputType: string): string {
  const trimmed = val.trim();
  if (inputType === 'date') {
    // If given ISO string e.g. 2026-09-05T00:00:00.000Z, extract YYYY-MM-DD
    if (/^\d{4}-\d{2}-\d{2}/.test(trimmed)) {
      return trimmed.slice(0, 10);
    }
  }
  if (inputType === 'time') {
    // If given HH:MM:SS, format to HH:MM if standard
    if (/^\d{2}:\d{2}:\d{2}$/.test(trimmed)) {
      return trimmed.slice(0, 5);
    }
  }
  if (inputType === 'datetime-local') {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(trimmed)) {
      return trimmed.slice(0, 16);
    }
  }
  return trimmed;
}
