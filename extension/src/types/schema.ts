export type FieldType =
  | 'text'
  | 'email'
  | 'password'
  | 'tel'
  | 'number'
  | 'url'
  | 'date'
  | 'time'
  | 'datetime-local'
  | 'month'
  | 'week'
  | 'search'
  | 'color'
  | 'file'
  | 'range'
  | 'select'
  | 'checkbox'
  | 'radio'
  | 'textarea'
  | 'hidden'
  | 'unknown';

export interface SelectOption {
  value: string;
  label: string;
  selected: boolean;
  disabled: boolean;
}

export interface RadioOption {
  id: string;
  value: string;
  label: string;
  checked: boolean;
  disabled: boolean;
  selector: string; // Crucial for M2 to target and select a specific radio button
}

export interface ValidationRules {
  required: boolean;
  pattern?: string;
  minLength?: number;
  maxLength?: number;
  min?: string | number;
  max?: string | number;
  step?: string | number;
}

export interface AriaInfo {
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  required?: boolean;
  invalid?: boolean;
}

export interface FormField {
  id: string;                      // Stable unique identifier assigned by scanner (e.g. 'vf-f-0')
  name: string;                    // HTML name or fallback
  type: FieldType;
  label: string;                   // Resolved human-readable label
  placeholder: string;
  currentValue: string | boolean;  // String value, or boolean for standalone checkbox
  validation: ValidationRules;
  autocomplete?: string;
  aria: AriaInfo;
  options?: SelectOption[];        // For <select> elements
  radioOptions?: RadioOption[];    // For grouped radio buttons
  selector: string;                // Stable CSS selector for DOM manipulation (M2)
  isVisible: boolean;
  disabled: boolean;
  readOnly: boolean;
  tagName: string;                 // 'INPUT', 'SELECT', 'TEXTAREA'
  formId?: string;                 // ID of parent form if enclosed
}

export interface DetectedForm {
  formId: string;                  // HTML id, name, or generated 'vf-form-0'
  name?: string;
  action?: string;
  method?: string;
  selector: string;                // CSS selector for the form element
  title?: string;                  // Form heading, legend, or aria-label
  fields: FormField[];
  fieldCount: number;
  lastScannedAt: number;
}

export interface PageScanResult {
  url: string;
  title: string;
  forms: DetectedForm[];
  orphanFields: FormField[];       // Fields existing outside <form> tags
  totalFieldCount: number;
  scannedAt: number;
}
