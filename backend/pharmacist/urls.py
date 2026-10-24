from django.urls import path

from . import order_views, views


app_name = "pharmacist"

urlpatterns = [
    path("orders/<int:pk>/", order_views.order_record, name="order_record"),
    path("orders/<int:pk>/receipt/", order_views.receipt, name="receipt"),
    path("", order_views.dashboard, name="dashboard"),
    path("prescriptions/", views.prescription_queue, name="prescription_queue"),
    path("prescriptions/<int:pk>/", views.prescription_detail, name="prescription_detail"),
    path("prescriptions/<int:pk>/document/", views.prescription_document, name="prescription_document"),
    path("prescriptions/<int:pk>/document/preview/", views.prescription_document_preview, name="prescription_document_preview"),
    path("prescriptions/sample/", views.preview, {"page": "prescription_review"}, name="prescription_review"),
    path("orders/", order_views.order_queue, name="order_queue"),
    path("orders/sample/", views.preview, {"page": "order_detail"}, name="order_detail"),
    path("sales/new/", order_views.sale_form, name="sale_form"),
    path("sales/sample/receipt/", views.preview, {"page": "sale_receipt"}, name="sale_receipt"),
]