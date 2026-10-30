"""URL routes for pharmacist workflows."""

from django.urls import path

from . import views

app_name = "pharmacist"

urlpatterns = [
    # Dashboard.
    path("", views.dashboard, name="dashboard"),

    # Prescription queue and review.
    path("prescriptions/", views.prescription_queue, name="prescription_queue"),
    path("prescriptions/<int:pk>/", views.prescription_detail, name="prescription_detail"),
    path("prescriptions/<int:pk>/document/", views.prescription_document, name="prescription_document"),
    path("prescriptions/<int:pk>/document/preview/", views.prescription_document_preview, name="prescription_document_preview"),

    # Orders and receipts.
    path("orders/", views.order_queue, name="order_queue"),
    path("orders/<int:pk>/", views.order_record, name="order_record"),
    path("orders/<int:pk>/receipt/", views.receipt, name="receipt"),

    # Walk-in sales.
    path("sales/new/", views.sale_form, name="sale_form"),

    # Inventory.
    path("inventory/", views.inventory_list, name="inventory"),

]
