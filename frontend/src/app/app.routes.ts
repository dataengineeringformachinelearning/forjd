import { Routes } from '@angular/router';

import { Landing } from './landing/landing';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    component: Landing,
    title: 'FORJD — Universal secure streaming engine',
  },
  {
    path: 'console',
    loadComponent: () => import('./console/console').then(({ Console }) => Console),
    title: 'FORJD Console',
  },
  { path: '**', redirectTo: '' },
];
