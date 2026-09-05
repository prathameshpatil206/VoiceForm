import {
  AriaInfo,
  FieldType,
  FormField,
  RadioOption,
  SelectOption,
  ValidationRules
} from '../../types/schema';
import {
  cleanLabelText,
  formatNameToLabel,
  resolveFieldLabel,
  resolveRadioOptionLabel
} from './label-resolver';
import { generateElementSelector } from './selector-generator';

export type FormElement = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

/**
 * Extracts normalized FormField metadata from an HTML form element.
 */
export function extractFormField(
  element: FormElement,
  fieldIndex: number,
  formId?: string
): FormField {
  const tagName = element.tagName.toUpperCase();
  const type = determineFieldType(element);
  const selector = generateElementSelector(element);
  const isVisible = checkElementVisibility(element, type);
  const label = resolveFieldLabel(element);
  const placeholder = element.getAttribute('placeholder') || '';
  const autocomplete = element.getAttribute('autocomplete') || undefined;

  const disabled = element.disabled || element.hasAttribute('disabled') || element.getAttribute('aria-disabled') === 'true';
  const readOnly = 'readOnly' in element ? (element as HTMLInputElement).readOnly : false;

  const validation = extractValidationRules(element);
  const aria = extractAriaInfo(element);

  let currentValue: string | boolean = '';
  let options: SelectOption[] | undefined;

  if (tagName === 'SELECT') {
    const select = element as HTMLSelectElement;
    currentValue = select.value;
    options = Array.from(select.options).map(opt => ({
      value: opt.value,
      label: opt.text ? opt.text.trim() : opt.value,
      selected: opt.selected,
      disabled: opt.disabled
    }));
  } else if (type === 'checkbox') {
    currentValue = (element as HTMLInputElement).checked;
  } else {
    currentValue = (element as HTMLInputElement | HTMLTextAreaElement).value || '';
  }

  const fieldId = element.id ? element.id : `vf-f-${fieldIndex}`;

  return {
    id: fieldId,
    name: element.name || element.id || fieldId,
    type,
    label,
    placeholder,
    currentValue,
    validation,
    autocomplete,
    aria,
    options,
    selector,
    isVisible,
    disabled,
    readOnly,
    tagName,
    formId
  };
}

/**
 * Creates a grouped FormField for a set of related radio buttons sharing the same name.
 */
export function extractRadioGroupField(
  radios: HTMLInputElement[],
  fieldIndex: number,
  formId?: string
): FormField {
  const firstRadio = radios[0];
  const name = firstRadio.name || firstRadio.id || `radio-group-${fieldIndex}`;

  // For a radio group, prioritize <fieldset><legend> or group name before individual radio labels
  let groupLabel = '';
  const fieldset = firstRadio.closest('fieldset');
  if (fieldset) {
    const legend = fieldset.querySelector('legend');
    if (legend) {
      groupLabel = cleanLabelText(legend.textContent || '');
    } else {
      const fieldsetAria = fieldset.getAttribute('aria-label');
      if (fieldsetAria) groupLabel = cleanLabelText(fieldsetAria);
    }
  }

  if (!groupLabel) {
    if (firstRadio.name) {
      groupLabel = formatNameToLabel(firstRadio.name);
    } else {
      groupLabel = resolveFieldLabel(firstRadio);
    }
  }

  const radioOptions: RadioOption[] = radios.map(radio => {
    const selector = generateElementSelector(radio);
    return {
      id: radio.id || selector,
      value: radio.value || 'on',
      label: resolveRadioOptionLabel(radio),
      checked: radio.checked,
      disabled: radio.disabled || radio.hasAttribute('disabled'),
      selector
    };
  });

  const checkedOption = radioOptions.find(o => o.checked);
  const currentValue = checkedOption ? checkedOption.value : '';

  const isRequired = radios.some(r => r.required || r.getAttribute('aria-required') === 'true');
  const allDisabled = radios.every(r => r.disabled || r.hasAttribute('disabled'));
  const isVisible = radios.some(r => checkElementVisibility(r, 'radio'));

  const aria = extractAriaInfo(firstRadio);

  return {
    id: `vf-rg-${name || fieldIndex}`,
    name,
    type: 'radio',
    label: groupLabel,
    placeholder: '',
    currentValue,
    validation: {
      required: isRequired
    },
    aria,
    radioOptions,
    selector: radioOptions[0]?.selector || generateElementSelector(firstRadio),
    isVisible,
    disabled: allDisabled,
    readOnly: false,
    tagName: 'INPUT',
    formId
  };
}

function determineFieldType(element: FormElement): FieldType {
  const tag = element.tagName.toUpperCase();
  if (tag === 'SELECT') return 'select';
  if (tag === 'TEXTAREA') return 'textarea';

  const type = (element.getAttribute('type') || 'text').toLowerCase();
  const knownTypes: FieldType[] = [
    'text', 'email', 'password', 'tel', 'number', 'url',
    'date', 'time', 'datetime-local', 'month', 'week',
    'search', 'color', 'file', 'range', 'checkbox', 'radio', 'hidden'
  ];

  if (knownTypes.includes(type as FieldType)) {
    return type as FieldType;
  }
  return 'text';
}

function extractValidationRules(element: FormElement): ValidationRules {
  const isRequired = element.required ||
    element.hasAttribute('required') ||
    element.getAttribute('aria-required') === 'true';

  const pattern = element.getAttribute('pattern') || undefined;
  
  let minLength: number | undefined;
  if ('minLength' in element && element.minLength > 0) {
    minLength = element.minLength;
  }

  let maxLength: number | undefined;
  if ('maxLength' in element && element.maxLength > 0) {
    maxLength = element.maxLength;
  }

  const min = element.getAttribute('min') || undefined;
  const max = element.getAttribute('max') || undefined;
  const step = element.getAttribute('step') || undefined;

  return {
    required: isRequired,
    pattern,
    minLength,
    maxLength,
    min,
    max,
    step
  };
}

function extractAriaInfo(element: FormElement): AriaInfo {
  return {
    label: element.getAttribute('aria-label') || undefined,
    labelledBy: element.getAttribute('aria-labelledby') || undefined,
    describedBy: element.getAttribute('aria-describedby') || undefined,
    required: element.getAttribute('aria-required') === 'true' ? true : undefined,
    invalid: element.getAttribute('aria-invalid') === 'true' ? true : undefined
  };
}

function checkElementVisibility(element: HTMLElement, type: FieldType): boolean {
  if (type === 'hidden') return false;

  // Modern browser checkVisibility
  if (typeof (element as any).checkVisibility === 'function') {
    return (element as any).checkVisibility({
      checkOpacity: true,
      checkVisibilityCSS: true
    });
  }

  // Fallback to computed style & bounding box
  const style = window.getComputedStyle(element);
  if (
    style.display === 'none' ||
    style.visibility === 'hidden' ||
    style.opacity === '0'
  ) {
    return false;
  }

  const rect = element.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0 && !element.getClientRects().length) {
    return false;
  }

  return true;
}
