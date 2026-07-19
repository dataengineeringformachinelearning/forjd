import { TestBed } from '@angular/core/testing';

import { Landing } from './landing';

describe('Landing', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Landing],
    }).compileComponents();
  });

  it('keeps the public product page at the root experience', async () => {
    const fixture = TestBed.createComponent(Landing);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.fj-brand')?.textContent).toContain('FORJD');
    expect(element.querySelectorAll('.landing__feature')).toHaveLength(4);
  });

  it('links to API documentation only — no runnable console', async () => {
    const fixture = TestBed.createComponent(Landing);
    await fixture.whenStable();
    const links = [...(fixture.nativeElement as HTMLElement).querySelectorAll('a')];
    expect(links.some((link) => link.getAttribute('href') === '/console')).toBe(false);
    expect(links.some((link) => link.getAttribute('href')?.endsWith('/docs'))).toBe(true);
    expect(links.some((link) => link.getAttribute('href')?.endsWith('/redoc'))).toBe(true);
  });
});
