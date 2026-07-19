import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';

import { Landing } from './landing';

describe('Landing', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Landing],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('keeps the public product page at the root experience', async () => {
    const fixture = TestBed.createComponent(Landing);
    await fixture.whenStable();
    const element = fixture.nativeElement as HTMLElement;
    expect(element.querySelector('.fj-brand')?.textContent).toContain('FORJD');
    expect(element.querySelectorAll('.landing__feature')).toHaveLength(6);
  });

  it('links to the isolated operational console and API docs', async () => {
    const fixture = TestBed.createComponent(Landing);
    await fixture.whenStable();
    const links = [...(fixture.nativeElement as HTMLElement).querySelectorAll('a')];
    expect(links.some((link) => link.getAttribute('href') === '/console')).toBe(true);
    expect(links.some((link) => link.getAttribute('href')?.endsWith('/docs'))).toBe(true);
  });
});
