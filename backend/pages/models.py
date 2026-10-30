from django.db import models


class HomepageProductImage(models.Model):
    """Homepage-only artwork; never replaces the shop catalogue image."""
    product = models.OneToOneField("shop.Product", on_delete=models.CASCADE,
                                  related_name="homepage_image_override")
    image = models.CharField(max_length=500)

    def __str__(self):
        return f"Homepage image: {self.product.name}"
