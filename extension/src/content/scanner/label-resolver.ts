/**
 * Multi-tier semantic label resolution engine.
 * Resolves human-readable labels for form fields using an 8-tier fallback strategy.
 */

export function resolveFieldLabel(element: HTMLElement): string {
  // 1. Explicit <label for="elementId">
  if (element.id) {
    try {
      const explicitLabel = document.querySelector<HTMLLabelElement>(
        `label[for="${CSS.escape(element.id)}"]`
      );
      if (explicitLabel) {
        const text = extractCleanText(explicitLabel, element);
        if (text) return text;
      }
    } catch {
      // Fall through if invalid selector
    }
  }

  // 2. Direct ancestor <label> enclosure
  const ancestorLabel = element.closest('label');
  if (ancestorLabel) {
    const text = extractCleanText(ancestorLabel, element);
    if (text) return text;
  }

  // 3. aria-labelledby
  const labelledBy = element.getAttribute('aria-labelledby');
  if (labelledBy) {
    const ids = labelledBy.trim().split(/\s+/);
    const parts: string[] = [];
    for (const id of ids) {
      try {
        const target = document.getElementById(id);
        if (target) {
          const t = target.textContent?.trim();
          if (t) parts.push(t);
        }
      } catch {
        // Continue
      }
    }
    if (parts.length > 0) {
      const text = cleanLabelText(parts.join(' '));
      if (text) return text;
    }
  }

  // 4. aria-label
  const ariaLabel = element.getAttribute('aria-label');
  if (ariaLabel && ariaLabel.trim()) {
    const text = cleanLabelText(ariaLabel);
    if (text) return text;
  }

  // 5. Preceding sibling or nearby label-like element
  const precedingLabel = findPrecedingLabel(element);
  if (precedingLabel) {
    return precedingLabel;
  }

  // 6. Fieldset <legend> context (especially for radio groups / checkboxes)
  const fieldset = element.closest('fieldset');
  if (fieldset) {
    const legend = fieldset.querySelector('legend');
    if (legend) {
      const text = cleanLabelText(legend.textContent || '');
      if (text) return text;
    }
  }

  // 7. Placeholder attribute
  const placeholder = element.getAttribute('placeholder');
  if (placeholder && placeholder.trim()) {
    const text = cleanLabelText(placeholder);
    if (text) return text;
  }

  // 8. Name attribute formatted to Title Case
  const name = element.getAttribute('name');
  if (name && name.trim()) {
    return formatNameToLabel(name);
  }

  // 9. Element ID formatted to Title Case as last resort
  if (element.id && element.id.trim()) {
    return formatNameToLabel(element.id);
  }

  return 'Unlabeled Field';
}

/**
 * Resolves the label for an individual radio option in a radio group.
 */
export function resolveRadioOptionLabel(radioInput: HTMLInputElement): string {
  // 1. Explicit <label for="radioId">
  if (radioInput.id) {
    try {
      const explicitLabel = document.querySelector<HTMLLabelElement>(
        `label[for="${CSS.escape(radioInput.id)}"]`
      );
      if (explicitLabel) {
        const text = extractCleanText(explicitLabel, radioInput);
        if (text) return text;
      }
    } catch {
      // ignore
    }
  }

  // 2. Wrapped <label>
  const ancestorLabel = radioInput.closest('label');
  if (ancestorLabel) {
    const text = extractCleanText(ancestorLabel, radioInput);
    if (text) return text;
  }

  // 3. aria-label
  const ariaLabel = radioInput.getAttribute('aria-label');
  if (ariaLabel && ariaLabel.trim()) {
    return cleanLabelText(ariaLabel);
  }

  // 4. Immediately following or preceding text node / sibling
  const nextSibling = radioInput.nextSibling;
  if (nextSibling && nextSibling.nodeType === Node.TEXT_NODE) {
    const text = cleanLabelText(nextSibling.textContent || '');
    if (text) return text;
  }
  if (radioInput.nextElementSibling) {
    const text = cleanLabelText(radioInput.nextElementSibling.textContent || '');
    if (text && text.length < 60) return text;
  }

  // 5. Value attribute formatted
  if (radioInput.value) {
    return formatNameToLabel(radioInput.value);
  }

  return 'Option';
}

/**
 * Extracts text content from a label element without picking up nested inputs' values.
 */
function extractCleanText(label: HTMLLabelElement, _targetElement?: HTMLElement): string {
  const clone = label.cloneNode(true) as HTMLElement;
  // Remove inputs, selects, textareas to prevent their text from polluting the label
  const nestedControls = clone.querySelectorAll('input, select, textarea, button');
  nestedControls.forEach(ctrl => ctrl.remove());
  
  return cleanLabelText(clone.textContent || '');
}

/**
 * Looks for preceding sibling or parent container label-like text.
 */
function findPrecedingLabel(element: HTMLElement): string | null {
  // Check previous element siblings
  let prev = element.previousElementSibling;
  while (prev) {
    const tag = prev.tagName.toLowerCase();
    if (['label', 'span', 'p', 'div', 'b', 'strong', 'dt'].includes(tag)) {
      const text = cleanLabelText(prev.textContent || '');
      // Reasonable length for a form field label
      if (text && text.length > 0 && text.length < 100) {
        return text;
      }
    }
    prev = prev.previousElementSibling;
  }

  // Check parent's previous element (e.g., in grid or flex layouts: <div>Label</div> <div><input></div>)
  const parent = element.parentElement;
  if (parent && parent.parentElement && !['form', 'body'].includes(parent.tagName.toLowerCase())) {
    const parentPrev = parent.previousElementSibling;
    if (parentPrev) {
      const text = cleanLabelText(parentPrev.textContent || '');
      if (text && text.length > 0 && text.length < 80) {
        return text;
      }
    }
  }

  return null;
}

/**
 * Strips asterisks, trailing punctuation, and cleans up whitespace.
 */
export function cleanLabelText(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/\s+/g, ' ')                          // Normalize multiple spaces/newlines
    .replace(/\s*[\*＊]\s*$/, '')                   // Remove trailing required asterisk
    .replace(/^\s*[\*＊]\s*/, '')                   // Remove leading asterisk
    .replace(/\s*\(required\)\s*$/i, '')           // Remove (required) annotations
    .replace(/\s*\(optional\)\s*$/i, '')           // Remove (optional) annotations
    .replace(/[:：]\s*$/, '')                      // Remove trailing colons
    .trim();
}

/**
 * Converts camelCase, snake_case, or kebab-case to Title Case.
 * e.g., 'first_name' -> 'First Name', 'shippingAddress' -> 'Shipping Address'
 */
export function formatNameToLabel(str: string): string {
  if (!str) return '';
  return str
    .replace(/[-_]+/g, ' ')                        // Replace hyphens and underscores with space
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')         // Break camelCase
    .replace(/\b\w/g, c => c.toUpperCase())        // Capitalize first letter of each word
    .trim();
}
