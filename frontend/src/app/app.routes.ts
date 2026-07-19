import { Routes } from '@angular/router';

import { Landing } from './landing/landing';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    component: Landing,
    title: 'FORJD — Universal secure streaming engine',
  },
  { path: '**', redirectTo: '' },
];
