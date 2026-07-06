from __future__ import annotations

import base64
import json
import math
import uuid
from io import BytesIO
from pathlib import Path
from urllib import error, request

import cv2
from PIL import Image, ImageDraw, ImageFont

from .db import connection
from .errors import ApiError
from .frame_sampling import unique_sample_indices
from .provider_settings_service import ProviderSettingsService
from .time_utils import utc_now


TAGGING_SECTION = "tagging"
DEFAULT_TAGGING_SETTINGS = {
    "provider": "openrouter",
    "sample_count": 9,
    "combine_frames": True,
    "prefer_batch": True,
}
BATCH_MAX_ITEMS = 6


class TaggingService:
    def __init__(self, database_path: Path, provider_settings_service: ProviderSettingsService) -> None:
        self._database_path = database_path
        self._provider_settings_service = provider_settings_service
        self._font = ImageFont.load_default()

    def get_settings(self) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute("SELECT payload FROM app_settings WHERE section = ?", (TAGGING_SECTION,)).fetchone()
        payload = {} if row is None else json.loads(row["payload"])
        settings = self._merge_settings_payload(payload)
        settings["vocabulary"] = self.list_vocabulary()
        return settings

    def update_settings(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Tagging settings payload must be a JSON object.", status=400)
        vocabulary_payload = payload.get("vocabulary")
        settings = self._merge_settings_payload(payload)
        if vocabulary_payload is not None:
            self._replace_vocabulary(vocabulary_payload)
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO app_settings (section, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (TAGGING_SECTION, json.dumps({key: settings[key] for key in DEFAULT_TAGGING_SETTINGS}), now, now),
            )
        return self.get_settings()

    def resolve_settings_snapshot(self) -> dict:
        settings = self.get_settings()
        provider = self._provider_settings_service.get_runtime_provider(settings["provider"])
        return {
            **settings,
            "provider_config": provider,
        }

    def list_vocabulary(self) -> list[dict]:
        with connection(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT id, tag_key, display_name, is_active, sort_order, created_at, updated_at
                FROM tag_catalog
                WHERE is_active = 1
                ORDER BY sort_order ASC, display_name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "tag_key": row["tag_key"],
                "display_name": row["display_name"],
                "is_active": bool(row["is_active"]),
                "sort_order": row["sort_order"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_file_tags(self, file_id: str) -> dict:
        with connection(self._database_path) as conn:
            file_row = conn.execute(
                """
                SELECT id, file_name, relative_path, tagging_updated_at, tagging_model_info
                FROM files
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
            if file_row is None:
                raise ApiError("file_not_found", "Requested file does not exist.", status=404)
            rows = conn.execute(
                """
                SELECT file_tags.confidence, file_tags.provider_name, file_tags.model_name, file_tags.assigned_at,
                       tag_catalog.tag_key, tag_catalog.display_name
                FROM file_tags
                JOIN tag_catalog ON tag_catalog.id = file_tags.tag_id
                WHERE file_tags.file_id = ?
                ORDER BY file_tags.confidence DESC, tag_catalog.display_name COLLATE NOCASE ASC
                """,
                (file_id,),
            ).fetchall()

        return {
            "file_id": file_id,
            "file_name": file_row["file_name"],
            "relative_path": file_row["relative_path"],
            "tagging_updated_at": file_row["tagging_updated_at"],
            "tagging_model_info": None if file_row["tagging_model_info"] is None else json.loads(file_row["tagging_model_info"]),
            "tags": [
                {
                    "tag_key": row["tag_key"],
                    "display_name": row["display_name"],
                    "confidence": round(float(row["confidence"]), 4),
                    "provider_name": row["provider_name"],
                    "model_name": row["model_name"],
                    "assigned_at": row["assigned_at"],
                }
                for row in rows
            ],
        }

    def tag_files(self, *, source_root: str, file_rows: list[dict], settings: dict) -> list[dict]:
        if not file_rows:
            return []

        vocabulary = settings.get("vocabulary")
        if not isinstance(vocabulary, list) or not vocabulary:
            raise ApiError("tagging_vocabulary_empty", "Configure at least one allowed tag before running tagging jobs.", status=400)

        provider = settings.get("provider_config")
        if not isinstance(provider, dict):
            provider = self._provider_settings_service.get_runtime_provider(settings.get("provider"))
        prefer_batch = bool(settings.get("prefer_batch")) and bool(provider.get("prefer_batch", True))

        prepared = [self._prepare_video_request(file_row, sample_count=settings["sample_count"], combine_frames=settings["combine_frames"]) for file_row in file_rows]
        results: list[dict] = []

        if prefer_batch and len(prepared) > 1:
            for index in range(0, len(prepared), BATCH_MAX_ITEMS):
                chunk = prepared[index : index + BATCH_MAX_ITEMS]
                results.extend(self._classify_batch(chunk, vocabulary=vocabulary, provider=provider))
        else:
            for item in prepared:
                results.append(self._classify_single(item, vocabulary=vocabulary, provider=provider))
        return results

    def _prepare_video_request(self, file_row: dict, *, sample_count: int, combine_frames: bool) -> dict:
        file_path = Path(file_row["path"])
        if not file_path.exists():
            return {
                "file_id": file_row["id"],
                "relative_path": file_row["relative_path"],
                "status": "failed",
                "error_code": "tagging_source_missing",
                "error_message": "The selected file is no longer available for tagging.",
            }

        images = self._sample_frames(file_path, sample_count=sample_count)
        if not images:
            return {
                "file_id": file_row["id"],
                "relative_path": file_row["relative_path"],
                "status": "failed",
                "error_code": "tagging_sampling_failed",
                "error_message": "No frames could be sampled from the selected video.",
            }

        if combine_frames:
            montage = self._build_montage(images, title=file_row["file_name"])
            encoded = self._image_to_data_url(montage)
            image_payloads = [encoded]
        else:
            image_payloads = [self._image_to_data_url(image) for image in images]

        return {
            "file_id": file_row["id"],
            "file_name": file_row["file_name"],
            "relative_path": file_row["relative_path"],
            "status": "pending",
            "image_payloads": image_payloads,
        }

    def _classify_batch(self, items: list[dict], *, vocabulary: list[dict], provider: dict) -> list[dict]:
        pending = [item for item in items if item["status"] == "pending"]
        completed = [self._normalize_terminal_result(item) for item in items if item["status"] != "pending"]
        if not pending:
            return completed

        prompt = {
            "instruction": "Select only tags from the allowed vocabulary. Return no free-form tags.",
            "videos": [{"relative_path": item["relative_path"]} for item in pending],
            "allowed_tags": [{"tag_key": tag["tag_key"], "display_name": tag["display_name"]} for tag in vocabulary],
            "response_schema": {
                "results": [
                    {
                        "relative_path": "string",
                        "selected_tags": [{"tag_key": "string", "confidence": "number 0..1"}],
                    }
                ]
            },
        }
        contents = []
        for item in pending:
            contents.append({"type": "text", "text": f"Video: {item['relative_path']}"})
            for image_url in item["image_payloads"]:
                contents.append({"type": "image_url", "image_url": image_url})
        response = self._run_provider_request(provider=provider, prompt=prompt, contents=contents, expect_batch=True)
        response_by_path = {entry["relative_path"]: entry for entry in response.get("results", []) if isinstance(entry, dict)}

        for item in pending:
            result = response_by_path.get(item["relative_path"], {"selected_tags": []})
            completed.append(self._persist_tag_result(item, result, vocabulary=vocabulary, provider=provider))
        return completed

    def _classify_single(self, item: dict, *, vocabulary: list[dict], provider: dict) -> dict:
        if item["status"] != "pending":
            return self._normalize_terminal_result(item)
        prompt = {
            "instruction": "Select only tags from the allowed vocabulary. Return no free-form tags.",
            "video": {"relative_path": item["relative_path"]},
            "allowed_tags": [{"tag_key": tag["tag_key"], "display_name": tag["display_name"]} for tag in vocabulary],
            "response_schema": {
                "selected_tags": [{"tag_key": "string", "confidence": "number 0..1"}],
            },
        }
        contents = [{"type": "text", "text": f"Video: {item['relative_path']}"}]
        contents.extend({"type": "image_url", "image_url": image_url} for image_url in item["image_payloads"])
        response = self._run_provider_request(provider=provider, prompt=prompt, contents=contents, expect_batch=False)
        return self._persist_tag_result(item, response, vocabulary=vocabulary, provider=provider)

    def _persist_tag_result(self, item: dict, response: dict, *, vocabulary: list[dict], provider: dict) -> dict:
        allowed = {tag["tag_key"]: tag for tag in vocabulary}
        selected = response.get("selected_tags")
        if not isinstance(selected, list):
            selected = []

        normalized_tags = []
        for entry in selected:
            if not isinstance(entry, dict):
                continue
            tag_key = entry.get("tag_key")
            if tag_key not in allowed:
                continue
            confidence = _normalize_confidence(entry.get("confidence"))
            normalized_tags.append(
                {
                    "tag_id": allowed[tag_key]["id"],
                    "tag_key": tag_key,
                    "display_name": allowed[tag_key]["display_name"],
                    "confidence": confidence,
                }
            )

        now = utc_now()
        model_name = provider["vision_model"]
        provider_name = provider["provider"]
        with connection(self._database_path) as conn, conn:
            conn.execute("DELETE FROM file_tags WHERE file_id = ?", (item["file_id"],))
            for tag in normalized_tags:
                conn.execute(
                    """
                    INSERT INTO file_tags (id, file_id, tag_id, confidence, provider_name, model_name, assigned_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), item["file_id"], tag["tag_id"], tag["confidence"], provider_name, model_name, now),
                )
            conn.execute(
                """
                UPDATE files
                SET tagging_updated_at = ?, tagging_model_info = ?, updated_at = ?, last_error_code = NULL, last_error_message = NULL
                WHERE id = ?
                """,
                (
                    now,
                    json.dumps({"provider": provider_name, "model": model_name, "sample_count": len(item.get("image_payloads", []))}),
                    now,
                    item["file_id"],
                ),
            )

        return {
            "file_id": item["file_id"],
            "relative_path": item["relative_path"],
            "status": "completed",
            "provider_name": provider_name,
            "model_name": model_name,
            "tags": normalized_tags,
            "tag_count": len(normalized_tags),
        }

    def _normalize_terminal_result(self, item: dict) -> dict:
        return {
            "file_id": item["file_id"],
            "relative_path": item["relative_path"],
            "status": item["status"],
            "error_code": item.get("error_code"),
            "error_message": item.get("error_message"),
            "tags": [],
            "tag_count": 0,
        }

    def _run_provider_request(self, *, provider: dict, prompt: dict, contents: list[dict], expect_batch: bool) -> dict:
        provider_name = provider["provider"]
        if provider_name == "openrouter":
            return self._call_openrouter(provider, prompt, contents)
        if provider_name == "gemini":
            return self._call_gemini(provider, prompt, contents)
        if provider_name == "mistral":
            return self._call_mistral(provider, prompt, contents)
        if provider_name == "fal":
            return self._call_fal(provider, prompt, contents)
        raise ApiError("provider_not_supported", f"Provider '{provider_name}' is not supported.", status=400)

    def _call_openrouter(self, provider: dict, prompt: dict, contents: list[dict]) -> dict:
        content_payload = [{"type": "text", "text": json.dumps(prompt)}]
        content_payload.extend(
            {"type": "image_url", "image_url": {"url": entry["image_url"]}} if entry["type"] == "image_url" else entry
            for entry in contents
        )
        payload = {
            "model": provider["vision_model"],
            "messages": [{"role": "user", "content": content_payload}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response = self._post_json(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {provider['api_key']}"},
            payload=payload,
        )
        text = response["choices"][0]["message"]["content"]
        return self._parse_json_text(text)

    def _call_gemini(self, provider: dict, prompt: dict, contents: list[dict]) -> dict:
        parts = [{"text": json.dumps(prompt)}]
        for entry in contents:
            if entry["type"] == "text":
                parts.append({"text": entry["text"]})
                continue
            prefix, encoded = entry["image_url"].split(",", 1)
            mime_type = prefix.removeprefix("data:").removesuffix(";base64")
            parts.append({"inline_data": {"mime_type": mime_type, "data": encoded}})
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "response_mime_type": "application/json",
            },
        }
        response = self._post_json(
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{provider['vision_model']}:generateContent?key={provider['api_key']}",
            headers={},
            payload=payload,
        )
        text = response["candidates"][0]["content"]["parts"][0]["text"]
        return self._parse_json_text(text)

    def _call_mistral(self, provider: dict, prompt: dict, contents: list[dict]) -> dict:
        content_payload = [{"type": "text", "text": json.dumps(prompt)}]
        for entry in contents:
            if entry["type"] == "text":
                content_payload.append(entry)
            else:
                content_payload.append({"type": "image_url", "image_url": entry["image_url"]})
        payload = {
            "model": provider["vision_model"],
            "messages": [{"role": "user", "content": content_payload}],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response = self._post_json(
            url="https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {provider['api_key']}"},
            payload=payload,
        )
        text = response["choices"][0]["message"]["content"]
        return self._parse_json_text(text)

    def _call_fal(self, provider: dict, prompt: dict, contents: list[dict]) -> dict:
        image_urls = [entry["image_url"] for entry in contents if entry["type"] == "image_url"]
        model_path = provider["vision_model"].strip()
        if not model_path:
            raise ApiError("provider_model_missing", "FAL tagging requires a configured vision model path.", status=400)
        url = model_path if model_path.startswith("http://") or model_path.startswith("https://") else f"https://queue.fal.run/{model_path}"
        payload = {
            "prompt": json.dumps(prompt),
            "image_urls": image_urls,
            "response_format": "json",
        }
        response = self._post_json(
            url=url,
            headers={"Authorization": f"Key {provider['api_key']}"},
            payload=payload,
        )
        if isinstance(response.get("output"), dict):
            return response["output"]
        if isinstance(response.get("result"), dict):
            return response["result"]
        if isinstance(response.get("data"), dict):
            return response["data"]
        raise ApiError("tagging_provider_invalid_response", "FAL did not return a JSON tagging payload.", status=502)

    def _post_json(self, *, url: str, headers: dict[str, str], payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **headers}
        req = request.Request(url, data=body, headers=request_headers, method="POST")
        try:
            with request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ApiError("tagging_provider_http_error", f"Provider request failed: {detail or exc.reason}", status=502) from exc
        except error.URLError as exc:
            raise ApiError("tagging_provider_unreachable", f"Provider request failed: {exc.reason}", status=502) from exc
        except json.JSONDecodeError as exc:
            raise ApiError("tagging_provider_invalid_response", "Provider returned invalid JSON.", status=502) from exc

    def _replace_vocabulary(self, payload: object) -> None:
        if not isinstance(payload, list):
            raise ApiError("invalid_request", "Field 'vocabulary' must be an array of tag labels.", status=400)

        normalized = []
        seen_keys = set()
        for index, value in enumerate(payload):
            if not isinstance(value, str) or not value.strip():
                raise ApiError("invalid_request", "Each vocabulary entry must be a non-empty string.", status=400)
            display_name = value.strip()
            tag_key = _slugify_tag(display_name)
            if not tag_key:
                raise ApiError("invalid_request", f"Vocabulary entry '{display_name}' does not produce a valid tag key.", status=400)
            if tag_key in seen_keys:
                raise ApiError("invalid_request", f"Vocabulary contains duplicate tag key '{tag_key}'.", status=400)
            seen_keys.add(tag_key)
            normalized.append((display_name, tag_key, index))

        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute("DELETE FROM file_tags")
            conn.execute("UPDATE files SET tagging_updated_at = NULL, tagging_model_info = NULL, updated_at = ?", (now,))
            conn.execute("DELETE FROM tag_catalog")
            for display_name, tag_key, sort_order in normalized:
                conn.execute(
                    """
                    INSERT INTO tag_catalog (id, tag_key, display_name, is_active, sort_order, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), tag_key, display_name, sort_order, now, now),
                )

    def _merge_settings_payload(self, payload: object) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Tagging settings payload must be a JSON object.", status=400)
        provider = payload.get("provider", DEFAULT_TAGGING_SETTINGS["provider"])
        if provider not in {"openrouter", "gemini", "fal", "mistral"}:
            raise ApiError("invalid_request", "Field 'provider' must be one of openrouter, gemini, fal, or mistral.", status=400)
        combine_frames = payload.get("combine_frames", DEFAULT_TAGGING_SETTINGS["combine_frames"])
        prefer_batch = payload.get("prefer_batch", DEFAULT_TAGGING_SETTINGS["prefer_batch"])
        if not isinstance(combine_frames, bool):
            raise ApiError("invalid_request", "Field 'combine_frames' must be a boolean.", status=400)
        if not isinstance(prefer_batch, bool):
            raise ApiError("invalid_request", "Field 'prefer_batch' must be a boolean.", status=400)
        sample_count = payload.get("sample_count", DEFAULT_TAGGING_SETTINGS["sample_count"])
        if not isinstance(sample_count, int) or sample_count < 3 or sample_count > 24:
            raise ApiError("invalid_request", "Field 'sample_count' must be an integer between 3 and 24.", status=400)
        return {
            "provider": provider,
            "sample_count": sample_count,
            "combine_frames": combine_frames,
            "prefer_batch": prefer_batch,
        }

    def _sample_frames(self, file_path: Path, *, sample_count: int) -> list[Image.Image]:
        capture = cv2.VideoCapture(str(file_path))
        if not capture.isOpened():
            raise ApiError("tagging_open_failed", f"Unable to open {file_path.name} for tagging.", status=500)
        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frame_count <= 0:
                raise ApiError("tagging_probe_failed", f"Unable to determine frame count for {file_path.name}.", status=500)
            images = []
            for frame_index in unique_sample_indices(frame_count=frame_count, sample_count=sample_count):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                images.append(Image.fromarray(rgb))
            return images
        finally:
            capture.release()

    def _build_montage(self, images: list[Image.Image], *, title: str) -> Image.Image:
        columns = 3
        rows = max(1, math.ceil(len(images) / columns))
        cell_width = 220
        cell_height = 124
        gap = 10
        header = 28
        canvas = Image.new("RGB", (columns * cell_width + (columns + 1) * gap, rows * cell_height + (rows + 1) * gap + header), (20, 24, 32))
        draw = ImageDraw.Draw(canvas)
        draw.text((gap, 6), title, font=self._font, fill=(235, 239, 244))
        for index, image in enumerate(images):
            row = index // columns
            column = index % columns
            x = gap + column * (cell_width + gap)
            y = header + gap + row * (cell_height + gap)
            fitted = image.copy()
            fitted.thumbnail((cell_width, cell_height))
            offset_x = x + (cell_width - fitted.width) // 2
            offset_y = y + (cell_height - fitted.height) // 2
            canvas.paste(fitted, (offset_x, offset_y))
        return canvas

    def _image_to_data_url(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=86)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def _parse_json_text(self, value: str) -> dict:
        if not isinstance(value, str):
            raise ApiError("tagging_provider_invalid_response", "Provider returned a non-text response.", status=502)
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ApiError("tagging_provider_invalid_response", "Provider returned invalid JSON tagging output.", status=502) from exc
        if not isinstance(parsed, dict):
            raise ApiError("tagging_provider_invalid_response", "Provider tagging output must be a JSON object.", status=502)
        return parsed


def _slugify_tag(value: str) -> str:
    lowered = value.strip().lower()
    chars = []
    last_was_sep = False
    for char in lowered:
        if char.isalnum():
            chars.append(char)
            last_was_sep = False
        elif not last_was_sep:
            chars.append("_")
            last_was_sep = True
    return "".join(chars).strip("_")


def _normalize_confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    confidence = float(value)
    if confidence > 1.0:
        confidence /= 100.0
    return round(max(0.0, min(1.0, confidence)), 4)
