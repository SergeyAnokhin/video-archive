// Client-side library sorting, extracted from LibraryView.tsx so the
// search-results view (SearchResults.tsx) can apply the same toolbar sort
// modes to its own fetched lists.
import type { FileEntry, VariantTag } from '../types/api'

export type SortBy = 'name' | 'size' | 'tags'

export const SORT_OPTIONS: SortBy[] = ['name', 'size', 'tags']

function variantTagSortKey(tag: VariantTag): string {
  const value = typeof tag.value === 'number' ? tag.value.toString().padStart(8, '0') : tag.value
  return `${tag.param}:${value}`
}

function compareByTags(a: FileEntry, b: FileEntry): number {
  const aKeys = (a.variant_tags ?? []).map(variantTagSortKey).sort()
  const bKeys = (b.variant_tags ?? []).map(variantTagSortKey).sort()
  const length = Math.max(aKeys.length, bKeys.length)
  for (let i = 0; i < length; i++) {
    if (aKeys[i] === undefined) return bKeys[i] === undefined ? 0 : -1
    if (bKeys[i] === undefined) return 1
    if (aKeys[i] !== bKeys[i]) return aKeys[i] < bKeys[i] ? -1 : 1
  }
  return 0
}

export function sortFiles(files: FileEntry[], sortBy: SortBy): FileEntry[] {
  const sorted = [...files]
  switch (sortBy) {
    case 'name':
      sorted.sort((a, b) => a.file_name.localeCompare(b.file_name))
      break
    case 'size':
      sorted.sort((a, b) => b.size_bytes - a.size_bytes)
      break
    case 'tags':
      sorted.sort(compareByTags)
      break
  }
  return sorted
}
