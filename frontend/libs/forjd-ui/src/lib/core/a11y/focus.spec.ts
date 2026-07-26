import { describe, expect, it } from 'vitest';
import {
  focusFirst,
  getFocusableElements,
  nextRovingIndex,
  nextRovingIndexBothAxes,
  nextRovingIndexHorizontal,
} from './focus';

describe('forjd focus helpers', () => {
  it('lists focusable controls', () => {
    document.body.innerHTML = `
      <div id="root">
        <button type="button">A</button>
        <button type="button" disabled>B</button>
        <a href="#x">C</a>
      </div>
    `;
    const root = document.getElementById('root')!;
    expect(getFocusableElements(root).map((el) => el.textContent?.trim())).toEqual(['A', 'C']);
  });

  it('focusFirst targets the first control', () => {
    document.body.innerHTML = `
      <div id="root"><button type="button" id="go">Go</button></div>
    `;
    focusFirst(document.getElementById('root')!);
    expect(document.activeElement?.id).toBe('go');
  });

  it('roving helpers wrap', () => {
    expect(nextRovingIndex('ArrowRight', 1, 2)).toBe(0);
    expect(nextRovingIndexHorizontal('ArrowRight', 1, 2)).toBe(0);
    expect(nextRovingIndexBothAxes('ArrowUp', 0, 3)).toBe(2);
  });
});
