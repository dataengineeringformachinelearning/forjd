import {
  DEFAULT_RECENT_STORAGE_KEY,
  clearRecentSearches,
  pushRecentSearch,
  readRecentSearches,
  recentSearchesAsItems,
} from './recent-searches';

describe('recent searches', () => {
  beforeEach(() => {
    clearRecentSearches(DEFAULT_RECENT_STORAGE_KEY);
  });

  afterEach(() => {
    clearRecentSearches(DEFAULT_RECENT_STORAGE_KEY);
  });

  it('pushes newest first and dedupes by query', () => {
    pushRecentSearch({ query: 'swagger' });
    pushRecentSearch({ query: 'projections' });
    pushRecentSearch({ query: 'swagger', title: 'Swagger', href: '/docs' });
    const recent = readRecentSearches();
    expect(recent.map((row) => row.query)).toEqual(['swagger', 'projections']);
    expect(recent[0]?.href).toBe('/docs');
  });

  it('maps query-only recents to re-run hrefs', () => {
    pushRecentSearch({ query: 'sealed ingest' });
    const items = recentSearchesAsItems(readRecentSearches());
    expect(items[0]?.group).toBe('Recent');
    expect(items[0]?.href).toContain('#fj-recent:');
  });
});
