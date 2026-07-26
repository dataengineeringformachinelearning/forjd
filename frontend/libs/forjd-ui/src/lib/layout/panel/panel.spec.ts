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
  });

  it('omits the heading when title is empty', () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h2')).toBeNull();
  });
});
