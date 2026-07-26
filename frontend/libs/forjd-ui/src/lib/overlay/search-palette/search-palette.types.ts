/** Curated or recent destination for the suite command palette. */
export type FjSearchPaletteItem = {
  readonly title: string;
  readonly href: string;
  readonly snippet?: string;
  readonly group?: string;
  readonly keywords?: readonly string[];
  readonly action?: string;
};
