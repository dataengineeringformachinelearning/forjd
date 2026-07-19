import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FjButton } from './button';

describe('FjButton', () => {
  let fixture: ComponentFixture<FjButton>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FjButton],
    }).compileComponents();

    fixture = TestBed.createComponent(FjButton);
    fixture.detectChanges();
  });

  it('renders a button', () => {
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.dataset['variant']).toBe('primary');
  });

  it('renders an anchor when href is set', () => {
    fixture.componentRef.setInput('href', 'https://backend.forjd.co/docs');
    fixture.componentRef.setInput('target', '_blank');
    fixture.detectChanges();
    const anchor = fixture.nativeElement.querySelector('a') as HTMLAnchorElement;
    expect(anchor).toBeTruthy();
    expect(anchor.getAttribute('href')).toBe('https://backend.forjd.co/docs');
    expect(anchor.getAttribute('rel')).toContain('noopener');
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
  });
});
