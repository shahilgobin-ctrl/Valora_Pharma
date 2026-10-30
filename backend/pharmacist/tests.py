from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from tempfile import TemporaryDirectory

from django.core.files.base import ContentFile
from django.test import Client

from prescriptions.models import Prescription

PAGES = ("dashboard", "prescription_queue", "order_queue", "sale_form", "inventory")


@override_settings(DEBUG=True)
class PharmacistAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        pharmacist_group, _ = Group.objects.get_or_create(name="Pharmacist")
        manager_group, _ = Group.objects.get_or_create(name="Pharmacy Manager")

        cls.pharmacist = user_model.objects.create_user(
            email="pharmacist@example.com",
            account_type="staff",
        )
        cls.pharmacist.groups.add(pharmacist_group)

        cls.customer = user_model.objects.create_user(
            email="customer@example.com",
            first_name="Test",
            last_name="Customer",
            account_type="customer",
        )

        cls.manager = user_model.objects.create_user(
            email="manager@example.com",
            account_type="staff",
        )
        cls.manager.groups.add(manager_group)

        cls.superuser = user_model.objects.create_superuser(
            email="admin@example.com",
        )

        cls.unassigned_staff = user_model.objects.create_user(
            email="unassigned@example.com",
            account_type="staff",
        )

    def test_anonymous_users_are_redirected_to_staff_login(self):
        for page in PAGES:
            with self.subTest(page=page):
                url = reverse(f"pharmacist:{page}")
                response = self.client.get(url)

                expected_url = f"{reverse('accounts:staff_login')}?next={url}"
                self.assertRedirects(
                    response,
                    expected_url,
                    fetch_redirect_response=False,
                )

    def test_pharmacist_can_access_all_pages(self):
        # Test access independently of the login form.
        self.client.force_login(self.pharmacist)

        for page in PAGES:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"pharmacist:{page}"))

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(
                    response,
                    "pharmacist/base.html",
                )
                self.assertContains(response, 'id="main-content"')
                # Sidebar and pagination can both legitimately mark the
                # current page. Assert exactly one active SIDEBAR item,
                # rather than counting the attribute in the whole response.
                html = response.content.decode("utf-8")
                self.assertIn('<nav class="vp-nav"', html)
                sidebar_nav = html.split('<nav class="vp-nav"', 1)[1].split(
                    "</nav>", 1
                )[0]
                self.assertEqual(
                    sidebar_nav.count('aria-current="page"'),
                    1,
                )

                if page == "prescription_queue":
                    self.assertContains(
                        response,
                        'class="pq-current-page" aria-current="page"',
                    )
                    self.assertContains(
                        response,
                        "No pending prescriptions.",
                    )
                    self.assertNotContains(
                        response,
                        "Sample data only",
                    )
                elif page in {"dashboard", "order_queue", "sale_form"}:
                    if page == "order_queue":
                        self.assertContains(
                            response,
                            'class="oq-current-page" aria-current="page"',
                        )
                    self.assertNotContains(response, "Sample data only")
                else:
                    self.assertNotContains(response, "Sample data only")

    def test_other_roles_cannot_access_pharmacist_pages(self):
        users = (
            self.customer,
            self.manager,
            self.superuser,
            self.unassigned_staff,
        )

        for user in users:
            self.client.force_login(user)

            for page in PAGES:
                with self.subTest(user=user.email, page=page):
                    response = self.client.get(reverse(f"pharmacist:{page}"))
                    self.assertEqual(response.status_code, 403)

            self.client.logout()

    def test_customer_with_pharmacist_group_is_still_denied(self):
        # Group membership alone must not bypass account-type checks.
        self.customer.groups.add(Group.objects.get(name="Pharmacist"))
        self.client.force_login(self.customer)

        response = self.client.get(reverse("pharmacist:dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_deactivated_pharmacist_loses_access(self):
        self.client.force_login(self.pharmacist)

        self.pharmacist.is_active = False
        self.pharmacist.save(update_fields=["is_active"])

        url = reverse("pharmacist:dashboard")
        response = self.client.get(url)

        # The default authentication backend rejects inactive users.
        self.assertRedirects(
            response,
            f"{reverse('accounts:staff_login')}?next={url}",
            fetch_redirect_response=False,
        )

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False)
    def test_database_pages_are_available_in_production(self):
        self.client.force_login(self.pharmacist)

        for page in PAGES:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"pharmacist:{page}"))

                self.assertEqual(response.status_code, 200)

    def test_read_only_pages_reject_mutating_requests(self):
        self.client.force_login(self.pharmacist)

        for page in PAGES:
            url = reverse(f"pharmacist:{page}")

            for method in ("post", "put", "patch", "delete"):
                with self.subTest(page=page, method=method):
                    response = getattr(self.client, method)(url)
                    expected = 400 if page == "sale_form" and method == "post" else 405
                    self.assertEqual(response.status_code, expected)

    def test_shared_assets_are_discoverable(self):
        assets = (
            "css/pharmacist.css",
            "js/pharmacist.js",
            "css/workflows.css",
            "css/sale_pos.css",
            "js/sale_pos.js",
        )

        for asset in assets:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(f"pharmacist/{asset}"))

    def test_queue_displays_pending_database_records(self):
        # These views do not open files, so only a stored path is needed.
        prescription = Prescription.objects.create(
            customer=self.customer,
            document="prescriptions/test-pending.pdf",
        )
        self.client.force_login(self.pharmacist)

        response = self.client.get(reverse("pharmacist:prescription_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"RX-{prescription.pk}")
        self.assertContains(response, "Test Customer")
        self.assertNotContains(
            response,
            "No pending prescriptions.",
        )
        self.assertQuerySetEqual(
            response.context["prescriptions"],
            [prescription],
        )

        detail_url = reverse(
            "pharmacist:prescription_detail",
            args=[prescription.pk],
        )
        self.assertContains(response, f'href="{detail_url}"')

    def test_queue_excludes_reviewed_prescriptions(self):
        review_time = timezone.now()

        pending = Prescription.objects.create(
            customer=self.customer,
            document="prescriptions/pending.pdf",
        )
        Prescription.objects.create(
            customer=self.customer,
            document="prescriptions/approved.pdf",
            status=Prescription.Status.APPROVED,
            uploaded_at=review_time,
            reviewed_by=self.pharmacist,
            reviewed_at=review_time,
        )
        Prescription.objects.create(
            customer=self.customer,
            document="prescriptions/rejected.pdf",
            status=Prescription.Status.REJECTED,
            uploaded_at=review_time,
            reviewed_by=self.pharmacist,
            reviewed_at=review_time,
            rejection_reason="The document is unreadable.",
        )
        self.client.force_login(self.pharmacist)

        response = self.client.get(reverse("pharmacist:prescription_queue"))

        self.assertQuerySetEqual(
            response.context["prescriptions"],
            [pending],
        )

    def test_detail_displays_selected_prescription(self):
        prescription = Prescription.objects.create(
            customer=self.customer,
            document="prescriptions/detail-test.pdf",
        )
        self.client.force_login(self.pharmacist)

        response = self.client.get(
            reverse(
                "pharmacist:prescription_detail",
                args=[prescription.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "pharmacist/prescription_detail.html",
        )
        self.assertEqual(
            response.context["prescription"],
            prescription,
        )
        self.assertContains(response, "Test Customer")
        self.assertContains(response, f"RX-{prescription.pk}")
        self.assertIn(
            "no-store",
            response.headers["Cache-Control"],
        )

    def test_detail_requires_pharmacist_and_existing_record(self):
        prescription = Prescription.objects.create(
            customer=self.customer,
            document="prescriptions/access-test.pdf",
        )
        url = reverse(
            "pharmacist:prescription_detail",
            args=[prescription.pk],
        )

        self.assertRedirects(
            self.client.get(url),
            f"{reverse('accounts:staff_login')}?next={url}",
            fetch_redirect_response=False,
        )

        users = (
            self.customer,
            self.manager,
            self.superuser,
            self.unassigned_staff,
        )

        for user in users:
            with self.subTest(user=user.email):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(url).status_code,
                    403,
                )
                self.client.logout()

        self.client.force_login(self.pharmacist)
        missing_url = reverse(
            "pharmacist:prescription_detail",
            args=[prescription.pk + 1],
        )
        self.assertEqual(
            self.client.get(missing_url).status_code,
            404,
        )


class PrescriptionWorkflowTests(TestCase):
    def setUp(self):
        # Isolate test documents from application uploads.
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)

        storage_settings = override_settings(MEDIA_ROOT=directory.name)
        storage_settings.enable()
        self.addCleanup(storage_settings.disable)

        user_model = get_user_model()

        self.pharmacist = user_model.objects.create_user(
            email="reviewer@example.com",
            account_type="staff",
        )
        group, _ = Group.objects.get_or_create(name="Pharmacist")
        self.pharmacist.groups.add(group)

        self.customer = user_model.objects.create_user(
            email="owner@example.com",
            account_type="customer",
        )

        self.prescription = Prescription(customer=self.customer)
        self.document_bytes = b"Test document for download assertions."
        self.prescription.document.save(
            "test.pdf",
            ContentFile(self.document_bytes),
            save=False,
        )
        self.prescription.full_clean()
        self.prescription.save()

        self.detail_url = reverse(
            "pharmacist:prescription_detail",
            args=[self.prescription.pk],
        )
        self.document_url = reverse(
            "pharmacist:prescription_document",
            args=[self.prescription.pk],
        )
        self.client.force_login(self.pharmacist)

    def test_approval_records_authenticated_reviewer(self):
        response = self.client.post(
            self.detail_url,
            {
                "decision": "approved",
                "reviewed_by": self.customer.pk,
            },
        )

        self.assertRedirects(response, self.detail_url)
        self.prescription.refresh_from_db()

        self.assertEqual(self.prescription.status, "approved")
        self.assertEqual(
            self.prescription.reviewed_by_id,
            self.pharmacist.pk,
        )
        self.assertIsNotNone(self.prescription.reviewed_at)
        self.assertEqual(self.prescription.rejection_reason, "")

        queue = self.client.get(reverse("pharmacist:prescription_queue"))
        self.assertQuerySetEqual(queue.context["prescriptions"], [])

    def test_rejection_requires_reason_and_saves_valid_reason(self):
        response = self.client.post(
            self.detail_url,
            {"decision": "rejected", "rejection_reason": "   "},
        )

        self.assertEqual(response.status_code, 400)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "pending")

        response = self.client.post(
            self.detail_url,
            {
                "decision": "rejected",
                "rejection_reason": "  Document is unreadable.  ",
            },
        )

        self.assertRedirects(response, self.detail_url)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "rejected")
        self.assertEqual(
            self.prescription.rejection_reason,
            "Document is unreadable.",
        )

    def test_review_cannot_be_overwritten(self):
        self.client.post(
            self.detail_url,
            {"decision": "approved"},
        )
        self.prescription.refresh_from_db()
        original_review_time = self.prescription.reviewed_at

        response = self.client.post(
            self.detail_url,
            {
                "decision": "rejected",
                "rejection_reason": "Attempted second review.",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "approved")
        self.assertEqual(
            self.prescription.reviewed_at,
            original_review_time,
        )

    def test_invalid_decision_does_not_change_record(self):
        response = self.client.post(
            self.detail_url,
            {"decision": "completed"},
        )

        self.assertEqual(response.status_code, 400)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "pending")

    def test_customer_cannot_review_or_download(self):
        self.client.force_login(self.customer)

        response = self.client.post(
            self.detail_url,
            {"decision": "approved"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            self.client.get(self.document_url).status_code,
            403,
        )

        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "pending")

    def test_document_download_returns_file_with_private_headers(self):
        response = self.client.get(self.document_url)

        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                b"".join(response.streaming_content),
                self.document_bytes,
            )
            self.assertIn(
                "attachment",
                response.headers["Content-Disposition"],
            )
            self.assertIn(
                "no-store",
                response.headers["Cache-Control"],
            )
            self.assertEqual(
                response.headers["X-Content-Type-Options"],
                "nosniff",
            )
        finally:
            response.close()

    def test_missing_document_blocks_download_and_approval(self):
        self.prescription.document.storage.delete(self.prescription.document.name)

        self.assertEqual(
            self.client.get(self.document_url).status_code,
            404,
        )

        response = self.client.post(
            self.detail_url,
            {"decision": "approved"},
        )
        self.assertEqual(response.status_code, 400)

        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "pending")

    def test_anonymous_document_request_redirects_to_login(self):
        self.client.logout()

        response = self.client.get(self.document_url)

        self.assertRedirects(
            response,
            f"{reverse('accounts:staff_login')}?next={self.document_url}",
            fetch_redirect_response=False,
        )

    def test_review_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.pharmacist)

        response = csrf_client.post(
            self.detail_url,
            {"decision": "approved"},
        )

        self.assertEqual(response.status_code, 403)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "pending")

    def test_get_request_cannot_record_decision(self):
        response = self.client.get(
            self.detail_url,
            {"decision": "approved"},
        )

        self.assertEqual(response.status_code, 200)
        self.prescription.refresh_from_db()
        self.assertEqual(self.prescription.status, "pending")


class RetiredSampleRouteTests(TestCase):
    def test_sample_urls_are_removed(self):
        for path in (
            "/pharmacist/prescriptions/sample/",
            "/pharmacist/orders/sample/",
            "/pharmacist/sales/sample/receipt/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
