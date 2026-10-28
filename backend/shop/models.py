from django.conf import settings
from django.db import models
from django.utils.text import slugify

from .images import catalogue_image_url


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=110, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.CharField(max_length=500, blank=True, help_text="Condition illustration URL or static-relative path.")
    display_order = models.PositiveIntegerField(default=100)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def card_image_url(self):
        return catalogue_image_url(self.image or getattr(self, "card_image", ""))

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    strength = models.CharField(max_length=100, blank=True)
    price = models.PositiveIntegerField(help_text="Price in Rs")
    stock_quantity = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    image = models.CharField(max_length=500, blank=True)
    is_prescription = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    homepage_order = models.PositiveIntegerField(default=100, help_text="Lower numbers appear first on the homepage.")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def image_url(self):
        """Share the same catalogue image and fallback across HTML and JSON."""
        return catalogue_image_url(self.image)

    @property
    def is_out_of_stock(self):
        return self.stock_quantity == 0

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shop_cart")
    updated_at = models.DateTimeField(auto_now=True)


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("cart", "product"), name="shop_cart_item_unique_product")]


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "placed", "Placed"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="shop_orders")
    total = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED)
    created_at = models.DateTimeField(auto_now_add=True)
    prescription_file = models.FileField(upload_to="prescriptions/", blank=True)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.PositiveIntegerField()

class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount_total = models.PositiveIntegerField()
    amount_paid = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)


class ShopSettings(models.Model):
    """One admin-managed record for shop-wide commercial settings."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    delivery_fee = models.PositiveIntegerField(default=0, help_text="Delivery charge in Rs for a non-empty cart.")
    hero_image = models.CharField(max_length=500, blank=True, help_text="Homepage hero image URL or static-relative path.")

    @property
    def hero_image_url(self):
        return catalogue_image_url(self.hero_image or "accounts/assets/pharmacy-shelves.png")

    class Meta:
        verbose_name = "shop settings"
        verbose_name_plural = "shop settings"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="shop_settings_single_record")]

    def __str__(self):
        return "Shop settings"
