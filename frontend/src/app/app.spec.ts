import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';

import { App } from './app';
import { routes } from './app.routes';
import { Landing } from './landing/landing';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should create the app', () => {
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should host routed pages via a router outlet inside an error boundary', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('forjd-error-boundary')).toBeTruthy();
    expect(compiled.querySelector('router-outlet')).toBeTruthy();
    expect(compiled.querySelector('forjd-toast-host')).toBeTruthy();
    // Landing-only: no console soft-chrome overlays mounted at the root.
    expect(compiled.querySelector('forjd-preferences')).toBeNull();
    expect(compiled.querySelector('forjd-shortcut-help')).toBeNull();
  });

  it('should render only the static landing at the root', () => {
    expect(routes.find(({ path }) => path === '')?.component).toBe(Landing);
    expect(routes.find(({ path }) => path === 'console')).toBeUndefined();
  });
});
