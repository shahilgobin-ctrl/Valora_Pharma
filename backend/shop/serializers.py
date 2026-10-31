"""Small JSON serializers; this project does not use Django REST Framework."""
from .pricing import cart_totals


def category_data(category):
    return {"id": category.pk, "name": category.name, "slug": category.slug, "description": category.description}


def product_data(product):
    return {"id": product.pk, "name": product.public_name, "slug": product.slug,
            "description": product.public_description, "strength": product.public_strength,
            "price": product.public_price, "stock_quantity": product.available_stock,
            "is_out_of_stock": product.is_out_of_stock, "category": category_data(product.category),
            "image": product.image_url, "is_prescription": product.requires_prescription,
            "is_active": bool(product.medicine_id and product.medicine.is_active), "created_at": product.created_at.isoformat() if product.created_at else None}


def cart_data(cart):
    items = [{"id": item.pk, "product": product_data(item.product), "quantity": item.quantity,
              "line_total": item.quantity * item.product.public_price} for item in cart.items.select_related("product", "product__category", "product__medicine")]
    subtotal = sum(item["line_total"] for item in items)
    totals = cart_totals(subtotal, has_items=bool(items))
    return {"items": items, "item_count": sum(item["quantity"] for item in items),
            **totals}


def order_data(order):
    return {"id": order.pk, "user_id": order.customer_id, "total": order.total_amount,
            "status": order.status, "delivery_method": order.delivery_method, "delivery_fee": order.delivery_fee, "payment_status": "succeeded", "simulated": True,
            "created_at": order.created_at.isoformat(),
            "items": [{"medicine_id": item.medicine_id, "quantity": item.quantity,
                       "unit_price": item.unit_price} for item in order.items.all()]}
