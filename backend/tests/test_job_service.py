from __future__ import annotations

import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from app.conversion_profile_service import ConversionProfileService
from app.conversion_service import ConversionService
from app.db import initialize_database
from app.provider_settings_service import ProviderSettingsService
from app.job_service import JobService
from app.library_service import LibraryService
from app.preview_service import PreviewService
from app.secrets import SecretStore
from app.source_service import SourceService, parse_source_payload
from app.tagging_service import TaggingService


class JobServiceTests(unittest.TestCase):
    def test_scan_job_persists_items_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            (source_root / "family" / "2024").mkdir(parents=True)
            (source_root / "family" / "2024" / "Beach Sunset.mp4").write_bytes(b"video-data")

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_scan_job()
            completed = _wait_for_terminal_status(job_service, job["id"])
            items = job_service.list_job_items(job["id"])
            events = job_service.list_events(job_id=job["id"], limit=50)
            files = library_service.list_files("family/2024")

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["item_counts"]["completed"], 1)
            self.assertEqual(len(items), 1)
            self.assertTrue(any(event["event_type"] == "job.started" for event in events))
            self.assertTrue(any(event["event_type"] == "job.completed" for event in events))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["file_name"], "Beach Sunset.mp4")

    def test_cancel_queued_job_and_restart_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            (source_root / "clips").mkdir(parents=True)
            (source_root / "clips" / "One.mp4").write_bytes(b"one")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")

            job = job_service.create_convert_directory_job("clips")
            cancelled = job_service.cancel_job(job["id"])
            restarted = job_service.restart_job(job["id"])

            self.assertEqual(cancelled["status"], "cancelled")
            self.assertEqual(cancelled["item_counts"]["cancelled"], 1)
            self.assertEqual(restarted["status"], "queued")

            job_service.start()
            self.addCleanup(job_service.shutdown)
            completed = _wait_for_terminal_status(job_service, restarted["id"])
            items = job_service.list_job_items(restarted["id"])
            events = job_service.list_events(job_id=restarted["id"], limit=50)

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(items[0]["status"], "completed")
            self.assertTrue(any(event["event_type"] == "convert.item.completed" for event in events))

    def test_convert_job_updates_file_metadata_in_production_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            source_file = target_dir / "One.mkv"
            source_file.write_bytes(b"original")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_convert_directory_job("clips")
            completed = _wait_for_terminal_status(job_service, job["id"])
            files = library_service.list_files("clips")
            items = job_service.list_job_items(job["id"])

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(files[0]["extension"], ".mp4")
            self.assertEqual(files[0]["conversion_state"], "done")
            self.assertTrue(files[0]["last_error_code"] is None)
            self.assertTrue((target_dir / "One.mp4").exists())
            self.assertFalse(source_file.exists())
            self.assertEqual(items[0]["status"], "completed")
            self.assertEqual(items[0]["output_ref"], str(target_dir / "One.mp4"))

    def test_convert_file_test_mode_preserves_source_and_creates_separate_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            source_file = target_dir / "One.mp4"
            source_file.write_bytes(b"original")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")
            file_id = library_service.list_files("clips")[0]["id"]

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_convert_file_job(file_id, mode="test")
            completed = _wait_for_terminal_status(job_service, job["id"])
            files = library_service.list_files("clips")

            self.assertEqual(completed["status"], "completed")
            self.assertTrue(source_file.exists())
            self.assertTrue((target_dir / "One.__test__default-h265-mp4.mp4").exists())
            self.assertEqual(files[0]["conversion_state"], "done")

    def test_preview_job_updates_file_metadata_and_directory_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            (target_dir / "One.mp4").write_bytes(b"one")
            (target_dir / "Two.mp4").write_bytes(b"two")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_preview_directory_job("clips")
            completed = _wait_for_terminal_status(job_service, job["id"])
            files = library_service.list_files("clips")
            events = job_service.list_events(job_id=job["id"], limit=50)
            directory_preview = job_service._preview_service.get_directory_preview(source["id"], "clips")
            file_card_preview = job_service._preview_service.get_file_card_preview_path(files[0]["id"])
            directory_card_preview = job_service._preview_service.get_directory_card_preview_path(source["id"], "clips")

            self.assertEqual(completed["status"], "completed")
            self.assertTrue(all(file["preview_state"] == "done" for file in files))
            self.assertTrue(all(file["has_preview_assets"] for file in files))
            self.assertIsNotNone(directory_preview)
            self.assertIsNotNone(file_card_preview)
            self.assertIsNotNone(directory_card_preview)
            self.assertTrue(any(event["event_type"] == "preview.item.completed" for event in events))

    def test_tag_job_stores_closed_vocabulary_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            (target_dir / "One.mp4").write_bytes(b"one")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_tag_directory_job("clips")
            completed = _wait_for_terminal_status(job_service, job["id"])
            files = library_service.list_files("clips")
            tag_payload = job_service._tagging_service.get_file_tags(files[0]["id"])
            events = job_service.list_events(job_id=job["id"], limit=50)

            self.assertEqual(completed["status"], "completed")
            self.assertEqual([tag["tag_key"] for tag in tag_payload["tags"]], ["beach", "family_time"])
            self.assertTrue(any(event["event_type"] == "tag.item.completed" for event in events))

    def test_tune_job_generates_separate_outputs_for_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, source_service, library_service, job_service, source_root = _build_services(tmp)
            target_dir = source_root / "clips"
            target_dir.mkdir(parents=True)
            source_file = target_dir / "One.mp4"
            source_file.write_bytes(b"original")
            source = source_service.get_active_source()
            assert source is not None
            library_service.scan_source(source, "")
            file_id = library_service.list_files("clips")[0]["id"]

            job_service.start()
            self.addCleanup(job_service.shutdown)

            job = job_service.create_tune_file_job(
                file_id,
                {"dimensions": [1000, 800], "quality_values": ["22"], "codecs": ["h264", "h265"]},
            )
            completed = _wait_for_terminal_status(job_service, job["id"])
            items = job_service.list_job_items(job["id"])
            events = job_service.list_events(job_id=job["id"], limit=100)

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(len(items), 4)
            self.assertTrue(all(item["status"] == "completed" for item in items))
            self.assertTrue(source_file.exists())
            self.assertTrue(all(item["output_ref"] for item in items))
            self.assertTrue(any(event["event_type"] == "tune.item.completed" for event in events))


