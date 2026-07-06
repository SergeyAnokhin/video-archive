from __future__ import annotations

import base64
import io
import json
import math
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy
from PIL import Image, ImageDraw, ImageFont

from .db import connection
from .errors import ApiError
from .frame_sampling import preview_sample_indices
from .preview_layout import (
    ASPECT_RATIO_PRESETS,
    DEFAULT_LAYOUT_DEFINITION,
    DEFAULT_PRESET_ID,
    DEFAULT_PREVIEW_SETTINGS,
    LAYOUT_VERSION,
    TIMELINE_FLOW_MODES,
    build_preview_layout,
    coerce_int,
    frame_to_tile_image,
    order_frames_for_flow,
    parent_directory,
    resize_for_detector,
)
from .time_utils import utc_now


PREVIEW_SECTION = "preview"


@dataclass
class _FrameAnalysis:
    sample_index: int
    frame_index: int
    timestamp_seconds: float
    image_bgr: numpy.ndarray
    face_count: int
    largest_face_ratio: float
    body_count: int
    largest_body_ratio: float
    max_body_weight: float
    blur_score: float

    @property
    def face_score(self) -> float:
        return (self.largest_face_ratio * 140.0) + (self.face_count * 8.0) + min(self.blur_score / 150.0, 8.0)

    @property
    def body_score(self) -> float:
        return (self.largest_body_ratio * 120.0) + (self.body_count * 10.0) + (self.max_body_weight * 6.0) + min(self.blur_score / 180.0, 6.0)

    @property
    def fallback_score(self) -> float:
        return max(self.face_score, self.body_score) + min(self.blur_score / 120.0, 10.0)


