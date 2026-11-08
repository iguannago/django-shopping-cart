# Django shopping cart

A local shopping-cart kata built with Python and Django.

## Run locally

From the repository root with Python 3.12 installed:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Run the checks and tests with:

```sh
.venv/bin/python manage.py check
.venv/bin/python manage.py test
```

## API

| Method and path | Result |
| --- | --- |
| `POST /carts` | `201` with the cart UUID in the JSON `id` field and a `Location` header |
| `POST /carts/{id}/items` | Add one unit and return `204`. Send JSON such as `{"id":"coffee","name":"Coffee","price":2.50}`. |
| `GET /carts/{id}/receipt` | `200` with grouped product lines and numeric `subtotal`, `discount` and `total` fields |

An unknown cart returns `404`. Invalid UUIDs or JSON bodies return `400`.
Non-JSON request media types return `415`.
Prices must be finite and positive. The accepted decimal exponent is −1000 to
1000, and the integer part may have at most 1000 digits.

Carts are held in memory, shared by requests in one server process and lost
on restart. Removal and offers are available through the cart service.
