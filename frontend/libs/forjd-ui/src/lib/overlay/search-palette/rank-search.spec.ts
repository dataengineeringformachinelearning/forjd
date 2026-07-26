import { rankSearchItems, scoreSearchItem } from './rank-search';
import type { FjSearchPaletteItem } from './search-palette.types';

const items: FjSearchPaletteItem[] = [
  {
    title: 'Sealed ingest',
    href: '#ingest',
    group: 'Product',
    keywords: ['e2ee', 'ciphertext'],
    snippet: 'X25519 envelopes',
  },
  {
    title: 'Swagger',
    href: '/docs',
    group: 'API',
    keywords: ['openapi'],
  },
  {
    title: 'Projections',
    href: '#projections',
    group: 'Product',
    snippet: 'Checkpointed stream_results',
  },
];

describe('rankSearchItems', () => {
  it('ranks exact title above keyword hits', () => {
    const ranked = rankSearchItems(items, 'swagger');
    expect(ranked[0]?.title).toBe('Swagger');
    expect(scoreSearchItem(items[1]!, 'swagger')).toBeGreaterThan(
      scoreSearchItem(items[0]!, 'swagger'),
    );
  });

  it('matches keywords when title misses', () => {
    const ranked = rankSearchItems(items, 'ciphertext');
    expect(ranked.map((row) => row.title)).toEqual(['Sealed ingest']);
  });

  it('returns curated order for empty query', () => {
    expect(rankSearchItems(items, ' ').map((row) => row.title)).toEqual(
      items.map((row) => row.title),
    );
  });
});
