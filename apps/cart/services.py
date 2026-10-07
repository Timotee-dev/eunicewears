from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ProductVariant

from .models import Cart, CartItem

SESSION_KEY = "cart_id"
MAX_PER_LINE = 20


def get_cart(request, create: bool = False) -> Cart | None:
    if request.user.is_authenticated:
        if create:
            return Cart.objects.get_or_create(user=request.user)[0]
        return Cart.objects.filter(user=request.user).first()
    cart = Cart.objects.filter(pk=request.session.get(SESSION_KEY), user__isnull=True).first()
    if cart is None and create:
        cart = Cart.objects.create()
        request.session[SESSION_KEY] = cart.pk
    return cart


def cart_items(cart: Cart | None):
    if cart is None:
        return CartItem.objects.none()
    return cart.items.select_related("variant__product").prefetch_related("variant__product__images")


def purchasable(variant: ProductVariant) -> bool:
    p = variant.product
    return variant.is_active and p.is_published and p.archived_at is None


def _check_quantity(variant: ProductVariant, quantity: int) -> None:
    if not purchasable(variant):
        raise ValidationError("This item is no longer available.")
    if quantity > MAX_PER_LINE:
        raise ValidationError(f"You can buy up to {MAX_PER_LINE} of one item per order.")
    if quantity > variant.stock:
        raise ValidationError(
            f"Only {variant.stock} left in this size and colour." if variant.stock else "This size and colour is sold out."
        )


@transaction.atomic
def add_item(cart: Cart, variant_id: int, quantity: int) -> CartItem:
    variant = ProductVariant.objects.select_related("product").filter(pk=variant_id).first()
    if variant is None:
        raise ValidationError("This item is no longer available.")
    item = CartItem.objects.select_for_update().filter(cart=cart, variant=variant).first()
    total = quantity + (item.quantity if item else 0)
    _check_quantity(variant, total)
    if item:
        item.quantity = total
        item.save(update_fields=["quantity", "updated_at"])
        return item
    return CartItem.objects.create(cart=cart, variant=variant, quantity=quantity)


def set_quantity(item: CartItem, quantity: int) -> None:
    _check_quantity(item.variant, quantity)
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])


@transaction.atomic
def merge_guest_cart(request, user) -> None:
    """Called right after sign-in: fold the guest cart into the customer's saved cart."""
    guest = Cart.objects.filter(pk=request.session.pop(SESSION_KEY, None), user__isnull=True).first()
    if guest is None:
        return
    mine, _ = Cart.objects.get_or_create(user=user)
    for line in guest.items.select_related("variant"):
        existing = mine.items.filter(variant=line.variant).first()
        quantity = min((existing.quantity if existing else 0) + line.quantity, line.variant.stock, MAX_PER_LINE)
        if quantity < 1:
            continue
        if existing:
            existing.quantity = quantity
            existing.save(update_fields=["quantity", "updated_at"])
        else:
            CartItem.objects.create(cart=mine, variant=line.variant, quantity=quantity)
    guest.delete()


def summarize(cart: Cart | None) -> dict:
    """Server-computed view of the cart. Prices come from the database every time."""
    lines, subtotal, count, problems = [], 0, 0, False
    for item in cart_items(cart):
        v, p = item.variant, item.variant.product
        ok = purchasable(v) and v.stock >= item.quantity
        problems = problems or not ok
        images = list(p.images.all())
        line_total = v.unit_price * item.quantity
        if ok:
            subtotal += line_total
        count += item.quantity
        lines.append({
            "id": item.pk, "variant_id": v.pk, "product": p.name, "slug": p.slug, "label": v.label,
            "image": images[0].image.url if images else None, "unit_price": v.unit_price,
            "quantity": item.quantity, "line_total": line_total, "max_quantity": min(v.stock, MAX_PER_LINE),
            "available": ok,
            "problem": None if ok else ("No longer available" if not purchasable(v) or v.stock == 0 else f"Only {v.stock} left"),
        })
    return {"items": lines, "count": count, "subtotal": subtotal, "has_problems": problems, "currency": "NGN"}
