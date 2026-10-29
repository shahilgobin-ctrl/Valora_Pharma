"""Small JSON serializers; this project does not use Django REST Framework."""


def category_data(category):
    return {"id": category.pk, "name": category.name, "slug": category.slug, "description": category.description}


def product_data(product):
    return {"id": product.pk, "name": product.name, "slug": product.slug,
            "description": product.description, "strength": product.strength,
            "price": product.price, "stock_quantity": product.stock_quantity,
            "is_out_of_stock": product.is_out_of_stock, "category": category_data(product.category),
            "image": product.image, "is_prescription": product.is_prescription,
            "is_active": product.is_active, "created_at": product.created_at.isoformat() if product.created_at else None}


def cart_data(cart):
    items = [{"id": item.pk, "product": product_data(item.product), "quantity": item.quantity,
              "line_total": item.quantity * item.product.price} for item in cart.items.select_related("product", "product__category")]
    subtotal = sum(item["line_total"] for item in items)
    delivery = 100 if items else 0
    return {"items": items, "item_count": sum(item["quantity"] for item in items),
            "subtotal": subtotal, "delivery": delivery, "total": subtotal + delivery}


def order_data(order):
    return {"id": order.pk, "user_id": order.user_id, "delivery_method": order.delivery_method, "total": order.total,
            "status": order.status, "created_at": order.created_at.isoformat() if order.created_at else None,
            "items": [{"product_id": item.product_id, "quantity": item.quantity, "unit_price": item.unit_price}
                      for item in order.items.all()]}
