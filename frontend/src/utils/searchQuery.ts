// Scoped library search (user request): the search box accepts an optional
// `tag:` / `file:` / `path:` prefix that narrows where to look; without a
// prefix the query searches all three areas at once. Russian aliases are
// accepted on input but always formatted back as the English canonical form.

export type SearchScope = 'all' | 'tag' | 'file' | 'path'

export interface ActiveSearch {
  scope: SearchScope
  label: string
  value: string
}

const SCOPE_ALIASES: Record<string, Exclude<SearchScope, 'all'>> = {
  tag: 'tag',
  тег: 'tag',
  file: 'file',
  файл: 'file',
  path: 'path',
  путь: 'path',
}

export interface ParsedSearchQuery {
  scope: SearchScope
  term: string
}

export function parseSearchQuery(input: string): ParsedSearchQuery {
  const trimmed = input.trim()
  const colon = trimmed.indexOf(':')
  if (colon > 0) {
    const scope = SCOPE_ALIASES[trimmed.slice(0, colon).trim().toLowerCase()]
    if (scope) {
      return { scope, term: trimmed.slice(colon + 1).trim() }
    }
  }
  return { scope: 'all', term: trimmed }
}

export function formatSearchQuery(scope: SearchScope, term: string): string {
  return scope === 'all' ? term : `${scope}:${term}`
}
