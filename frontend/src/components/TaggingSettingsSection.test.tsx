// @vitest-environment jsdom
//
// Component test for the "preview what the model sees" demo added to
// Settings -> Tagging (TaggingSettingsSection.tsx): clicking the button
// should call POST /api/tagging-settings/preview with the current settings
// and render the returned image(s) at their real pixel size, or an error
// hint when there's no video to sample from. This is the one piece of this
// session's tagging-preview work with no backend-side coverage (the
// endpoint itself is tested in backend/tests/test_tagging_router.py).
//
// First component test in this repo -- see docs/development.md for the
// jsdom/@testing-library/react setup this required.
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n'
import { TagsProvider } from '../context/TagsContext'
import { recordRecentlyViewed } from '../utils/recentlyViewed'
import { TaggingSettingsSection } from './TaggingSettingsSection'

const SETTINGS = {
  sample_frame_count: 9,
  combine_into_collage: true,
  top_tag_count: 10,
  image_resolution: 360,
  updated_at: '2026-01-01T00:00:00Z',
}

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

function fetchRouter(handlers: Record<string, () => Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const method = init?.method ?? 'GET'
    const handler = handlers[`${method} ${url}`]
    if (!handler) {
      throw new Error(`Unhandled fetch in test: ${method} ${url}`)
    }
    return handler()
  })
}

describe('TaggingSettingsSection preview demo', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders the generated collage image and its pixel dimensions', async () => {
    recordRecentlyViewed('file-1')
    vi.stubGlobal(
      'fetch',
      fetchRouter({
        'GET /api/tags': () => jsonResponse({ tags: [] }),
        'GET /api/tagging-settings': () => jsonResponse(SETTINGS),
        'POST /api/tagging-settings/preview': () =>
          jsonResponse({
            images: [{ data_url: 'data:image/jpeg;base64,AAAA', width: 1080, height: 1080 }],
            combine_into_collage: true,
          }),
      }),
    )

    render(
      <TagsProvider>
        <TaggingSettingsSection />
      </TagsProvider>,
    )

    const button = await screen.findByRole('button', { name: /preview what the model sees/i })
    fireEvent.click(button)

    expect(await screen.findByText('1080×1080 px')).toBeTruthy()

    const img = document.querySelector<HTMLImageElement>('.tagging-preview__collage img')
    expect(img?.src).toBe('data:image/jpeg;base64,AAAA')
    expect(img?.width).toBe(1080)
  })

  it('renders one thumbnail per sampled frame when frames are sent separately', async () => {
    recordRecentlyViewed('file-1')
    vi.stubGlobal(
      'fetch',
      fetchRouter({
        'GET /api/tags': () => jsonResponse({ tags: [] }),
        'GET /api/tagging-settings': () => jsonResponse({ ...SETTINGS, combine_into_collage: false }),
        'POST /api/tagging-settings/preview': () =>
          jsonResponse({
            images: [0, 1, 2].map((i) => ({ data_url: `data:image/jpeg;base64,FRAME${i}`, width: 360, height: 202 })),
            combine_into_collage: false,
          }),
      }),
    )

    render(
      <TagsProvider>
        <TaggingSettingsSection />
      </TagsProvider>,
    )

    const button = await screen.findByRole('button', { name: /preview what the model sees/i })
    fireEvent.click(button)

    await screen.findAllByText('360×202 px')
    expect(document.querySelectorAll('.tagging-preview__frame img')).toHaveLength(3)
  })

  it('shows an error hint when there is no video available to preview', async () => {
    // Nothing recorded as recently viewed, and the fallback listing (used by
    // loadPreviewSampleFileIds()) comes back empty -- no video to sample.
    vi.stubGlobal(
      'fetch',
      fetchRouter({
        'GET /api/tags': () => jsonResponse({ tags: [] }),
        'GET /api/tagging-settings': () => jsonResponse(SETTINGS),
        'GET /api/files?video_only=true&limit=20': () => jsonResponse({ files: [] }),
      }),
    )

    render(
      <TagsProvider>
        <TaggingSettingsSection />
      </TagsProvider>,
    )

    const button = await screen.findByRole('button', { name: /preview what the model sees/i })
    fireEvent.click(button)

    expect(await screen.findByText(/no video available yet/i)).toBeTruthy()
  })
})
