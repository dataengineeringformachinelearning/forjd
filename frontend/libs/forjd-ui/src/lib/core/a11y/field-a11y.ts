/**
 * Field validation a11y — associate description/error with the control
 * (mirrors viking-ui/core/field-a11y).
 */

export const FIELD_CONTROL_SELECTOR = [
  'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="image"])',
  'textarea',
  'select',
  '[role="combobox"]',
  '[role="textbox"]',
  '[role="spinbutton"]',
  '[role="searchbox"]',
].join(',');

export type FieldMessageIds = {
  descriptionId: string;
  errorId: string;
  hasDescription: boolean;
  hasError: boolean;
};

export function fieldDescribedBy(ids: FieldMessageIds): string | null {
  const parts: string[] = [];
  if (ids.hasDescription) parts.push(ids.descriptionId);
  if (ids.hasError) parts.push(ids.errorId);
  return parts.length ? parts.join(' ') : null;
}

export function findFieldControl(root: ParentNode): HTMLElement | null {
  const found = root.querySelector(FIELD_CONTROL_SELECTOR);
  return found instanceof HTMLElement ? found : null;
}

export function syncFieldControlA11y(
  root: ParentNode,
  ids: FieldMessageIds & { required?: boolean },
): HTMLElement | null {
  const control = findFieldControl(root);
  if (!control) return null;

  const describedBy = fieldDescribedBy(ids);
  if (describedBy) {
    control.setAttribute('aria-describedby', describedBy);
  } else {
    control.removeAttribute('aria-describedby');
  }

  if (ids.hasError) {
    control.setAttribute('aria-invalid', 'true');
  } else {
    control.removeAttribute('aria-invalid');
  }

  if (ids.required) {
    control.setAttribute('aria-required', 'true');
    if (
      control instanceof HTMLInputElement ||
      control instanceof HTMLTextAreaElement ||
      control instanceof HTMLSelectElement
    ) {
      control.required = true;
    }
  }

  return control;
}
