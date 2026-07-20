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

describe('FjButton projected label', () => {
  it('projects label text into an href anchor', async () => {
    const { Component } = await import('@angular/core');
    @Component({
      imports: [FjButton],
      template: `<forjd-button variant="primary" href="https://backend.forjd.co/docs">API docs</forjd-button>`,
    })
    class Host {}

    await TestBed.configureTestingModule({ imports: [Host] }).compileComponents();
    const hostFixture = TestBed.createComponent(Host);
    hostFixture.detectChanges();

    const anchor = hostFixture.nativeElement.querySelector('a') as HTMLAnchorElement;
    expect(anchor).toBeTruthy();
    expect(anchor.textContent?.trim()).toBe('API docs');
  });
});
