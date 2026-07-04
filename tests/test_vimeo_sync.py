from __future__ import annotations

import importlib
import unittest


vimeo_sync_module = importlib.import_module("app.vimeo_sync")


class VimeoSyncHelpersTests(unittest.TestCase):
    def test_extract_vimeo_video_id_from_uri(self) -> None:
        video_id = vimeo_sync_module._extract_vimeo_video_id({"uri": "/videos/123456789"})
        self.assertEqual(video_id, "123456789")

    def test_build_workout_document_uses_module_name_as_tag(self) -> None:
        document = vimeo_sync_module._build_workout_document(
            video={
                "uri": "/videos/123456789",
                "name": "Upper Body Blast",
                "pictures": {"sizes": [{"link": "https://example.com/thumb-small.jpg"}, {"link": "https://example.com/thumb-large.jpg"}]},
                "status": "available",
                "privacy": {"view": "anybody"},
            },
            module_name="Strength",
            source_type="PROJECT",
            source_uri="/me/projects/42",
            existing_workout=None,
            now=vimeo_sync_module.datetime.now(vimeo_sync_module.timezone.utc),
        )

        self.assertIsNotNone(document)
        assert document is not None
        self.assertEqual(document["vimeo_id"], "123456789")
        self.assertEqual(document["tag"], "Strength")
        self.assertEqual(document["video_source"], "VIMEO")
        self.assertEqual(document["visibility"], "Draft")
        self.assertEqual(document["vimeo_provider_visibility"], "Published")
        self.assertEqual(document["thumbnail"], "https://example.com/thumb-large.jpg")

    def test_resolve_workout_visibility_marks_private_video_as_draft(self) -> None:
        visibility = vimeo_sync_module._resolve_workout_visibility(
            {"status": "available", "privacy": {"view": "password"}}
        )
        self.assertEqual(visibility, "Draft")

    def test_resolve_synced_visibility_preserves_admin_publish_state(self) -> None:
        visibility = vimeo_sync_module._resolve_synced_visibility(
            {"visibility": "Published"},
            {"status": "available", "privacy": {"view": "disable"}},
        )
        self.assertEqual(visibility, "Published")


if __name__ == "__main__":
    unittest.main()
