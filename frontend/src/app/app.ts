import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

// --- Route shell ---
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {}
