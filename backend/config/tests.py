from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .runtime import data_directory


class DataDirectoryTests(SimpleTestCase):
    def test_default_keeps_existing_single_checkout_behavior(self):
        with TemporaryDirectory() as directory, patch.dict("os.environ", {"DJANGO_DATA_DIR": ""}):
            self.assertEqual(data_directory(Path(directory)), Path(directory).resolve())

    def test_two_checkouts_can_share_one_directory_via_local_pointer(self):
        with TemporaryDirectory() as directory, patch.dict("os.environ", {"DJANGO_DATA_DIR": ""}):
            root = Path(directory)
            original = root / "original"
            shared = root / "shared"
            original.mkdir()
            shared.mkdir()
            (original / ".data-directory").write_text(str(shared), encoding="utf-8")
            self.assertEqual(data_directory(original), data_directory(shared))

    def test_explicit_environment_takes_precedence_over_pointer(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".data-directory").write_text("does-not-exist", encoding="utf-8")
            with patch.dict("os.environ", {"DJANGO_DATA_DIR": str(root)}):
                self.assertEqual(data_directory(root), root.resolve())

    def test_invalid_directory_does_not_create_an_empty_database(self):
        with TemporaryDirectory() as directory, patch.dict("os.environ", {"DJANGO_DATA_DIR": ""}):
            root = Path(directory)
            (root / ".data-directory").write_text("missing", encoding="utf-8")
            with self.assertRaises(ImproperlyConfigured):
                data_directory(root)
            self.assertFalse((root / "missing").exists())
