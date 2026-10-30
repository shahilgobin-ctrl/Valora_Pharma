from html.parser import HTMLParser

from django.test import SimpleTestCase, override_settings
from django.urls import include, path, resolve, reverse

from .views import about


class PageElements(HTMLParser):
    """Collect HTML elements without adding a test dependency."""

    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class MountedURLs:
    urlpatterns = [
        path("company/", include("pages.urls")),
        path("", include("accounts.urls")),
    ]


class AboutPageTests(SimpleTestCase):
    # SimpleTestCase also fails if this informational view queries the database.
    def setUp(self):
        self.response = self.client.get(reverse("pages:about"))
        self.html = self.response.content.decode()
        self.elements = PageElements(self.html).elements

    def test_named_url_resolves_to_about_view(self):
        self.assertEqual(reverse("pages:about"), "/about/")
        self.assertEqual(resolve("/about/").func, about)

    def test_page_succeeds_and_uses_child_and_base_templates(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertTemplateUsed(self.response, "pages/about.html")
        self.assertTemplateUsed(self.response, "pages/base.html")

    def test_about_heading_and_page_title(self):
        self.assertContains(self.response, '<h1 id="about-heading">ABOUT US</h1>', html=True)
        self.assertContains(self.response, "<title>About Us | ValoraPharma</title>", html=True)

    def test_company_description_is_complete(self):
        for phrase in [
            "Established in 2025", "Through a hybrid model", "monitor their order history",
            "On the back end", "configure user permissions", "Valora Pharma's vision",
            "prioritizing customer satisfaction",
        ]:
            with self.subTest(phrase=phrase):
                self.assertContains(self.response, phrase)

    def test_all_three_benefits_are_present(self):
        self.assertEqual(sum(tag == "article" for tag, _ in self.elements), 3)
        for heading in ["FULLY SECURE HUB", "CERTIFIED SAFETY", "OPERATIONAL EFFICIENCY"]:
            self.assertContains(self.response, f"<h3>{heading}</h3>", html=True)

    def test_shared_structure_and_accessible_landmarks(self):
        for tag in ["html", "header", "nav", "main", "h1"]:
            self.assertEqual(sum(t == tag for t, _ in self.elements), 1)
        self.assertIn(("html", {"lang": "en"}), self.elements)
        self.assertContains(self.response, 'href="#main-content"')
        self.assertContains(self.response, 'id="main-content" tabindex="-1"')

    def test_about_link_is_the_only_active_navigation_item(self):
        active = [a for t, a in self.elements if a.get("aria-current") == "page"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["href"], reverse("pages:about"))
        self.assertIn("vp-nav__item--active", active[0]["class"])

    def test_unavailable_destinations_have_no_fake_links(self):
        unavailable = [a for _, a in self.elements if a.get("aria-disabled") == "true"]
        self.assertEqual(len(unavailable), 0)
        self.assertTrue(all("href" not in a and "tabindex" not in a for a in unavailable))
        self.assertNotContains(self.response, "Other menu items are inactive.")
        self.assertNotContains(self.response, 'href="#"')

    def test_internal_links_resolve_and_fragments_exist(self):
        ids = {a["id"] for _, a in self.elements if "id" in a}
        for tag, attrs in self.elements:
            if tag == "a":
                href = attrs["href"]
                if href.startswith("/"):
                    self.assertIn(resolve(href.split("#")[0]).view_name, {"home", "shop:shop", "shop:cart", "pages:about", "accounts:login", "accounts:register"})
                elif href.startswith("#"):
                    self.assertIn(href[1:], ids)

    def test_styles_are_internal_and_inside_the_head(self):
        self.assertEqual(self.html.count("<style>"), 1)
        self.assertLess(self.html.index("<style>"), self.html.index("</head>"))
        self.assertNotContains(self.response, 'rel="stylesheet"')
        self.assertNotContains(self.response, '<script')
        self.assertFalse(any("style" in attrs for _, attrs in self.elements))

    def test_photograph_and_fonts_are_embedded(self):
        photos = [attrs for tag, attrs in self.elements if tag == "img"]
        self.assertEqual(len(photos), 1)
        photo = photos[0]
        self.assertTrue(photo["src"].startswith("data:image/svg+xml;base64,"))
        self.assertIn("Pharmacy interior", photo["alt"])
        self.assertEqual((photo["width"], photo["height"]), ("365", "308"))
        self.assertContains(self.response, "data:font/woff;base64,", count=2)

    def test_no_external_resources_are_required(self):
        for tag, attrs in self.elements:
            if tag in {"img", "script", "source"}:
                self.assertTrue(attrs.get("src", "data:").startswith("data:"))
            if tag == "link":
                self.assertTrue(attrs["href"].startswith("data:"))
        self.assertNotContains(self.response, "/static/")
        self.assertNotContains(self.response, "@import")

    def test_preview_scope_and_image_source_are_disclosed(self):
        self.assertContains(self.response, "describe planned services and goals")
        self.assertContains(self.response, "They do not establish actual certification")
        self.assertContains(self.response, "photograph comes from the supplied design reference")

    def test_no_data_entry_controls_are_exposed(self):
        self.assertFalse(any(t in {"form", "input", "textarea", "select"} for t, _ in self.elements))

    def test_safe_request_methods_only(self):
        self.assertEqual(self.client.head(reverse("pages:about")).status_code, 200)
        self.assertEqual(self.client.post(reverse("pages:about"), {}).status_code, 405)

    def test_query_parameters_are_not_reflected(self):
        response = self.client.get(reverse("pages:about"), {"name": "<script>alert('x')</script>"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>")

    def test_public_root_and_unknown_pages(self):
        self.assertEqual(resolve("/").view_name, "home")
        self.assertEqual(self.client.get("/does-not-exist/").status_code, 404)

    @override_settings(ROOT_URLCONF=MountedURLs)
    def test_named_links_follow_a_new_mount_prefix(self):
        self.assertEqual(reverse("pages:about"), "/company/about/")
        response = self.client.get(reverse("pages:about"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/company/about/"', count=2)

    def test_existing_customer_routes_are_linked(self):
        self.assertContains(self.response, 'href="/login/"')
        self.assertContains(self.response, 'href="/register/"')
        self.assertEqual(resolve('/login/').view_name, 'accounts:login')
        self.assertEqual(resolve('/register/').view_name, 'accounts:register')
