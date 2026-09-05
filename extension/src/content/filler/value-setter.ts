/**
 * Safe value setter engine for modern DOMs and frameworks (React, Vue, Angular, Svelte).
 * Uses native prototype property descriptors and synthetic event pipelines.
 */

export function setNativeInputValue(
  input: HTMLInputElement | HTMLTextAreaElement,
  value: string
): void {
  const previousValue = input.value;
  if (previousValue === value) return;

  // 1. Focus the input
  input.focus();
  input.dispatchEvent(new FocusEvent('focus', { bubbles: true }));

  // 2. Locate native prototype property descriptor for 'value'
  const prototype = input instanceof HTMLInputElement
    ? window.HTMLInputElement.prototype
    : window.HTMLTextAreaElement.prototype;

  const descriptor = Object.getOwnPropertyDescriptor(prototype, 'value');

  if (descriptor && descriptor.set) {
    descriptor.set.call(input, value);
  } else {
    input.value = value;
  }

  // 3. Reset React's internal value tracker if present so React detects the diff
  const tracker = (input as any)._valueTracker;
  if (tracker && typeof tracker.setValue === 'function') {
    tracker.setValue(previousValue);
  }

  // 4. Dispatch standard synthetic events
  input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));

  // 5. Blur the input
  input.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}

export function setNativeCheckboxValue(
  checkbox: HTMLInputElement,
  checked: boolean
): void {
  const previousChecked = checkbox.checked;
  if (previousChecked === checked) return;

  checkbox.focus();
  checkbox.dispatchEvent(new FocusEvent('focus', { bubbles: true }));

  const descriptor = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'checked'
  );

  if (descriptor && descriptor.set) {
    descriptor.set.call(checkbox, checked);
  } else {
    checkbox.checked = checked;
  }

  // React value tracker for checked
  const tracker = (checkbox as any)._valueTracker;
  if (tracker && typeof tracker.setValue === 'function') {
    tracker.setValue(previousChecked);
  }

  // Dispatch events
  checkbox.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  checkbox.dispatchEvent(new Event('change', { bubbles: true }));
  checkbox.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}

export function setNativeRadioChecked(radio: HTMLInputElement): void {
  if (radio.checked) return;

  radio.focus();
  radio.dispatchEvent(new FocusEvent('focus', { bubbles: true }));

  const descriptor = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'checked'
  );

  if (descriptor && descriptor.set) {
    descriptor.set.call(radio, true);
  } else {
    radio.checked = true;
  }

  const tracker = (radio as any)._valueTracker;
  if (tracker && typeof tracker.setValue === 'function') {
    tracker.setValue(false);
  }

  radio.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  radio.dispatchEvent(new Event('change', { bubbles: true }));
  radio.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
}

export function setNativeSelectValue(
  select: HTMLSelectElement,
  targetValueOrLabel: string
): { success: boolean; selectedValue?: string; selectedLabel?: string } {
  select.focus();
  select.dispatchEvent(new FocusEvent('focus', { bubbles: true }));

  const normalizedTarget = targetValueOrLabel.trim().toLowerCase();
  const options = Array.from(select.options);

  // 1. Try exact value match
  let matchedOption = options.find(opt => opt.value === targetValueOrLabel);

  // 2. Try case-insensitive value match
  if (!matchedOption) {
    matchedOption = options.find(opt => opt.value.trim().toLowerCase() === normalizedTarget);
  }

  // 3. Try exact label/text match
  if (!matchedOption) {
    matchedOption = options.find(opt => opt.text.trim() === targetValueOrLabel.trim());
  }

  // 4. Try case-insensitive label/text match
  if (!matchedOption) {
    matchedOption = options.find(opt => opt.text.trim().toLowerCase() === normalizedTarget);
  }

  // 5. Try substring match on label (e.g. "United States" matching "United States of America")
  if (!matchedOption) {
    matchedOption = options.find(opt =>
      opt.text.toLowerCase().includes(normalizedTarget) ||
      normalizedTarget.includes(opt.text.toLowerCase())
    );
  }

  if (!matchedOption || matchedOption.disabled) {
    return { success: false };
  }

  const previousValue = select.value;
  const descriptor = Object.getOwnPropertyDescriptor(
    window.HTMLSelectElement.prototype,
    'value'
  );

  if (descriptor && descriptor.set) {
    descriptor.set.call(select, matchedOption.value);
  } else {
    select.value = matchedOption.value;
  }

  matchedOption.selected = true;

  const tracker = (select as any)._valueTracker;
  if (tracker && typeof tracker.setValue === 'function') {
    tracker.setValue(previousValue);
  }

  select.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
  select.dispatchEvent(new Event('change', { bubbles: true }));
  select.dispatchEvent(new FocusEvent('blur', { bubbles: true }));

  return {
    success: true,
    selectedValue: matchedOption.value,
    selectedLabel: matchedOption.text.trim()
  };
}

/**
 * Normalizes values for boolean/checkbox inputs.
 */
export function normalizeBooleanValue(val: unknown): boolean {
  if (typeof val === 'boolean') return val;
  if (typeof val === 'number') return val !== 0;
  if (typeof val === 'string') {
    const s = val.trim().toLowerCase();
    return ['true', '1', 'yes', 'on', 'checked'].includes(s);
  }
  return Boolean(val);
}
