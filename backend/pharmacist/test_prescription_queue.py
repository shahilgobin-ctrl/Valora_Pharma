from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from prescriptions.models import Prescription


class PrescriptionQueueFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.pharmacist = user_model.objects.create_user(
            email="queue-pharmacist@example.com",
            account_type=user_model.AccountType.STAFF,
        )
        group, _ = Group.objects.get_or_create(name="Pharmacist")
        cls.pharmacist.groups.add(group)

        cls.customer = user_model.objects.create_user(
            email="anika@example.com",
            first_name="Anika",
            last_name="Devi",
            account_type=user_model.AccountType.CUSTOMER,
        )
        cls.other_customer = user_model.objects.create_user(
            email="ravi@example.com",
            first_name="Ravi",
            last_name="Singh",
            account_type=user_model.AccountType.CUSTOMER,
        )

        uploaded_at = timezone.now() - timedelta(days=1)
        reviewed_at = timezone.now()

        # Queue tests need document references, not physical files.
        cls.pending = Prescription.objects.create(
            customer=cls.customer,
            document="prescriptions/queue-pending.pdf",
            uploaded_at=uploaded_at,
        )
        cls.approved = Prescription.objects.create(
            customer=cls.customer,
            document="prescriptions/queue-approved.pdf",
            status=Prescription.Status.APPROVED,
            uploaded_at=uploaded_at,
            reviewed_by=cls.pharmacist,
            reviewed_at=reviewed_at,
        )
        cls.rejected = Prescription.objects.create(
            customer=cls.other_customer,
            document="prescriptions/queue-rejected.pdf",
            status=Prescription.Status.REJECTED,
            uploaded_at=uploaded_at,
            reviewed_by=cls.pharmacist,
            reviewed_at=reviewed_at,
            rejection_reason="The document is unreadable.",
        )

    def setUp(self):
        self.client.force_login(self.pharmacist)
        self.url = reverse("pharmacist:prescription_queue")

    def test_default_queue_shows_only_pending(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(
            response.context["prescriptions"],
            [self.pending],
        )

    def test_status_filters_show_matching_records(self):
        for status, expected in (
            ("approved", self.approved),
            ("rejected", self.rejected),
        ):
            with self.subTest(status=status):
                response = self.client.get(
                    self.url,
                    {"status": status},
                )
                self.assertEqual(response.status_code, 200)
                self.assertQuerySetEqual(
                    response.context["prescriptions"],
                    [expected],
                )

    def test_all_statuses_include_reviewed_records(self):
        response = self.client.get(self.url, {"status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["page_obj"].paginator.count,
            3,
        )
        self.assertSetEqual(
            set(response.context["prescriptions"]),
            {self.pending, self.approved, self.rejected},
        )

    def test_search_by_name_full_name_and_email(self):
        for query in ("anika", "ANIKA DEVI", "anika@example.com"):
            with self.subTest(query=query):
                response = self.client.get(
                    self.url,
                    {"q": query, "status": "all"},
                )
                self.assertSetEqual(
                    set(response.context["prescriptions"]),
                    {self.pending, self.approved},
                )

    def test_search_by_reference(self):
        for query in (
            f"RX-{self.rejected.pk}",
            f"rx-{self.rejected.pk}",
            str(self.rejected.pk),
        ):
            with self.subTest(query=query):
                response = self.client.get(
                    self.url,
                    {"q": query, "status": "all"},
                )
                self.assertQuerySetEqual(
                    response.context["prescriptions"],
                    [self.rejected],
                )

    def test_search_and_status_are_applied_together(self):
        response = self.client.get(
            self.url,
            {"q": "Anika", "status": "approved"},
        )

        self.assertQuerySetEqual(
            response.context["prescriptions"],
            [self.approved],
        )

    def test_invalid_filters_return_errors(self):
        for parameters, field in (
            ({"status": "unknown"}, "status"),
            ({"q": "x" * 101}, "q"),
        ):
            with self.subTest(parameters=parameters):
                response = self.client.get(self.url, parameters)

                self.assertEqual(response.status_code, 400)
                self.assertIn(
                    field,
                    response.context["filter_form"].errors,
                )
                self.assertEqual(
                    response.context["page_obj"].paginator.count,
                    0,
                )

    def test_no_matches_displays_empty_message(self):
        response = self.client.get(
            self.url,
            {"q": "NoMatchingCustomer", "status": "all"},
        )

        self.assertContains(
            response,
            "No prescriptions match your filters.",
        )

    def test_pagination_preserves_filters_and_order(self):
        for index in range(10):
            Prescription.objects.create(
                customer=self.customer,
                document=f"prescriptions/extra-{index}.pdf",
            )

        parameters = {"q": "Anika", "status": "pending"}
        first_response = self.client.get(self.url, parameters)
        second_response = self.client.get(
            self.url,
            {**parameters, "page": 2},
        )

        first_page = first_response.context["page_obj"]
        second_page = second_response.context["page_obj"]

        self.assertEqual(first_page.paginator.count, 11)
        self.assertEqual(len(first_page.object_list), 10)
        self.assertEqual(len(second_page.object_list), 1)
        self.assertEqual(first_page.object_list[0], self.pending)

        self.assertTrue(
            set(first_page.object_list).isdisjoint(
                set(second_page.object_list)
            )
        )
        self.assertContains(
            first_response,
            "?q=Anika&amp;status=pending&amp;page=2",
        )

    def test_invalid_page_values_do_not_crash(self):
        for page in ("abc", "99999", "-1"):
            with self.subTest(page=page):
                response = self.client.get(
                    self.url,
                    {"page": page},
                )
                self.assertEqual(response.status_code, 200)

    def test_very_large_numeric_search_does_not_crash(self):
        response = self.client.get(
            self.url,
            {"q": "9" * 100, "status": "all"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["page_obj"].paginator.count,
            0,
        )