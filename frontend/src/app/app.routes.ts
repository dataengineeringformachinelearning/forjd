import { Routes } from '@angular/router';

import { Landing } from './landing/landing';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    // Eager: landing is the only product surface — keep LCP (hero mark/brand) in the initial graph.
    component: Landing,
    title: 'FORJD — Universal Secure Streaming Engine',
  },
  { path: '**', redirectTo: '' },
];
