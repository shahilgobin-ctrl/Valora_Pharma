from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from prescriptions.models import Prescription


class PrescriptionDocumentPreviewTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)

        media_settings = override_settings(
            MEDIA_ROOT=self.media_directory.name,
        )
        media_settings.enable()
        self.addCleanup(media_settings.disable)

        user_model = get_user_model()

        self.pharmacist = user_model.objects.create_user(
            email="preview-pharmacist@example.com",
            password="Preview-Test-Password-482!",
            account_type=user_model.AccountType.STAFF,
        )
        pharmacist_group, _ = Group.objects.get_or_create(
            name="Pharmacist",
        )
        self.pharmacist.groups.add(pharmacist_group)

        self.customer = user_model.objects.create_user(
            email="preview-customer@example.com",
            password="Preview-Test-Password-482!",
            account_type=user_model.AccountType.CUSTOMER,
        )

        self.unassigned_staff = user_model.objects.create_user(
            email="preview-staff@example.com",
            password="Preview-Test-Password-482!",
            account_type=user_model.AccountType.STAFF,
        )

        # These bytes test HTTP delivery, not PDF rendering or validation.
        self.document_bytes = b"%PDF-1.4\nPreview response test.\n%%EOF\n"
        self.prescription = Prescription(customer=self.customer)
        self.prescription.document.save(
            "preview.pdf",
            ContentFile(self.document_bytes),
            save=False,
        )
        self.prescription.save()

        self.preview_url = reverse(
            "pharmacist:prescription_document_preview",
            args=[self.prescription.pk],
        )
        self.detail_url = reverse(
            "pharmacist:prescription_detail",
            args=[self.prescription.pk],
        )

        self.client.force_login(self.pharmacist)

    def test_pharmacist_can_preview_pdf_with_security_headers(self):
        response = self.client.get(self.preview_url)
        self.addCleanup(response.close)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(
            response["Content-Disposition"].startswith("inline;")
        )
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(
            response["Content-Security-Policy"],
            "frame-ancestors 'self'",
        )
        self.assertEqual(
            response["X-Content-Type-Options"],
            "nosniff",
        )
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertEqual(
            b"".join(response.streaming_content),
            self.document_bytes,
        )

    def test_anonymous_user_is_redirected_to_staff_login(self):
        self.client.logout()

        response = self.client.get(self.preview_url)

        login_url = reverse("accounts:staff_login")
        self.assertRedirects(
            response,
            f"{login_url}?next={self.preview_url}",
            fetch_redirect_response=False,
        )

    def test_customer_and_unassigned_staff_cannot_preview(self):
        for user in (self.customer, self.unassigned_staff):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(self.preview_url)
                self.assertEqual(response.status_code, 403)

    def test_missing_file_returns_404(self):
        document = self.prescription.document
        document.storage.delete(document.name)

        response = self.client.get(self.preview_url)

        self.assertEqual(response.status_code, 404)

    def test_review_page_does_not_embed_missing_document(self):
        self.prescription.document.storage.delete(self.prescription.document.name)
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<iframe")
        self.assertNotContains(response, 'href="' + self.preview_url + '"')
        self.assertContains(response, "The prescription document is unavailable.")

    def test_unknown_prescription_returns_404(self):
        url = reverse(
            "pharmacist:prescription_document_preview",
            args=[self.prescription.pk + 1000],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_preview_does_not_accept_post(self):
        response = self.client.post(self.preview_url)

        self.assertEqual(response.status_code, 405)

    def test_review_page_embeds_pdf_and_keeps_download_link(self):
        response = self.client.get(self.detail_url)

        # Browser PDF viewers can create nested frames. The containing review
        # page and private preview must both permit same-origin framing.
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(response, "<iframe")
        self.assertContains(response, f'src="{self.preview_url}"')
        self.assertContains(response, "Open in new tab")
        self.assertContains(
            response,
            reverse(
                "pharmacist:prescription_document",
                args=[self.prescription.pk],
            ),
        )

    def test_other_pharmacist_pages_keep_frame_protection(self):
        response = self.client.get(reverse("pharmacist:prescription_queue"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_image_formats_use_image_content_type_and_template(self):
        for extension, content_type in (
            ("png", "image/png"),
            ("jpg", "image/jpeg"),
            ("jpeg", "image/jpeg"),
        ):
            with self.subTest(extension=extension):
                prescription = Prescription(customer=self.customer)
                prescription.document.save(
                    f"preview.{extension}",
                    ContentFile(b"HTTP delivery test fixture."),
                    save=False,
                )
                prescription.save()

                preview_url = reverse(
                    "pharmacist:prescription_document_preview",
                    args=[prescription.pk],
                )
                response = self.client.get(preview_url)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        response["Content-Type"],
                        content_type,
                    )
                finally:
                    response.close()

                detail_response = self.client.get(
                    reverse(
                        "pharmacist:prescription_detail",
                        args=[prescription.pk],
                    )
                )
                self.assertContains(
                    detail_response,
                    'class="vp-document-image"',
                )
                self.assertContains(
                    detail_response,
                    f'src="{preview_url}"',
                )
                self.assertNotContains(detail_response, "<iframe")

    def test_unsupported_extension_is_not_served_inline(self):
        Prescription.objects.filter(pk=self.prescription.pk).update(
            document="prescriptions/unsupported.html",
        )

        response = self.client.get(self.preview_url)

        self.assertEqual(response.status_code, 404)
