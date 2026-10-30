from html.parser import HTMLParser

from django.test import Client, TestCase, override_settings
from django.urls import include, path, resolve, reverse

from .forms import ContactForm
from .models import ContactMessage


class PageElements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class MountedURLs:
    urlpatterns = [path("company/", include("pages.urls")), path("", include("accounts.urls"))]


class ConnectedURLs:
    from .views import about

    urlpatterns = [
        path("", include("pages.urls")),
        path("", include("accounts.urls")),
        path("home/", about, name="home"),
        path("catalogue/", include(([
            path("", about, name="shop"),
            path("basket/", about, name="cart"),
        ], "shop"))),
    ]


class PageRenderingTests(TestCase):
    def test_pages_are_public_and_use_template_inheritance(self):
        for page, title in [("about", "About Us"), ("contact", "Contact Us")]:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"pages:{page}"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, f"pages/{page}.html")
                self.assertTemplateUsed(response, "pages/base.html")
                self.assertContains(response, f"<title>{title} | ValoraPharma</title>", html=True)

    def test_semantic_landmarks_and_one_active_navigation_link(self):
        for page in ("about", "contact"):
            response = self.client.get(reverse(f"pages:{page}"))
            elements = PageElements(response.content.decode()).elements
            for tag in ("html", "header", "nav", "main", "h1"):
                self.assertEqual(sum(t == tag for t, _ in elements), 1)
            active = [a for _, a in elements if a.get("aria-current") == "page"]
            self.assertEqual([a["href"] for a in active], [reverse(f"pages:{page}")])
            self.assertContains(response, 'href="#main-content"')

    def test_both_pages_link_to_each_other_and_existing_account_routes(self):
        for page in ("about", "contact"):
            response = self.client.get(reverse(f"pages:{page}"))
            for name in ("pages:about", "pages:contact", "accounts:login", "accounts:register"):
                self.assertContains(response, f'href="{reverse(name)}"')
            for tag, attrs in PageElements(response.content.decode()).elements:
                if tag == "a" and attrs["href"].startswith("/"):
                    self.assertIsNotNone(resolve(attrs["href"]))

    def test_unconnected_destinations_do_not_have_fake_links(self):
        for page in ("about", "contact"):
            response = self.client.get(reverse(f"pages:{page}"))
            elements = PageElements(response.content.decode()).elements
            unavailable = [a for _, a in elements if a.get("aria-disabled") == "true"]
            self.assertTrue(all("href" not in a and "tabindex" not in a for a in unavailable))
            self.assertNotContains(response, 'href="#"')

    def test_styles_are_internal_and_assets_are_embedded(self):
        for page in ("about", "contact"):
            response = self.client.get(reverse(f"pages:{page}"))
            html = response.content.decode()
            self.assertEqual(html.count("<style>"), 1)
            self.assertLess(html.index("</style>"), html.index("</head>"))
            self.assertNotIn('rel="stylesheet"', html)
            self.assertNotIn("<script", html)
            self.assertNotIn("@import", html)
            self.assertIn("data:font/woff;base64,", html)
            for tag, attrs in PageElements(html).elements:
                self.assertNotIn("style", attrs)
                if tag == "img":
                    self.assertTrue(attrs["src"].startswith("data:image/"))
                    self.assertIn("alt", attrs)

    def test_about_copy_and_three_benefits_match_the_design(self):
        response = self.client.get(reverse("pages:about"))
        for phrase in ("Established in 2025", "Through a hybrid model", "configure user permissions", "Valora Pharma’s vision", "FULLY SECURE HUB", "CERTIFIED SAFETY", "OPERATIONAL", "EFFICIENCY"):
            self.assertContains(response, phrase)
        self.assertEqual(sum(t == "article" for t, _ in PageElements(response.content.decode()).elements), 3)
        self.assertNotContains(response, "<form")

    def test_contact_has_accessible_fields_and_actionable_contact_details(self):
        response = self.client.get(reverse("pages:contact"))
        elements = PageElements(response.content.decode()).elements
        labels = {a["for"] for t, a in elements if t == "label"}
        fields = [a for t, a in elements if t in ("input", "textarea") and a.get("type") != "hidden"]
        self.assertEqual(len(fields), 5)
        self.assertTrue(all(a["id"] in labels for a in fields))
        self.assertContains(response, 'href="tel:+23057401234"')
        self.assertContains(response, 'href="mailto:info@valorapharma.mu"')
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_supported_http_methods(self):
        for page in ("about", "contact"):
            self.assertEqual(self.client.head(reverse(f"pages:{page}")).status_code, 200)
            self.assertEqual(self.client.put(reverse(f"pages:{page}")).status_code, 405)
        self.assertEqual(self.client.post(reverse("pages:about"), {}).status_code, 405)

    def test_unknown_routes_remain_404(self):
        self.assertEqual(self.client.get("/not-a-page/").status_code, 404)

    @override_settings(ROOT_URLCONF=MountedURLs)
    def test_named_links_follow_the_pages_app_mount_point(self):
        for page in ("about", "contact"):
            response = self.client.get(reverse(f"pages:{page}"))
            self.assertContains(response, 'href="/company/about/"')
            self.assertContains(response, 'href="/company/contact/"')

    @override_settings(ROOT_URLCONF=ConnectedURLs)
    def test_home_shop_and_cart_links_activate_when_the_team_routes_exist(self):
        for page in ("about", "contact"):
            response = self.client.get(reverse(f"pages:{page}"))
            elements = PageElements(response.content.decode()).elements
            links = {a.get("class"): a.get("href") for t, a in elements if t == "a"}
            self.assertEqual(links["nav-home"], "/home/")
            self.assertEqual(links["nav-products"], "/catalogue/")
            self.assertEqual(links["cart"], "/catalogue/basket/")
            self.assertEqual(links["brand"], "/home/")
            if page == "about":
                self.assertEqual(links["nav-shop"], "/catalogue/")
            self.assertFalse(any(a.get("aria-disabled") == "true" for _, a in elements))

    @override_settings(ROOT_URLCONF=ConnectedURLs)
    def test_standalone_previews_do_not_link_to_django_only_routes(self):
        from django.template.loader import render_to_string

        html = render_to_string("pages/about.html", {"active_page": "about", "preview_mode": True})
        self.assertNotIn('href="/home/"', html)
        self.assertNotIn('href="/catalogue/"', html)
        self.assertIn('href="contact-preview.html"', html)


