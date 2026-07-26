import { ComponentFixture, TestBed } from '@angular/core/testing';

import { FjSearchPalette } from './search-palette';

describe('FjSearchPalette', () => {
  let fixture: ComponentFixture<FjSearchPalette>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FjSearchPalette],
    }).compileComponents();

    fixture = TestBed.createComponent(FjSearchPalette);
    fixture.componentRef.setInput('items', [
      {
        title: 'Swagger',
        href: 'https://backend.forjd.co/docs',
        group: 'API',
        keywords: ['openapi'],
      },
      {
        title: 'Sealed ingest',
        href: '#capabilities-title',
        group: 'Product',
        keywords: ['e2ee'],
      },
    ]);
    fixture.componentRef.setInput('globalShortcut', false);
    fixture.detectChanges();
  });

  it('ranks results after search()', () => {
    const palette = fixture.componentInstance;
    palette.openPalette();
    palette.search('openapi');
    fixture.detectChanges();
    expect(palette['flatResults']().map((row) => row.title)).toEqual(['Swagger']);
  });

  it('exposes openPalette / closePalette', () => {
    const palette = fixture.componentInstance;
    palette.openPalette();
    expect(palette.open()).toBe(true);
    palette.closePalette();
    expect(palette.open()).toBe(false);
    expect(palette['query']()).toBe('');
  });

  it('keeps the closed dialog out of the layout (UA dialog rule)', () => {
    fixture.detectChanges();
    const dialog = fixture.nativeElement.querySelector(
      'dialog.fj-search-palette-backdrop',
    ) as HTMLDialogElement | null;
    expect(dialog).toBeTruthy();
    expect(dialog!.open).toBe(false);
    // Author display:flex must not override dialog:not([open]) { display: none }.
    expect(getComputedStyle(dialog!).display).toBe('none');
  });
});
