from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest import TestCase

from .service import CartService, Product


class CartServiceTests(TestCase):
    def setUp(self):
        self.service = CartService()
        self.cart = self.service.create_cart()
        self.coffee = Product("coffee", "Coffee", Decimal("2.50"))

    def test_grouping_removal_and_readding_with_new_details(self):
        replacement = Product("coffee", "New coffee", Decimal("3.00"))
        self.service.add_product(self.cart, self.coffee)
        self.service.add_product(self.cart, replacement)
        receipt = self.service.receipt(self.cart)
        self.assertEqual(receipt.lines[0].product, self.coffee)
        self.assertEqual(receipt.lines[0].quantity, 2)
        self.assertEqual(receipt.total, Decimal("5.00"))

        self.service.remove_product(self.cart, "coffee")
        self.assertEqual(self.service.receipt(self.cart).lines[0].quantity, 1)
        self.service.remove_product(self.cart, "coffee")
        self.service.remove_product(self.cart, "coffee")
        self.assertEqual(self.service.receipt(self.cart).lines, ())

        self.service.add_product(self.cart, replacement)
        self.assertEqual(self.service.receipt(self.cart).lines[0].product, replacement)

    def test_offers_combine_and_recalculate_after_quantity_changes(self):
        other = Product("tea", "Tea", Decimal("1.005"))
        for _ in range(2):
            self.service.enable_two_for_one(self.cart, "coffee")
            self.service.enable_twenty_percent(self.cart)
        for _ in range(3):
            self.service.add_product(self.cart, self.coffee)
        self.service.add_product(self.cart, other)
        self.service.add_product(self.cart, other)

        receipt = self.service.receipt(self.cart)
        self.assertEqual(receipt.subtotal, Decimal("9.510"))
        self.assertEqual(receipt.discount, Decimal("3.90"))
        self.assertEqual(receipt.total, Decimal("5.610"))

        for _ in range(3):
            self.service.remove_product(self.cart, "coffee")
        for _ in range(2):
            self.service.add_product(self.cart, self.coffee)
        self.assertEqual(self.service.receipt(self.cart).discount, Decimal("3.40"))

    def test_percentage_discount_rounds_a_half_penny_up(self):
        self.service.enable_twenty_percent(self.cart)
        self.service.add_product(self.cart, Product("sample", "Sample", Decimal("0.025")))
        self.assertEqual(self.service.receipt(self.cart).discount, Decimal("0.01"))

    def test_percentage_discount_rounds_once_across_the_cart(self):
        self.service.enable_twenty_percent(self.cart)
        self.service.add_product(self.cart, Product("coffee", "Coffee", Decimal("1.02")))
        self.service.add_product(self.cart, Product("tea", "Tea", Decimal("1.02")))
        self.assertEqual(self.service.receipt(self.cart).discount, Decimal("0.41"))

    def test_concurrent_additions_are_isolated_to_the_target_cart(self):
        other_cart = self.service.create_cart()

        def add(_):
            self.service.add_product(self.cart, self.coffee)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(add, range(40)))

        self.assertEqual(self.service.receipt(self.cart).lines[0].quantity, 40)
        self.assertEqual(self.service.receipt(other_cart).lines, ())

    def test_product_rejects_blank_id_and_invalid_prices(self):
        for product_id, price in (
            (" ", Decimal("1")),
            ("coffee", Decimal("0")),
            ("coffee", Decimal("-1")),
            ("coffee", Decimal("NaN")),
            ("coffee", Decimal("1e1000")),
        ):
            with self.subTest(product_id=product_id, price=price), self.assertRaises(ValueError):
                Product(product_id, "Coffee", price)
