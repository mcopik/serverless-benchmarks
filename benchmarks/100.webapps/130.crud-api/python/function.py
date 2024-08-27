from . import nosql

nosql_client = nosql.nosql.get_instance()

nosql_table_name = "shopping_cart"


def add_product(cart_id: str, product_id: str, product_name: str, price: float, quantity: int):

    nosql_client.insert(
        nosql_table_name,
        ("cart_id", cart_id),
        ("product_id", product_id),
        {"price": price, "quantity": quantity, "name": product_name},
    )


def get_products(cart_id: str, product_id: str):
    return nosql_client.get(nosql_table_name, ("cart_id", cart_id), ("product_id", product_id))


def query_products(cart_id: str):

    res = nosql_client.query(
        nosql_table_name,
        ("cart_id", cart_id),
        "product_id",
    )

    products = []
    price_sum = 0
    quantity_sum = 0
    for product in res:

        products.append(product["name"])
        price_sum += product["price"]
        quantity_sum += product["quantity"]

    avg_price = price_sum / quantity_sum if quantity_sum > 0 else 0.0

    return {"products": products, "total_cost": price_sum, "avg_price": avg_price}


def handler(event):

    results = []

    for request in event["requests"]:

        route = request["route"]
        body = request["body"]

        if route == "PUT /cart":
            add_product(
                body["cart"], body["product_id"], body["name"], body["price"], body["quantity"]
            )
            res = {}
        elif route == "GET /cart/{id}":
            res = get_products(body["cart"], request["path"]["id"])
        elif route == "GET /cart":
            res = query_products(body["cart"])
        else:
            raise RuntimeError(f"Unknown request route: {route}")

        results.append(res)

    return {"result": results}
