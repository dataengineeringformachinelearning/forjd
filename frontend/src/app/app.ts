import { Component, signal } from '@angular/core';
import { FjButton } from 'forjd-ui';

@Component({
  selector: 'app-root',
  imports: [FjButton],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly title = signal('FORJD');
}
