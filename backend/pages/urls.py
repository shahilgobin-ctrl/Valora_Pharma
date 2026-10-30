from django.urls import path

from . import views
from .contact_views import contact

app_name = "pages"

urlpatterns = [
    path("about/", views.about, name="about"),
    path("contact/", contact, name="contact"),
]
