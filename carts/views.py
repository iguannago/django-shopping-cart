import json
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from uuid import UUID

from django.core.exceptions import RequestDataTooBig
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .service import CartNotFound, CartService, Product, Receipt, is_valid_price


cart_service = CartService()


def _problem(status: int, detail: str, errors: dict | None = None) -> JsonResponse:
    body = {
        "type": "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
        "detail": detail,
    }
    if errors:
        body["errors"] = errors
    return JsonResponse(body, status=status, content_type="application/problem+json")


def _invalid_json_constant(value: str):
    raise ValueError(f"Invalid JSON number: {value}")


def _product_fields(body: dict) -> dict[str, list[str]]:
    errors = {}
    product_id = body.get("id")
    if not isinstance(product_id, str) or not product_id.strip():
        errors["id"] = ["Must be a non-blank string"]
    if not isinstance(body.get("name"), str):
        errors["name"] = ["Must be a string"]
    price = body.get("price")
    if not isinstance(price, Decimal) or not is_valid_price(price):
        errors["price"] = ["Must be a finite positive number within the supported range"]
    return errors


def _receipt_json(receipt: Receipt) -> HttpResponse:
    # JSONEncoder serialises Decimal as a string in Django. Emit the finite
    # decimal values as numeric tokens and use json.dumps to escape all text.
    lines = [
        (
            f'{{"product":{{"id":{json.dumps(line.product.id)},'
            f'"name":{json.dumps(line.product.name)},"price":{line.product.price}}},'
            f'"quantity":{line.quantity}}}'
        )
        for line in receipt.lines
    ]
    body = (
        f'{{"lines":[{",".join(lines)}],"subtotal":{receipt.subtotal},'
        f'"discount":{receipt.discount},"total":{receipt.total}}}'
    )
    return HttpResponse(body, content_type="application/json")


# These API routes use no cookie-based identity. Admin retains Django's CSRF protection.
@csrf_exempt
@require_POST
def create_cart(request):
    cart_id = cart_service.create_cart()
    return JsonResponse({"id": str(cart_id)}, status=201, headers={"Location": f"/carts/{cart_id}"})


@require_GET
def get_receipt(request, cart_id):
    try:
        cart_id = UUID(cart_id)
    except ValueError:
        return _problem(400, "Cart ID must be a UUID")
    try:
        receipt = cart_service.receipt(cart_id)
    except CartNotFound as error:
        return _problem(404, str(error))
    return _receipt_json(receipt)


@csrf_exempt
@require_POST
def add_item(request, cart_id):
    try:
        cart_id = UUID(cart_id)
    except ValueError:
        return _problem(400, "Cart ID must be a UUID")

    try:
        raw_body = request.body
        media_type = (request.content_type or "").lower()
        if raw_body and not (
            media_type == "application/json"
            or (media_type.startswith("application/") and media_type.endswith("+json"))
        ):
            return _problem(415, "Request body must use a JSON content type")
        body = json.loads(
            raw_body, parse_int=Decimal, parse_float=Decimal, parse_constant=_invalid_json_constant
        )
    except (ValueError, InvalidOperation, RequestDataTooBig, RecursionError):
        return _problem(400, "Request body is missing or could not be read")
    if not isinstance(body, dict):
        return _problem(400, "Request body must be a JSON object")
    errors = _product_fields(body)
    if errors:
        return _problem(400, "One or more request fields are invalid", errors)

    try:
        cart_service.add_product(cart_id, Product(body["id"], body["name"], body["price"]))
    except CartNotFound as error:
        return _problem(404, str(error))
    return HttpResponse(status=204)
