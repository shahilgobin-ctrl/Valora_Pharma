from django.db import models


class ContactMessage(models.Model):
    """A message submitted through the public Contact page."""

    full_name = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    phone = models.CharField(max_length=32, blank=True)
    subject = models.CharField(max_length=160)
    message = models.TextField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name}: {self.subject}"