def _build_services(tmp: str) -> tuple[Path, SourceService, LibraryService, JobService, Path]:
    root = Path(tmp)
    source_root = root / "library"
    source_root.mkdir(parents=True, exist_ok=True)
    db_path = root / "video_archive.db"
    secrets_path = root / "secrets.json"
    initialize_database(db_path)
    source_service = SourceService(db_path, SecretStore(secrets_path))
    payload = parse_source_payload(
        {
            "name": "Archive NAS",
            "protocol": "smb",
            "host": "nas.local",
            "port": 445,
            "root_path": str(source_root),
        }
    )
    source_service.replace_active_source(payload)
    library_service = LibraryService(db_path, source_service)
    profile_service = ConversionProfileService(db_path)
    preview_service = FakePreviewService(db_path, root / ".local")
    provider_settings_service = ProviderSettingsService(db_path, SecretStore(secrets_path))
    provider_settings_service.update_settings(
        [
            {
                "provider": "openrouter",
                "enabled": True,
                "vision_model": "openrouter/test-vision",
                "text_model": "",
                "prefer_batch": True,
                "api_key": "test-openrouter-key",
            },
            {"provider": "gemini", "enabled": False, "vision_model": "gemini-2.0-flash", "text_model": "", "prefer_batch": True},
            {"provider": "fal", "enabled": False, "vision_model": "fal-ai/example", "text_model": "", "prefer_batch": True},
            {"provider": "mistral", "enabled": False, "vision_model": "pixtral-large-latest", "text_model": "", "prefer_batch": True},
        ]
    )
    tagging_service = FakeTaggingService(db_path, provider_settings_service)
    tagging_service.update_settings(
        {
            "provider": "openrouter",
            "sample_count": 9,
            "combine_frames": True,
            "prefer_batch": True,
            "vocabulary": ["Beach", "Family Time", "Pets"],
        }
    )
    job_service = JobService(
        db_path,
        source_service,
        library_service,
        profile_service,
        FakeConversionService(),
        preview_service,
        tagging_service,
    )
    return root, source_service, library_service, job_service, source_root


class FakeConversionService(ConversionService):
    def __init__(self) -> None:
        super().__init__(ffmpeg_binary="fake-ffmpeg", ffprobe_binary="fake-ffprobe")

    def convert_file(self, *, source_root: str, file_row: dict, profile: dict, mode: str) -> dict:
        source_path = Path(file_row["path"])
        container = profile["container"]
        if mode == "production":
            final_path = source_path.with_suffix(f".{container}")
            final_path.write_bytes(b"converted")
            if final_path != source_path and source_path.exists():
                source_path.unlink()
        else:
            final_path = source_path.with_name(f"{source_path.stem}.__test__default-h265-mp4.{container}")
            final_path.write_bytes(b"converted-test")

        return {
            "path": str(final_path),
            "relative_path": final_path.relative_to(Path(source_root)).as_posix(),
            "file_name": final_path.name,
            "extension": final_path.suffix.lower(),
            "size_bytes": int(final_path.stat().st_size),
            "modified_at": "2026-07-05T12:00:00Z",
            "output_ref": str(final_path),
            "validation": {"codec_name": "hevc", "format_name": "mp4"},
        }


