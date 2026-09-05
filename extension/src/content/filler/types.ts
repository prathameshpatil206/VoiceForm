export type FormActionType =
  | 'fill_field'
  | 'clear_field'
  | 'select_option'
  | 'set_checkbox'
  | 'select_radio';

export type FillErrorCode =
  | 'FIELD_NOT_FOUND'
  | 'FIELD_DISABLED'
  | 'FIELD_READONLY'
  | 'INVALID_OPTION'
  | 'INVALID_VALUE'
  | 'UNSUPPORTED_TYPE'
  | 'MUTATION_FAILED';

export interface FormAction {
  action?: FormActionType;         // Defaults to 'fill_field'
  field_id?: string;               // Schema field identifier (e.g., 'vf-f-0' or element id)
  selector?: string;               // Direct CSS selector override
  name?: string;                   // HTML name fallback
  value: string | boolean | number;
}

export interface FillResult {
  success: boolean;
  field_id?: string;
  selector?: string;
  message?: string;
  error?: FillErrorCode;
  details?: string;
  previousValue?: string | boolean;
  newValue?: string | boolean;
}
