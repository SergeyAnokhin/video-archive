import { describe, expect, it } from 'vitest'
import type { DirectoryEntry, DirectoryStatus, FileEntry, VariantTag } from '../types/api'
import { sortDirectories, sortFiles } from './sortFiles'

function dir(name: string, totalSizeBytes?: number): DirectoryEntry {
  const status: DirectoryStatus | undefined =
    totalSizeBytes === undefined
      ? undefined
      : {
          total_supported_files: 1,
          converted_count: 0,
          preview_count: 0,
          conversion_complete: false,
          preview_complete: false,
          total_size_bytes: totalSizeBytes,
          top_variant_tags: [],
        }
  return { path: name, name, status, has_folder_preview: false, is_favorite: false }
}

function file(fileName: string, sizeBytes: number, variantTags?: VariantTag[]): FileEntry {
  return {
    id: fileName,
    file_name: fileName,
    extension: '.mp4',
    size_bytes: sizeBytes,
    modified_at: null,
    is_video_supported: true,
    is_image_supported: false,
    has_preview_asset: false,
    converted_at: null,
    tagged_at: null,
    is_variant: false,
    is_original: false,
    duration_seconds: null,
    variant_tags: variantTags,
  }
}

const names = <T extends { name: string }>(entries: T[]) => entries.map((entry) => entry.name)

describe('sortDirectories', () => {
  it('sorts by recursive folder size, largest first', () => {
    const input = [dir('small', 100), dir('big', 9000), dir('medium', 500)]
    expect(names(sortDirectories(input, 'size'))).toEqual(['big', 'medium', 'small'])
  })

  it('treats a folder with no fetched status as zero bytes', () => {
    // status is absent unless the listing was fetched with include_status=true
    // (e.g. the directory-search response) -- those must not outrank real sizes.
    const input = [dir('unknown'), dir('tiny', 1)]
    expect(names(sortDirectories(input, 'size'))).toEqual(['tiny', 'unknown'])
  })

  it('sorts alphabetically for name, and for tags (folders have no tag sort)', () => {
    const input = [dir('Zulu', 1), dir('alpha', 9000), dir('Mike', 500)]
    expect(names(sortDirectories(input, 'name'))).toEqual(['alpha', 'Mike', 'Zulu'])
    expect(names(sortDirectories(input, 'tags'))).toEqual(['alpha', 'Mike', 'Zulu'])
  })

  it('does not mutate the input array', () => {
    const input = [dir('small', 100), dir('big', 9000)]
    sortDirectories(input, 'size')
    expect(names(input)).toEqual(['small', 'big'])
  })
})

describe('sortFiles', () => {
  it('sorts by size, largest first', () => {
    const input = [file('a.mp4', 100), file('b.mp4', 9000), file('c.mp4', 500)]
    expect(sortFiles(input, 'size').map((f) => f.file_name)).toEqual(['b.mp4', 'c.mp4', 'a.mp4'])
  })

  it('sorts by file name', () => {
    const input = [file('c.mp4', 1), file('a.mp4', 9000), file('b.mp4', 500)]
    expect(sortFiles(input, 'name').map((f) => f.file_name)).toEqual(['a.mp4', 'b.mp4', 'c.mp4'])
  })

  it('sorts untagged files ahead of tagged ones, then by variant tag key', () => {
    const input = [
      file('crf28.mp4', 1, [{ param: 'crf', value: 28 }]),
      file('plain.mp4', 1),
      file('crf20.mp4', 1, [{ param: 'crf', value: 20 }]),
    ]
    expect(sortFiles(input, 'tags').map((f) => f.file_name)).toEqual([
      'plain.mp4',
      'crf20.mp4',
      'crf28.mp4',
    ])
  })

  it('does not mutate the input array', () => {
    const input = [file('a.mp4', 100), file('b.mp4', 9000)]
    sortFiles(input, 'size')
    expect(input.map((f) => f.file_name)).toEqual(['a.mp4', 'b.mp4'])
  })
})
