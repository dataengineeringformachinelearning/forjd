import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { FjErrorBoundary, FjToastHost } from 'forjd-ui';

import { SHELL_STORY } from './shell.story';

// --- Route shell: error boundary + toast only (landing has no soft-chrome overlays) ---
@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, FjErrorBoundary, FjToastHost],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly shell = SHELL_STORY;
}
