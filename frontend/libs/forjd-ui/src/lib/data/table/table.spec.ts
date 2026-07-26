import { ComponentFixture, TestBed } from '@angular/core/testing';

import { FjTable } from './table';

describe('FjTable selection', () => {
  let fixture: ComponentFixture<FjTable>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [FjTable],
    }).compileComponents();

    fixture = TestBed.createComponent(FjTable);
    fixture.componentRef.setInput('columns', [{ key: 'name', label: 'Name' }]);
    fixture.componentRef.setInput('rows', [
      { id: 'a', name: 'Alpha' },
      { id: 'b', name: 'Beta' },
    ]);
    fixture.componentRef.setInput('selectable', true);
    fixture.componentRef.setInput('bulkActions', [
      { id: 'delete', label: 'Delete', variant: 'danger' },
    ]);
  });

  it('toggles a row and shows the bulk toolbar', () => {
    fixture.detectChanges();
    const boxes = fixture.nativeElement.querySelectorAll(
      'tbody input[type="checkbox"]',
    ) as NodeListOf<HTMLInputElement>;
    expect(boxes.length).toBe(2);

    boxes[0].click();
    fixture.detectChanges();

    expect(fixture.componentInstance.selectedIds()).toEqual(['a']);
    const toolbar = fixture.nativeElement.querySelector('.suite-bulk-toolbar');
    expect(toolbar?.textContent).toContain('1 selected');
  });

  it('select-all checks every row id', () => {
    fixture.detectChanges();
    const header = fixture.nativeElement.querySelector(
      'thead input[type="checkbox"]',
    ) as HTMLInputElement;
    header.click();
    fixture.detectChanges();

    expect(fixture.componentInstance.selectedIds()).toEqual(['a', 'b']);
  });

  it('emits bulkAction with the current selection', () => {
    const seen: { action: string; selectedIds: readonly string[] }[] = [];
    fixture.componentInstance.bulkAction.subscribe((event) => seen.push(event));
    fixture.componentRef.setInput('selectedIds', ['a', 'b']);
    fixture.detectChanges();

    const deleteBtn = Array.from(
      fixture.nativeElement.querySelectorAll('.suite-bulk-toolbar button'),
    ).find((el) => (el as HTMLElement).textContent?.includes('Delete')) as
      HTMLButtonElement | undefined;
    expect(deleteBtn).toBeTruthy();
    deleteBtn?.click();
    fixture.detectChanges();

    expect(seen).toEqual([{ action: 'delete', selectedIds: ['a', 'b'] }]);
  });
});
