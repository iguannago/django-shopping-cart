import json
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import SimpleTestCase

from .service import CartService


class CartApiTests(SimpleTestCase):
    def setUp(self):
        self.enterContext(patch("carts.views.cart_service", CartService()))
        response = self.client.post("/carts")
        self.assertEqual(response.status_code, 201)
        cart_id = UUID(response.json()["id"])
        self.location = response.headers["Location"]
        self.assertEqual(self.location, f"/carts/{cart_id}")

    def _receipt(self):
        response = self.client.get(f"{self.location}/receipt")
        self.assertEqual(response.status_code, 200)
        return response.json(parse_float=Decimal)

    def test_create_cart_add_item_and_read_receipt_with_exact_money(self):
        self.assertEqual(self._receipt(), {"lines": [], "subtotal": 0, "discount": 0, "total": 0})
        price = "2.123456789012345678901234567891"
        body = '{"id":"coffee","name":"Coffee \\"blend\\"","price":' + price + "}"
        for _ in range(2):
            response = self.client.post(
                f"{self.location}/items", body, content_type="application/json"
            )
            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.content, b"")

        self.assertEqual(
            self._receipt(),
            {
                "lines": [
                    {
                        "product": {"id": "coffee", "name": 'Coffee "blend"', "price": Decimal(price)},
                        "quantity": 2,
                    }
                ],
                "subtotal": Decimal("4.246913578024691357802469135782"),
                "discount": 0,
                "total": Decimal("4.246913578024691357802469135782"),
            },
        )

    def test_unknown_and_malformed_cart_ids_return_problem_responses(self):
        for cart_id, expected_status in ((uuid4(), 404), ("invalid", 400)):
            with self.subTest(cart_id=cart_id):
                receipt = self.client.get(f"/carts/{cart_id}/receipt")
                item = self.client.post(
                    f"/carts/{cart_id}/items",
                    json.dumps({"id": "coffee", "name": "Coffee", "price": 2.5}),
                    content_type="application/json",
                )
                for response in (receipt, item):
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                    self.assertEqual(response.json()["status"], expected_status)

    def test_invalid_bodies_do_not_mutate_cart(self):
        for body, expected_field in (
            ('{"id":', None),
            ("[]", None),
            ('{"id":" ","name":"Coffee","price":2.5}', "id"),
            ('{"id":"coffee","name":null,"price":2.5}', "name"),
            ('{"id":"coffee","name":"Coffee","price":0}', "price"),
            ('{"id":"coffee","name":"Coffee","price":true}', "price"),
        ):
            with self.subTest(body=body):
                response = self.client.post(
                    f"{self.location}/items", body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.headers["Content-Type"], "application/problem+json")
                if expected_field:
                    self.assertIn(expected_field, response.json()["errors"])
        self.assertEqual(self._receipt()["lines"], [])

    def test_non_json_media_type_does_not_mutate_cart(self):
        response = self.client.post(
            f"{self.location}/items",
            '{"id":"coffee","name":"Coffee","price":2.5}',
            content_type="text/plain",
        )
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.headers["Content-Type"], "application/problem+json")
        self.assertEqual(self._receipt()["lines"], [])