class FakePreviewService(PreviewService):
    def __init__(self, database_path: Path, data_dir: Path) -> None:
        super().__init__(database_path, data_dir)

    def generate_file_preview(self, *, source_root: str, file_row: dict, settings: dict) -> dict:
        output_path = Path(file_row["path"]).with_suffix(".jpg")
        card_gif_path = self._preview_dir / "animated" / "files" / f"{file_row['id']}.gif"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        card_gif_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-preview")
        card_gif_path.write_bytes(b"fake-gif")
        metadata = {
            "scope_type": "file",
            "file_id": file_row["id"],
            "relative_path": file_row["relative_path"],
            "file_name": file_row["file_name"],
            "sample_count": settings["sample_count"],
            "large_tile_count": settings["large_tile_count"],
            "timeline_flow": settings["timeline_flow"],
            "identity_diversity_enabled": settings["identity_diversity_enabled"],
            "layout": {"sample_count": settings["sample_count"], "large_tile_count": settings["large_tile_count"], "tiles": []},
            "keyframe_timestamps": [1.0, 2.0, 3.0],
            "large_tile_timestamps": [1.0, 2.0],
            "face_detection_summary": {"samples_with_faces": 2},
            "body_detection_summary": {"samples_with_bodies": 1},
            "layout_version": 1,
            "card_gif_path": str(card_gif_path),
        }
        self._store_file_preview_asset(
            source_id=file_row["source_id"],
            file_id=file_row["id"],
            relative_path=file_row["relative_path"],
            image_path=output_path,
            metadata=metadata,
        )
        return {"output_ref": str(output_path), "metadata": metadata}

    def generate_directory_preview(self, *, source_id: str, source_root: str, relative_path: str, settings: dict, file_rows: list[dict]) -> dict | None:
        output_path = self._preview_dir / "directories" / (relative_path.replace("/", "__") or "root")
        card_gif_path = self._preview_dir / "animated" / "directories" / f"{(relative_path.replace('/', '__') or 'root')}.gif"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        card_gif_path.parent.mkdir(parents=True, exist_ok=True)
        output_path = output_path.with_suffix(".jpg")
        output_path.write_bytes(b"fake-directory-preview")
        card_gif_path.write_bytes(b"fake-directory-gif")
        metadata = {
            "scope_type": "directory",
            "relative_path": relative_path,
            "sample_count": min(settings["sample_count"], len(file_rows)),
            "large_tile_count": min(settings["large_tile_count"], len(file_rows)),
            "timeline_flow": settings["timeline_flow"],
            "identity_diversity_enabled": settings["identity_diversity_enabled"],
            "layout": {"sample_count": min(settings["sample_count"], len(file_rows)), "large_tile_count": min(settings["large_tile_count"], len(file_rows)), "tiles": []},
            "keyframe_timestamps": [1.0],
            "large_tile_timestamps": [1.0],
            "layout_version": 1,
            "video_count": len(file_rows),
            "card_gif_path": str(card_gif_path),
        }
        self._store_directory_preview_asset(
            source_id=source_id,
            relative_path=relative_path,
            image_path=output_path,
            metadata=metadata,
        )
        return {"output_ref": str(output_path), "metadata": metadata}


class FakeTaggingService(TaggingService):
    def tag_files(self, *, source_root: str, file_rows: list[dict], settings: dict) -> list[dict]:
        vocabulary = settings["vocabulary"]
        allowed = {entry["tag_key"]: entry for entry in vocabulary}
        now = "2026-07-05T12:30:00Z"
        results = []
        for file_row in file_rows:
            selected = []
            for tag_key, confidence in (("beach", 0.93), ("family_time", 0.81), ("freeform", 0.99)):
                if tag_key not in allowed:
                    continue
                selected.append(
                    {
                        "tag_id": allowed[tag_key]["id"],
                        "tag_key": tag_key,
                        "display_name": allowed[tag_key]["display_name"],
                        "confidence": confidence,
                    }
                )
            from app.db import connection
            with connection(self._database_path) as conn, conn:
                conn.execute("DELETE FROM file_tags WHERE file_id = ?", (file_row["id"],))
                for tag in selected:
                    conn.execute(
                        """
                        INSERT INTO file_tags (id, file_id, tag_id, confidence, provider_name, model_name, assigned_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), file_row["id"], tag["tag_id"], tag["confidence"], "openrouter", "openrouter/test-vision", now),
                    )
                conn.execute(
                    """
                    UPDATE files
                    SET tagging_updated_at = ?, tagging_model_info = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, json.dumps({"provider": "openrouter", "model": "openrouter/test-vision"}), now, file_row["id"]),
                )

            results.append(
                {
                    "file_id": file_row["id"],
                    "relative_path": file_row["relative_path"],
                    "status": "completed",
                    "provider_name": "openrouter",
                    "model_name": "openrouter/test-vision",
                    "tags": selected,
                    "tag_count": len(selected),
                }
            )
        return results


def _wait_for_terminal_status(job_service: JobService, job_id: str, timeout: float = 5) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = job_service.get_job(job_id)
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for job {job_id} to reach a terminal status.")


if __name__ == "__main__":
    unittest.main()
