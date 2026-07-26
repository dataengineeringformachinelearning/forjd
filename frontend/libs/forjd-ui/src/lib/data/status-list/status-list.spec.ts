import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FjStatusList } from './status-list';

describe('FjStatusList', () => {
  let fixture: ComponentFixture<FjStatusList>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FjStatusList],
    }).compileComponents();

    fixture = TestBed.createComponent(FjStatusList);
  });

  it('renders items with default state labels', () => {
    fixture.componentRef.setInput('items', [
      { name: 'api', ok: true },
      { name: 'engine', ok: false },
    ]);
    fixture.detectChanges();

    const rows = fixture.nativeElement.querySelectorAll('li') as NodeListOf<HTMLLIElement>;
    expect(rows.length).toBe(2);
    expect(rows[0].textContent).toContain('api');
    expect(rows[0].textContent).toContain('ok');
    expect(rows[1].textContent).toContain('down');
    expect(rows[1].dataset['ok']).toBe('false');
  });
});
