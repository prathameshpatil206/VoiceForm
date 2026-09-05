import { DetectedForm, FormField, PageScanResult } from '../../types/schema';
import { extractFormField, extractRadioGroupField, FormElement } from './field-extractor';
import { generateElementSelector } from './selector-generator';

const IGNORED_INPUT_TYPES = new Set(['submit', 'button', 'reset', 'image']);
const SHADOW_HOST_TAG = 'voiceform-debug-drawer';

/**
 * Main DOM scanner that discovers forms and orphan fields on the current page.
 */
export function scanPageForms(): PageScanResult {
  const forms: DetectedForm[] = [];
  const scannedElements = new Set<Element>();

  // 1. Scan explicit <form> elements
  const formElements = Array.from(document.querySelectorAll('form'));
  let formCounter = 0;
  let globalFieldCounter = 0;

  for (const form of formElements) {
    if (isVoiceFormElement(form)) continue;

    const formId = form.id || form.getAttribute('name') || `vf-form-${formCounter++}`;
    const formSelector = generateElementSelector(form);
    const formTitle = extractFormTitle(form);

    const controls = Array.from(
      form.querySelectorAll<FormElement>('input, select, textarea')
    ).filter(el => !isIgnoredControl(el));

    const { fields, processedSet } = processControlList(controls, globalFieldCounter, formId);
    globalFieldCounter += fields.length;

    // Track processed elements so they aren't marked as orphans
    processedSet.forEach(el => scannedElements.add(el));

    forms.push({
      formId,
      name: form.getAttribute('name') || undefined,
      action: form.getAttribute('action') || undefined,
      method: form.getAttribute('method') || undefined,
      selector: formSelector,
      title: formTitle,
      fields,
      fieldCount: fields.length,
      lastScannedAt: Date.now()
    });
  }

  // 2. Scan orphan controls (fields living outside any <form>)
  const allControls = Array.from(
    document.querySelectorAll<FormElement>('input, select, textarea')
  ).filter(el => !isIgnoredControl(el) && !el.closest('form'));

  const orphanControls = allControls.filter(el => !scannedElements.has(el));
  const { fields: orphanFields } = processControlList(
    orphanControls,
    globalFieldCounter,
    undefined
  );

  const totalFieldCount =
    forms.reduce((sum, f) => sum + f.fieldCount, 0) + orphanFields.length;

  return {
    url: window.location.href,
    title: document.title,
    forms,
    orphanFields,
    totalFieldCount,
    scannedAt: Date.now()
  };
}

/**
 * Processes a list of form controls, grouping radio buttons by name.
 */
function processControlList(
  controls: FormElement[],
  startCounter: number,
  formId?: string
): { fields: FormField[]; processedSet: Set<Element> } {
  const fields: FormField[] = [];
  const processedSet = new Set<Element>();
  let counter = startCounter;

  // Group radio buttons by name
  const radioGroups = new Map<string, HTMLInputElement[]>();
  const nonRadios: FormElement[] = [];

  for (const control of controls) {
    if (isVoiceFormElement(control)) continue;

    if (control.tagName === 'INPUT' && (control as HTMLInputElement).type === 'radio') {
      const radio = control as HTMLInputElement;
      const groupName = radio.name || radio.id || '__unnamed_radio__';
      if (!radioGroups.has(groupName)) {
        radioGroups.set(groupName, []);
      }
      radioGroups.get(groupName)!.push(radio);
    } else {
      nonRadios.push(control);
    }
  }

  // 1. Process non-radio fields
  for (const control of nonRadios) {
    const field = extractFormField(control, counter++, formId);
    fields.push(field);
    processedSet.add(control);
  }

  // 2. Process grouped radio buttons
  for (const [, radios] of radioGroups.entries()) {
    if (radios.length === 0) continue;
    const groupField = extractRadioGroupField(radios, counter++, formId);
    fields.push(groupField);
    radios.forEach(r => processedSet.add(r));
  }

  return { fields, processedSet };
}

function isIgnoredControl(element: FormElement): boolean {
  if (isVoiceFormElement(element)) return true;

  if (element.tagName === 'INPUT') {
    const type = (element.getAttribute('type') || 'text').toLowerCase();
    if (IGNORED_INPUT_TYPES.has(type)) {
      return true;
    }
  }

  return false;
}

function isVoiceFormElement(element: Element): boolean {
  if (element.tagName.toLowerCase() === SHADOW_HOST_TAG) return true;
  if (element.closest(SHADOW_HOST_TAG)) return true;
  if (element.hasAttribute('data-voiceform-ignore')) return true;
  return false;
}

function extractFormTitle(form: HTMLFormElement): string | undefined {
  // 1. Check aria-label or aria-labelledby
  const ariaLabel = form.getAttribute('aria-label');
  if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

  const labelledBy = form.getAttribute('aria-labelledby');
  if (labelledBy) {
    const el = document.getElementById(labelledBy.trim());
    if (el && el.textContent?.trim()) return el.textContent.trim();
  }

  // 2. Check first legend or heading inside form
  const legend = form.querySelector('legend');
  if (legend && legend.textContent?.trim()) {
    return legend.textContent.trim();
  }

  const heading = form.querySelector('h1, h2, h3, h4');
  if (heading && heading.textContent?.trim()) {
    return heading.textContent.trim();
  }

  // 3. Check immediately preceding heading
  let prev = form.previousElementSibling;
  while (prev) {
    if (/^H[1-4]$/.test(prev.tagName)) {
      const text = prev.textContent?.trim();
      if (text) return text;
    }
    prev = prev.previousElementSibling;
  }

  // 4. Form name or ID
  if (form.id) return form.id;
  if (form.name) return form.name;

  return undefined;
}