class PreviewService:
    def __init__(self, database_path: Path, data_dir: Path) -> None:
        self._database_path = database_path
        self._preview_dir = data_dir / "previews"
        self._preview_dir.mkdir(parents=True, exist_ok=True)
        self._face_cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        self._body_detector = cv2.HOGDescriptor()
        self._body_detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self._font = ImageFont.load_default()

    def get_settings(self) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute(
                "SELECT payload FROM app_settings WHERE section = ?",
                (PREVIEW_SECTION,),
            ).fetchone()
        payload = {} if row is None else json.loads(row["payload"])
        return self._merge_preview_settings(payload)

    def update_settings(self, payload: dict) -> dict:
        settings = self._merge_preview_settings(payload)
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO app_settings (section, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (PREVIEW_SECTION, json.dumps(settings), now, now),
            )
        return settings

    def resolve_settings_snapshot(self) -> dict:
        settings = self.get_settings()
        preset = self.get_layout_preset(settings["layout_preset_id"])
        return {
            **settings,
            "preset": preset,
            "layout_definition": preset["layout_definition"],
            "layout_version": LAYOUT_VERSION,
        }

    def list_layout_presets(self) -> list[dict]:
        with connection(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT id, name, timeline_flow, sample_count, large_tile_count,
                       identity_diversity_enabled, layout_definition, is_default,
                       created_at, updated_at
                FROM preview_layout_presets
                ORDER BY is_default DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()
        return [self._serialize_preset_row(row) for row in rows]

    def get_layout_preset(self, preset_id: str | None) -> dict:
        target_id = preset_id or DEFAULT_PRESET_ID
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, name, timeline_flow, sample_count, large_tile_count,
                       identity_diversity_enabled, layout_definition, is_default,
                       created_at, updated_at
                FROM preview_layout_presets
                WHERE id = ?
                """,
                (target_id,),
            ).fetchone()
        if row is None:
            raise ApiError("preview_preset_not_found", "Requested preview preset does not exist.", status=404)
        return self._serialize_preset_row(row)

    def create_layout_preset(self, payload: dict) -> dict:
        preset = self._validate_preset_payload(payload, allow_partial=False)
        now = utc_now()
        preset_id = str(uuid.uuid4())
        is_default = bool(preset.get("is_default", False))
        with connection(self._database_path) as conn, conn:
            if is_default:
                conn.execute("UPDATE preview_layout_presets SET is_default = 0 WHERE is_default = 1")
            conn.execute(
                """
                INSERT INTO preview_layout_presets (
                    id, name, timeline_flow, sample_count, large_tile_count,
                    identity_diversity_enabled, layout_definition, is_default,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preset_id,
                    preset["name"],
                    preset["timeline_flow"],
                    preset["sample_count"],
                    preset["large_tile_count"],
                    int(preset["identity_diversity_enabled"]),
                    json.dumps(preset["layout_definition"]),
                    int(is_default),
                    now,
                    now,
                ),
            )
        return self.get_layout_preset(preset_id)

    def update_layout_preset(self, preset_id: str, payload: dict) -> dict:
        current = self.get_layout_preset(preset_id)
        merged = {
            **current,
            **payload,
            "layout_definition": payload.get("layout_definition", current["layout_definition"]),
        }
        preset = self._validate_preset_payload(merged, allow_partial=False)
        is_default = bool(preset.get("is_default", current["is_default"]))
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            if is_default:
                conn.execute("UPDATE preview_layout_presets SET is_default = 0 WHERE is_default = 1 AND id <> ?", (preset_id,))
            conn.execute(
                """
                UPDATE preview_layout_presets
                SET name = ?, timeline_flow = ?, sample_count = ?, large_tile_count = ?,
                    identity_diversity_enabled = ?, layout_definition = ?, is_default = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    preset["name"],
                    preset["timeline_flow"],
                    preset["sample_count"],
                    preset["large_tile_count"],
                    int(preset["identity_diversity_enabled"]),
                    json.dumps(preset["layout_definition"]),
                    int(is_default),
                    now,
                    preset_id,
                ),
            )
        return self.get_layout_preset(preset_id)

    def delete_layout_preset(self, preset_id: str) -> None:
        if preset_id == DEFAULT_PRESET_ID:
            raise ApiError("preview_preset_protected", "The default preview preset cannot be deleted.", status=409)
        with connection(self._database_path) as conn, conn:
            deleted = conn.execute("DELETE FROM preview_layout_presets WHERE id = ?", (preset_id,))
        if deleted.rowcount != 1:
            raise ApiError("preview_preset_not_found", "Requested preview preset does not exist.", status=404)

    def build_live_preview(self, payload: dict | None = None) -> dict:
        base_settings = self.get_settings()
        overrides = payload or {}
        merged = self._merge_preview_settings({**base_settings, **overrides})
        preset = self.get_layout_preset(merged["layout_preset_id"])
        layout = self._build_layout(
            sample_count=merged["sample_count"],
            large_tile_count=merged["large_tile_count"],
            timeline_flow=merged["timeline_flow"],
            aspect_ratio_preset=merged["aspect_ratio_preset"],
        )
        image = self._render_placeholder_layout(layout)
        return {
            "settings": merged,
            "preset": preset,
            "layout": layout,
            "image_data_url": self._image_to_data_url(image),
        }

    def generate_file_preview(self, *, source_root: str, file_row: dict, settings: dict) -> dict:
        file_path = Path(file_row["path"])
        if not file_path.exists():
            raise ApiError("preview_source_missing", "The selected file is no longer available for preview generation.", status=404)

        analyses = self._sample_video(file_path, sample_count=settings["sample_count"])
        if not analyses:
            raise ApiError("preview_sampling_failed", "No frames could be sampled from the selected video.", status=500)

        layout = self._build_layout(
            sample_count=len(analyses),
            large_tile_count=min(settings["large_tile_count"], len(analyses)),
            timeline_flow=settings["timeline_flow"],
            aspect_ratio_preset=settings["aspect_ratio_preset"],
        )
        ordered_frames, large_tile_timestamps = self._select_frames_for_layout(
            analyses=analyses,
            large_tile_count=layout["large_tile_count"],
            identity_diversity_enabled=settings["identity_diversity_enabled"],
            timeline_flow=settings["timeline_flow"],
        )
        collage = self._render_collage(layout, ordered_frames, file_row["file_name"])
        output_path = self._preview_dir / "files" / f"{file_row['id']}.jpg"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        collage.save(output_path, format="JPEG", quality=88)

        face_summary = {
            "max_face_count": max(frame.face_count for frame in analyses),
            "max_face_ratio": round(max(frame.largest_face_ratio for frame in analyses), 6),
            "samples_with_faces": sum(1 for frame in analyses if frame.face_count > 0),
        }
        body_summary = {
            "max_body_count": max(frame.body_count for frame in analyses),
            "max_body_ratio": round(max(frame.largest_body_ratio for frame in analyses), 6),
            "samples_with_bodies": sum(1 for frame in analyses if frame.body_count > 0),
        }
        metadata = {
            "scope_type": "file",
            "file_id": file_row["id"],
            "relative_path": file_row["relative_path"],
            "file_name": file_row["file_name"],
            "sample_count": len(analyses),
            "large_tile_count": layout["large_tile_count"],
            "timeline_flow": settings["timeline_flow"],
            "identity_diversity_enabled": settings["identity_diversity_enabled"],
            "aspect_ratio_preset": settings["aspect_ratio_preset"],
            "layout": layout,
            "keyframe_timestamps": [round(frame.timestamp_seconds, 3) for frame in analyses],
            "large_tile_timestamps": [round(value, 3) for value in large_tile_timestamps],
            "face_detection_summary": face_summary,
            "body_detection_summary": body_summary,
            "layout_version": LAYOUT_VERSION,
        }
        self._store_file_preview_asset(
            source_id=file_row["source_id"],
            file_id=file_row["id"],
            relative_path=file_row["relative_path"],
            image_path=output_path,
            metadata=metadata,
        )
        return {
            "output_ref": str(output_path),
            "metadata": metadata,
        }

    def generate_directory_preview(
        self,
        *,
        source_id: str,
        source_root: str,
        relative_path: str,
        settings: dict,
        file_rows: list[dict],
    ) -> dict | None:
        if not file_rows:
            return None

        candidates: list[_FrameAnalysis] = []
        for sample_index, file_row in enumerate(file_rows):
            preview = self.get_file_preview(file_row["id"], include_image_data=False)
            if preview is None:
                continue
            metadata = preview["metadata"]
            timestamps = metadata.get("large_tile_timestamps") or metadata.get("keyframe_timestamps") or []
            if not timestamps:
                continue
            frame = self._read_specific_frame(Path(file_row["path"]), float(timestamps[0]))
            if frame is None:
                continue
            image_bgr = frame
            analysis = self._analyze_frame(image_bgr, sample_index=sample_index, frame_index=sample_index, timestamp_seconds=float(timestamps[0]))
            candidates.append(analysis)

        if not candidates:
            return None

        sample_count = min(settings["sample_count"], len(candidates))
        candidates = candidates[:sample_count]
        layout = self._build_layout(
            sample_count=sample_count,
            large_tile_count=min(settings["large_tile_count"], sample_count),
            timeline_flow=settings["timeline_flow"],
            aspect_ratio_preset=settings["aspect_ratio_preset"],
        )
        ordered_frames, large_tile_timestamps = self._select_frames_for_layout(
            analyses=candidates,
            large_tile_count=layout["large_tile_count"],
            identity_diversity_enabled=settings["identity_diversity_enabled"],
            timeline_flow=settings["timeline_flow"],
        )
        title = relative_path or "Library root"
        collage = self._render_collage(layout, ordered_frames, title)
        output_path = self._preview_dir / "directories" / (relative_path.replace("/", "__") or "root")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path = output_path.with_suffix(".jpg")
        collage.save(output_path, format="JPEG", quality=88)
        metadata = {
            "scope_type": "directory",
            "relative_path": relative_path,
            "sample_count": sample_count,
            "large_tile_count": layout["large_tile_count"],
            "timeline_flow": settings["timeline_flow"],
            "identity_diversity_enabled": settings["identity_diversity_enabled"],
            "aspect_ratio_preset": settings["aspect_ratio_preset"],
            "layout": layout,
            "keyframe_timestamps": [round(frame.timestamp_seconds, 3) for frame in candidates],
            "large_tile_timestamps": [round(value, 3) for value in large_tile_timestamps],
            "layout_version": LAYOUT_VERSION,
            "video_count": len(file_rows),
        }
        self._store_directory_preview_asset(
            source_id=source_id,
            relative_path=relative_path,
            image_path=output_path,
            metadata=metadata,
        )
        return {
            "output_ref": str(output_path),
            "metadata": metadata,
        }

    def get_file_preview(self, file_id: str, *, include_image_data: bool = True) -> dict | None:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT preview_assets.image_path, preview_assets.metadata
                FROM preview_assets
                WHERE preview_assets.asset_kind = 'file' AND preview_assets.file_id = ?
                """,
                (file_id,),
            ).fetchone()
        if row is None:
            return None
        return self._serialize_preview_asset_row(row, include_image_data=include_image_data)

    def get_directory_preview(self, source_id: str, relative_path: str, *, include_image_data: bool = True) -> dict | None:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT image_path, metadata
                FROM preview_assets
                WHERE asset_kind = 'directory' AND source_id = ? AND directory_relative_path = ?
                """,
                (source_id, relative_path),
            ).fetchone()
        if row is None:
            return None
        return self._serialize_preview_asset_row(row, include_image_data=include_image_data)

    def clear_file_preview(self, file_id: str) -> None:
        with connection(self._database_path) as conn, conn:
            conn.execute("DELETE FROM preview_assets WHERE asset_kind = 'file' AND file_id = ?", (file_id,))

    def clear_directory_previews_for_subtree(self, source_id: str, relative_path: str) -> None:
        with connection(self._database_path) as conn, conn:
            if relative_path:
                conn.execute(
                    """
                    DELETE FROM preview_assets
                    WHERE asset_kind = 'directory' AND source_id = ?
                      AND (directory_relative_path = ? OR directory_relative_path LIKE ?)
                    """,
                    (source_id, relative_path, f"{relative_path}/%"),
                )
            else:
                conn.execute(
                    "DELETE FROM preview_assets WHERE asset_kind = 'directory' AND source_id = ?",
                    (source_id,),
                )

    def _sample_video(self, file_path: Path, *, sample_count: int) -> list[_FrameAnalysis]:
        capture = cv2.VideoCapture(str(file_path))
        if not capture.isOpened():
            raise ApiError("preview_open_failed", f"Unable to open {file_path.name} for preview generation.", status=500)

        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            if frame_count <= 0:
                raise ApiError("preview_probe_failed", f"Unable to determine frame count for {file_path.name}.", status=500)

            indices = preview_sample_indices(frame_count=frame_count, sample_count=sample_count)
            analyses: list[_FrameAnalysis] = []
            for sample_index, frame_index in enumerate(indices):
                frame = self._read_frame(capture, frame_index)
                if frame is None:
                    continue
                timestamp_seconds = 0.0 if fps <= 0 else frame_index / fps
                analyses.append(
                    self._analyze_frame(
                        frame,
                        sample_index=sample_index,
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                    )
                )
            return analyses
        finally:
            capture.release()

    def _analyze_frame(
        self,
        image_bgr: numpy.ndarray,
        *,
        sample_index: int,
        frame_index: int,
        timestamp_seconds: float,
    ) -> _FrameAnalysis:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        frame_area = max(width * height, 1)

        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        largest_face_ratio = 0.0
        for (_, _, face_width, face_height) in faces:
            largest_face_ratio = max(largest_face_ratio, (face_width * face_height) / frame_area)

        body_input, scale_ratio = resize_for_detector(rgb, max_side=720)
        bodies, weights = self._body_detector.detectMultiScale(
            body_input,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.05,
        )
        largest_body_ratio = 0.0
        max_body_weight = 0.0
        for body_index, (_, _, body_width, body_height) in enumerate(bodies):
            body_area = (body_width / scale_ratio) * (body_height / scale_ratio)
            largest_body_ratio = max(largest_body_ratio, body_area / frame_area)
            if body_index < len(weights):
                max_body_weight = max(max_body_weight, float(weights[body_index]))

        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        return _FrameAnalysis(
            sample_index=sample_index,
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            image_bgr=image_bgr,
            face_count=len(faces),
            largest_face_ratio=largest_face_ratio,
            body_count=len(bodies),
            largest_body_ratio=largest_body_ratio,
            max_body_weight=max_body_weight,
            blur_score=blur_score,
        )

    def _select_frames_for_layout(
        self,
        *,
        analyses: list[_FrameAnalysis],
        large_tile_count: int,
        identity_diversity_enabled: bool,
        timeline_flow: str,
    ) -> tuple[list[_FrameAnalysis], list[float]]:
        remaining = list(analyses)
        large_frames: list[_FrameAnalysis] = []

        face_candidates = sorted(
            [frame for frame in remaining if frame.face_count > 0],
            key=lambda frame: (-frame.face_score, frame.sample_index),
        )
        body_candidates = sorted(
            [frame for frame in remaining if frame.body_count > 0],
            key=lambda frame: (-frame.body_score, frame.sample_index),
        )
        fallback_candidates = sorted(
            remaining,
            key=lambda frame: (-frame.fallback_score, frame.sample_index),
        )

        for slot_index in range(large_tile_count):
            chosen = None
            if slot_index < 2:
                chosen = self._pick_face_priority_frame(
                    large_frames=large_frames,
                    face_candidates=face_candidates,
                    fallback_candidates=fallback_candidates,
                    identity_diversity_enabled=identity_diversity_enabled,
                )
            else:
                chosen = self._pick_figure_priority_frame(
                    large_frames=large_frames,
                    body_candidates=body_candidates,
                    face_candidates=face_candidates,
                    fallback_candidates=fallback_candidates,
                )
            if chosen is None:
                break
            large_frames.append(chosen)
            remaining = [frame for frame in remaining if frame.frame_index != chosen.frame_index]
            face_candidates = [frame for frame in face_candidates if frame.frame_index != chosen.frame_index]
            body_candidates = [frame for frame in body_candidates if frame.frame_index != chosen.frame_index]
            fallback_candidates = [frame for frame in fallback_candidates if frame.frame_index != chosen.frame_index]

        small_frames = order_frames_for_flow(remaining, timeline_flow)
        ordered_frames = large_frames + small_frames
        return ordered_frames, [frame.timestamp_seconds for frame in large_frames]

    def _pick_face_priority_frame(
        self,
        *,
        large_frames: list[_FrameAnalysis],
        face_candidates: list[_FrameAnalysis],
        fallback_candidates: list[_FrameAnalysis],
        identity_diversity_enabled: bool,
    ) -> _FrameAnalysis | None:
        if not face_candidates:
            return fallback_candidates[0] if fallback_candidates else None
        if not identity_diversity_enabled or not large_frames:
            return face_candidates[0]

        prior = large_frames[0]
        min_distance = max(1, math.ceil((len(face_candidates) + len(large_frames)) / 3))
        distant = [frame for frame in face_candidates if abs(frame.sample_index - prior.sample_index) >= min_distance]
        if distant:
            return distant[0]
        return max(face_candidates, key=lambda frame: (abs(frame.sample_index - prior.sample_index), frame.face_score))

    def _pick_figure_priority_frame(
        self,
        *,
        large_frames: list[_FrameAnalysis],
        body_candidates: list[_FrameAnalysis],
        face_candidates: list[_FrameAnalysis],
        fallback_candidates: list[_FrameAnalysis],
    ) -> _FrameAnalysis | None:
        if body_candidates:
            return body_candidates[0]
        if face_candidates:
            return face_candidates[0]
        return fallback_candidates[0] if fallback_candidates else None

    def _render_collage(self, layout: dict, ordered_frames: list[_FrameAnalysis], title: str) -> Image.Image:
        canvas = Image.new("RGB", (layout["canvas_width"], layout["canvas_height"] + 40), color=(8, 17, 30))
        draw = ImageDraw.Draw(canvas)
        draw.text((16, 12), title, fill=(233, 242, 255), font=self._font)
        for tile, frame in zip(layout["tiles"], ordered_frames, strict=False):
            tile_image = frame_to_tile_image(frame.image_bgr, tile["width"], tile["height"])
            canvas.paste(tile_image, (tile["x"], tile["y"] + 40))
        return canvas

    def _render_placeholder_layout(self, layout: dict) -> Image.Image:
        canvas = Image.new("RGB", (layout["canvas_width"], layout["canvas_height"]), color=(7, 17, 31))
        draw = ImageDraw.Draw(canvas)
        for tile in layout["tiles"]:
            color = (67, 122, 220) if tile["is_large"] else (34, 67, 110)
            draw.rounded_rectangle(
                (tile["x"], tile["y"], tile["x"] + tile["width"], tile["y"] + tile["height"]),
                radius=16,
                fill=color,
                outline=(158, 189, 235),
                width=2,
            )
            label = f"{'Large' if tile['is_large'] else 'Frame'} {tile['slot_index'] + 1}"
            draw.text((tile["x"] + 12, tile["y"] + 12), label, fill=(241, 246, 255), font=self._font)
        return canvas

    def _store_file_preview_asset(self, *, source_id: str, file_id: str, relative_path: str, image_path: Path, metadata: dict) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO preview_assets (
                    id, source_id, asset_kind, file_id, directory_relative_path, image_path, metadata, created_at, updated_at
                ) VALUES (?, ?, 'file', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    image_path = excluded.image_path,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
                """,
                (
                    str(uuid.uuid4()),
                    source_id,
                    file_id,
                    parent_directory(relative_path),
                    str(image_path),
                    json.dumps(metadata),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE files
                SET preview_state = 'done', preview_generated_at = ?, has_preview_assets = 1,
                    keyframe_timestamps = ?, large_tile_timestamps = ?, face_detection_summary = ?,
                    body_detection_summary = ?, preview_layout_version = ?, preview_asset_path = ?,
                    last_error_code = NULL, last_error_message = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    now,
                    json.dumps(metadata["keyframe_timestamps"]),
                    json.dumps(metadata["large_tile_timestamps"]),
                    json.dumps(metadata["face_detection_summary"]),
                    json.dumps(metadata["body_detection_summary"]),
                    metadata["layout_version"],
                    str(image_path),
                    now,
                    file_id,
                ),
            )

    def _store_directory_preview_asset(self, *, source_id: str, relative_path: str, image_path: Path, metadata: dict) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            existing = conn.execute(
                """
                SELECT id
                FROM preview_assets
                WHERE asset_kind = 'directory' AND source_id = ? AND directory_relative_path = ?
                """,
                (source_id, relative_path),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO preview_assets (
                        id, source_id, asset_kind, file_id, directory_relative_path, image_path, metadata, created_at, updated_at
                    ) VALUES (?, ?, 'directory', NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        source_id,
                        relative_path,
                        str(image_path),
                        json.dumps(metadata),
                        now,
                        now,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE preview_assets
                    SET image_path = ?, metadata = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (str(image_path), json.dumps(metadata), now, existing["id"]),
                )

    def _serialize_preview_asset_row(self, row, *, include_image_data: bool) -> dict:
        image_path = Path(row["image_path"])
        metadata = json.loads(row["metadata"])
        payload = {
            "image_path": str(image_path),
            "metadata": metadata,
        }
        if include_image_data:
            payload["image_data_url"] = self._image_file_to_data_url(image_path)
        return payload

    def _merge_preview_settings(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Preview settings payload must be a JSON object.", status=400)
        preset_id = payload.get("layout_preset_id", DEFAULT_PRESET_ID)
        if preset_id is not None and not isinstance(preset_id, str):
            raise ApiError("invalid_request", "Field 'layout_preset_id' must be a string when provided.", status=400)
        sample_count = coerce_int(payload.get("sample_count", DEFAULT_PREVIEW_SETTINGS["sample_count"]), "sample_count", minimum=3, maximum=24)
        large_tile_count = coerce_int(payload.get("large_tile_count", DEFAULT_PREVIEW_SETTINGS["large_tile_count"]), "large_tile_count", minimum=0, maximum=6)
        if large_tile_count > sample_count:
            raise ApiError("invalid_request", "Field 'large_tile_count' cannot exceed 'sample_count'.", status=400)
        timeline_flow = payload.get("timeline_flow", DEFAULT_PREVIEW_SETTINGS["timeline_flow"])
        if timeline_flow not in TIMELINE_FLOW_MODES:
            raise ApiError("invalid_request", "Field 'timeline_flow' must be 'row', 'column', or 'shuffle'.", status=400)
        identity_diversity_enabled = payload.get("identity_diversity_enabled", DEFAULT_PREVIEW_SETTINGS["identity_diversity_enabled"])
        if not isinstance(identity_diversity_enabled, bool):
            raise ApiError("invalid_request", "Field 'identity_diversity_enabled' must be a boolean.", status=400)
        aspect_ratio_preset = payload.get("aspect_ratio_preset", DEFAULT_PREVIEW_SETTINGS["aspect_ratio_preset"])
        if aspect_ratio_preset not in ASPECT_RATIO_PRESETS:
            raise ApiError(
                "invalid_request",
                "Field 'aspect_ratio_preset' must be one of: square, video, portrait, s24, ultrawide.",
                status=400,
            )
        return {
            "sample_count": sample_count,
            "large_tile_count": large_tile_count,
            "timeline_flow": timeline_flow,
            "identity_diversity_enabled": identity_diversity_enabled,
            "aspect_ratio_preset": aspect_ratio_preset,
            "layout_preset_id": (preset_id or DEFAULT_PRESET_ID).strip() or DEFAULT_PRESET_ID,
        }

    def _validate_preset_payload(self, payload: dict, *, allow_partial: bool) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Preview preset payload must be a JSON object.", status=400)
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ApiError("invalid_request", "Field 'name' must be a non-empty string.", status=400)
        settings = self._merge_preview_settings(payload)
        layout_definition = payload.get("layout_definition", DEFAULT_LAYOUT_DEFINITION)
        if not isinstance(layout_definition, dict):
            raise ApiError("invalid_request", "Field 'layout_definition' must be a JSON object.", status=400)
        layout_definition = {
            **layout_definition,
            "aspect_ratio_preset": settings["aspect_ratio_preset"],
        }
        is_default = payload.get("is_default", False)
        if not isinstance(is_default, bool):
            raise ApiError("invalid_request", "Field 'is_default' must be a boolean when provided.", status=400)
        return {
            "name": name.strip(),
            **settings,
            "layout_definition": layout_definition,
            "is_default": is_default,
        }

    def _serialize_preset_row(self, row) -> dict:
        layout_definition = json.loads(row["layout_definition"])
        return {
            "id": row["id"],
            "name": row["name"],
            "timeline_flow": row["timeline_flow"],
            "sample_count": row["sample_count"],
            "large_tile_count": row["large_tile_count"],
            "identity_diversity_enabled": bool(row["identity_diversity_enabled"]),
            "aspect_ratio_preset": layout_definition.get("aspect_ratio_preset", DEFAULT_PREVIEW_SETTINGS["aspect_ratio_preset"]),
            "layout_definition": layout_definition,
            "is_default": bool(row["is_default"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _read_frame(self, capture: cv2.VideoCapture, frame_index: int) -> numpy.ndarray | None:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if ok and frame is not None:
            return frame
        for delta in (1, -1, 2, -2):
            capture.set(cv2.CAP_PROP_POS_FRAMES, max(frame_index + delta, 0))
            ok, frame = capture.read()
            if ok and frame is not None:
                return frame
        return None

    def _read_specific_frame(self, file_path: Path, timestamp_seconds: float) -> numpy.ndarray | None:
        capture = cv2.VideoCapture(str(file_path))
        if not capture.isOpened():
            return None
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_index = 0 if fps <= 0 else max(0, int(timestamp_seconds * fps))
            return self._read_frame(capture, frame_index)
        finally:
            capture.release()

    def _image_to_data_url(self, image: Image.Image) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _image_file_to_data_url(self, image_path: Path) -> str:
        if not image_path.exists():
            raise ApiError("preview_asset_missing", "Preview image is no longer available on disk.", status=404)
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/jpeg;base64,{encoded}"

    def _build_layout(self, *, sample_count: int, large_tile_count: int, timeline_flow: str, aspect_ratio_preset: str) -> dict:
        return build_preview_layout(
            sample_count=sample_count,
            large_tile_count=large_tile_count,
            timeline_flow=timeline_flow,
            aspect_ratio_preset=aspect_ratio_preset,
        )
