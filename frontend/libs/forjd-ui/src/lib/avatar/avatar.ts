import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

@Component({
  selector: 'forjd-avatar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-avatar fj-avatar',
    '[attr.data-size]': 'size()',
  },
  template: `
    @if (src()) {
      <img [src]="src()!" [alt]="alt()" />
    } @else {
      <span aria-hidden="true">{{ initials() }}</span>
    }
  `,
})
export class FjAvatar {
  readonly src = input<string | undefined>(undefined);
  readonly alt = input('');
  readonly name = input('');
  readonly size = input<'sm' | 'md' | 'lg'>('md');

  protected readonly initials = computed(() => {
    const parts = this.name().trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  });
}
