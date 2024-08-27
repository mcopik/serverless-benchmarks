import uuid


def allocate_nosql() -> dict:
    return {"shopping_cart": {"primary_key": "cart_id", "secondary_key": "product_id"}}


def generate_input(
    data_dir, size, benchmarks_bucket, input_buckets, output_buckets, upload_func, nosql_func
):

    input_config = {}

    cart_id = str(uuid.uuid4().hex)
    write_cart_id = str(uuid.uuid4().hex)

    # Set initial data

    nosql_func(
        "130.crud-api",
        "shopping_cart",
        {"name": "Gothic Game", "price": 42, "quantity": 2},
        ("cart_id", cart_id),
        ("product_id", "game-gothic"),
    )
    nosql_func(
        "130.crud-api",
        "shopping_cart",
        {"name": "Gothic 2", "price": 142, "quantity": 3},
        ("cart_id", cart_id),
        ("product_id", "game-gothic-2"),
    )
    nosql_func(
        "130.crud-api",
        "shopping_cart",
        {"name": "SeBS Benchmark", "price": 1000, "quantity": 1},
        ("cart_id", cart_id),
        ("product_id", "sebs-benchmark"),
    )
    nosql_func(
        "130.crud-api",
        "shopping_cart",
        {"name": "Mint Linux", "price": 0, "quantity": 5},
        ("cart_id", cart_id),
        ("product_id", "mint-linux"),
    )

    requests = []

    if size == "test":
        # retrieve a single entry
        requests.append(
            {
                "route": "GET /cart/{id}",
                "path": {"id": "game-gothic"},
                "body": {
                    "cart": cart_id,
                },
            }
        )
    elif size == "small":
        requests.append(
            {
                "route": "GET /cart",
                "body": {
                    "cart": cart_id,
                },
            }
        )
    elif size == "large":
        # add many new entries
        for i in range(5):
            requests.append(
                {
                    "route": "PUT /cart",
                    "body": {
                        "cart": write_cart_id,
                        "product_id": f"new-id-{i}",
                        "name": f"Test Item {i}",
                        "price": 100 * i,
                        "quantity": i,
                    },
                }
            )
            requests.append(
                {
                    "route": "GET /cart",
                    "body": {
                        "cart": write_cart_id,
                    },
                }
            )

    input_config["requests"] = requests

    return input_config
