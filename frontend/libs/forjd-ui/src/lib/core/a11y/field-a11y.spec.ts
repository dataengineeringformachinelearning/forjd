import { describe, expect, it } from 'vitest';

import { fieldDescribedBy, syncFieldControlA11y } from './field-a11y';

describe('forjd field-a11y helpers', () => {
  it('builds describedby keeping description with error', () => {
    expect(
      fieldDescribedBy({
        descriptionId: 'd',
        errorId: 'e',
        hasDescription: true,
        hasError: true,
      }),
    ).toBe('d e');
  });

  it('syncFieldControlA11y clears invalid when error is gone', () => {
    const root = document.createElement('div');
    root.innerHTML = `<input type="text" />`;
    syncFieldControlA11y(root, {
      descriptionId: 'd',
      errorId: 'e',
      hasDescription: false,
      hasError: true,
    });
    expect(root.querySelector('input')?.getAttribute('aria-invalid')).toBe('true');
    syncFieldControlA11y(root, {
      descriptionId: 'd',
      errorId: 'e',
      hasDescription: false,
      hasError: false,
    });
    expect(root.querySelector('input')?.hasAttribute('aria-invalid')).toBe(false);
  });
});
