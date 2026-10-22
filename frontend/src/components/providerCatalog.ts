import type { ProviderType } from '../types/api'

export const PROVIDER_TYPES: ProviderType[] = ['openrouter', 'gemini', 'mistral', 'fal']
export const MODEL_LISTING_SUPPORTED: ProviderType[] = ['openrouter', 'gemini', 'mistral']
// Mirrors the backend's batch-capable provider set (`registry.entry_supports_batch`).
export const BATCH_SUPPORTED: ProviderType[] = ['gemini', 'mistral']
// Hand-picked, hardcoded model ids for FAL (user request), since FAL has no
// live model-catalog API to call (see `MODEL_LISTING_SUPPORTED` above and
// `backend/app/providers/fal.py`'s docstring -- each FAL model endpoint has
// its own bespoke schema, unlike OpenRouter/Gemini/Mistral). Two groups,
// both verified directly against fal.ai's/openrouter.ai's own docs:
// - "fal-ai/..." ids call that FAL app endpoint directly (small, dedicated
//   vision/VQA models, `{image_url, prompt}` request shape).
// - everything else routes through FAL's `openrouter/router/vision` gateway
//   instead (`{image_urls, model, prompt}` shape) -- general-purpose vision
//   LLMs with real reasoning ability, one per major vendor. `fal.py` picks
//   the request shape by checking for the "fal-ai/" prefix.
// Last verified 2026-10-22 against fal.ai/models/openrouter/router/vision's
// own model picker (its quick-pick list, which fal.ai keeps current as
// vendors release new models) -- request/response shape there is unchanged.
export const FAL_VISION_MODELS = [
  'fal-ai/moondream2/visual-query',
  'fal-ai/moondream3-preview/query',
  'openai/gpt-6-sol',
  'anthropic/claude-opus-5.5',
  'anthropic/claude-sonnet-5',
  'google/gemini-3.8-flash',
  'google/gemini-2.5-flash',
  'x-ai/grok-4.7',
  'deepseek/deepseek-v4.1-flash',
  'qwen/qwen3.8-max-0902',
  'z-ai/glm-5.3-flash',
  'moonshotai/kimi-k3',
  'minimax/minimax-m3',
  'mistralai/mistral-medium-3-5',
]
