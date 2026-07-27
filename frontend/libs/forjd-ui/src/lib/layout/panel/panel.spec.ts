import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FjPanel } from './panel';

describe('FjPanel', () => {
  let fixture: ComponentFixture<FjPanel>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FjPanel],
    }).compileComponents();

    fixture = TestBed.createComponent(FjPanel);
  });

  it('renders a title when provided', () => {
    fixture.componentRef.setInput('title', 'Stack');
    fixture.detectChanges();
    const heading = fixture.nativeElement.querySelector('h2') as HTMLHeadingElement;
    expect(heading?.textContent).toContain('Stack');
    expect(fixture.nativeElement.getAttribute('role')).toBe('region');
    expect(fixture.nativeElement.getAttribute('aria-label')).toBe('Stack');
  });

  it('omits the heading when title is empty', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h2')).toBeNull();
    expect(fixture.nativeElement.hasAttribute('role')).toBe(false);
    expect(fixture.nativeElement.hasAttribute('aria-label')).toBe(false);
  });

  it('does not turn repeated cards into page landmarks', () => {
    fixture.componentRef.setInput('title', 'Ingest');
    fixture.componentRef.setInput('variant', 'card');
    fixture.detectChanges();

    expect(fixture.nativeElement.hasAttribute('role')).toBe(false);
    expect(fixture.nativeElement.hasAttribute('aria-label')).toBe(false);
  });
});
