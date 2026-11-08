from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from threading import Lock
from uuid import UUID, uuid4


_ZERO = Decimal("0")
_PERCENTAGE = Decimal("0.20")
_PENNY = Decimal("0.01")
_MAX_PRICE_PLACES = 1000


class CartNotFound(Exception):
    pass


def is_valid_price(price: Decimal) -> bool:
    # Bound the work of aligning exponents and serialising client-supplied prices.
    return (
        price.is_finite()
        and price > _ZERO
        and abs(price.as_tuple().exponent) <= _MAX_PRICE_PLACES
        and price.adjusted() < _MAX_PRICE_PLACES
    )


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    price: Decimal

    def __post_init__(self):
        if not self.id.strip():
            raise ValueError("Product ID must not be blank")
        if not is_valid_price(self.price):
            raise ValueError("Price must be finite, positive and within the supported range")


@dataclass(frozen=True)
class ReceiptLine:
    product: Product
    quantity: int


@dataclass(frozen=True)
class Receipt:
    lines: tuple[ReceiptLine, ...]
    subtotal: Decimal
    discount: Decimal
    total: Decimal


class _Cart:
    def __init__(self):
        self.lock = Lock()
        self.lines: dict[str, ReceiptLine] = {}
        self.two_for_one: set[str] = set()
        self.twenty_percent = False

    def add(self, product: Product):
        existing = self.lines.get(product.id)
        if existing is None:
            self.lines[product.id] = ReceiptLine(product, 1)
        else:
            self.lines[product.id] = ReceiptLine(existing.product, existing.quantity + 1)

    def remove(self, product_id: str):
        existing = self.lines.get(product_id)
        if existing is None:
            return
        if existing.quantity == 1:
            del self.lines[product_id]
        else:
            self.lines[product_id] = ReceiptLine(existing.product, existing.quantity - 1)

    def receipt(self) -> Receipt:
        lines = tuple(self.lines.values())
        if not lines:
            return Receipt(lines, _ZERO, _ZERO, _ZERO)

        # Allow for the price scale, carries across all units and the percentage
        # multiplication before rounding. Decimal's default 28 digits can round
        # inputs that the cart is otherwise able to represent exactly.
        highest_place = max(line.product.price.adjusted() for line in lines)
        lowest_place = min(line.product.price.as_tuple().exponent for line in lines)
        quantity_digits = len(str(sum(line.quantity for line in lines)))
        with localcontext() as context:
            context.prec = max(28, highest_place - min(lowest_place, -2) + quantity_digits + 4)
            subtotal = sum((line.product.price * line.quantity for line in lines), _ZERO)
            discount = sum(
                (
                    line.product.price * (line.quantity // 2)
                    for line in lines
                    if line.product.id in self.two_for_one
                ),
                _ZERO,
            )
            if self.twenty_percent:
                discount += ((subtotal - discount) * _PERCENTAGE).quantize(
                    _PENNY, rounding=ROUND_HALF_UP
                )
            return Receipt(lines, subtotal, discount, subtotal - discount)


class _InMemoryCartStore:
    def __init__(self):
        self._carts: dict[UUID, _Cart] = {}
        self._lock = Lock()

    def create(self) -> UUID:
        with self._lock:
            cart_id = uuid4()
            while cart_id in self._carts:
                cart_id = uuid4()
            self._carts[cart_id] = _Cart()
            return cart_id

    def get(self, cart_id: UUID) -> _Cart:
        with self._lock:
            try:
                return self._carts[cart_id]
            except KeyError:
                raise CartNotFound(f"Cart {cart_id} not found") from None


class CartService:
    def __init__(self):
        self._store = _InMemoryCartStore()

    def create_cart(self) -> UUID:
        return self._store.create()

    def add_product(self, cart_id: UUID, product: Product):
        cart = self._store.get(cart_id)
        with cart.lock:
            cart.add(product)

    def remove_product(self, cart_id: UUID, product_id: str):
        cart = self._store.get(cart_id)
        with cart.lock:
            cart.remove(product_id)

    def enable_two_for_one(self, cart_id: UUID, product_id: str):
        cart = self._store.get(cart_id)
        with cart.lock:
            cart.two_for_one.add(product_id)

    def enable_twenty_percent(self, cart_id: UUID):
        cart = self._store.get(cart_id)
        with cart.lock:
            cart.twenty_percent = True

    def receipt(self, cart_id: UUID) -> Receipt:
        cart = self._store.get(cart_id)
        with cart.lock:
            return cart.receipt()
