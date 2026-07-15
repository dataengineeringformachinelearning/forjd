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
});
