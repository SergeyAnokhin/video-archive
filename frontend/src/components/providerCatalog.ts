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
export const FAL_VISION_MODELS = [
  'fal-ai/moondream2/visual-query',
  'fal-ai/moondream3-preview/query',
  'anthropic/claude-sonnet-4.5',
  'openai/gpt-5',
  'google/gemini-2.5-flash',
  'meta-llama/llama-3.2-90b-vision-instruct',
  'qwen/qwen2.5-vl-72b-instruct',
  'mistralai/pixtral-12b',
]