class ContactSubmissionTests(TestCase):
    def setUp(self):
        self.url = reverse("pages:contact")
        self.data = {
            "full_name": "Test Visitor", "email": "visitor@example.test",
            "phone": "+230 5740 1234", "subject": "Opening hours", "message": "Can I visit on Saturday?",
        }

    def test_valid_message_is_saved_then_redirected(self):
        response = self.client.post(self.url, self.data)
        self.assertRedirects(response, self.url)
        saved = ContactMessage.objects.get()
        for field, value in self.data.items():
            self.assertEqual(getattr(saved, field), value)
        self.assertIsNotNone(saved.created_at)

    def test_refresh_after_success_does_not_duplicate_the_message(self):
        response = self.client.post(self.url, self.data, follow=True)
        self.assertContains(response, "Your message has been saved")
        self.client.get(self.url)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_empty_post_shows_required_errors_and_saves_nothing(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.context["form"].errors), {"full_name", "email", "subject", "message"})
        self.assertFalse(ContactMessage.objects.exists())

    def test_invalid_email_or_phone_is_rejected_and_input_retained(self):
        for field, value in (("email", "not-an-email"), ("phone", "call me tomorrow")):
            response = self.client.post(self.url, {**self.data, field: value})
            self.assertIn(field, response.context["form"].errors)
            self.assertContains(response, "Test Visitor")
            self.assertContains(response, 'aria-invalid="true"')
        self.assertFalse(ContactMessage.objects.exists())

    def test_phone_is_optional_and_international_formats_are_accepted(self):
        for phone in ("", "+230 5740 1234", "(020) 7946-0958"):
            form = ContactForm({**self.data, "phone": phone})
            self.assertTrue(form.is_valid(), form.errors)

    def test_overlong_and_whitespace_only_values_are_rejected(self):
        for field, value in (("full_name", "x" * 121), ("subject", "x" * 161), ("message", "x" * 4001), ("message", "   ")):
            response = self.client.post(self.url, {**self.data, field: value})
            self.assertIn(field, response.context["form"].errors)
        self.assertFalse(ContactMessage.objects.exists())

    def test_csrf_token_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.get(self.url)
        self.assertEqual(client.post(self.url, self.data).status_code, 403)
        self.assertFalse(ContactMessage.objects.exists())
        data = {**self.data, "csrfmiddlewaretoken": client.cookies["csrftoken"].value}
        self.assertEqual(client.post(self.url, data).status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)

    def test_user_input_is_escaped_on_validation_failure(self):
        response = self.client.post(self.url, {**self.data, "full_name": '<script>alert("x")</script>', "email": "invalid"})
        self.assertNotContains(response, '<script>')
        self.assertContains(response, "&lt;script&gt;")

    def test_submissions_are_not_listed_publicly(self):
        self.client.post(self.url, self.data)
        response = self.client.get(self.url)
        self.assertNotContains(response, self.data["message"])
        self.assertNotContains(response, self.data["email"])

    def test_extra_fields_cannot_set_the_id_or_timestamp(self):
        self.client.post(self.url, {**self.data, "id": "987654", "created_at": "2000-01-01"})
        saved = ContactMessage.objects.get()
        self.assertNotEqual(saved.pk, 987654)
        self.assertGreater(saved.created_at.year, 2000)
