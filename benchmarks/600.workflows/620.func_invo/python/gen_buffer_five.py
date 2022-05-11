def handler(event):
    size = int(event["size"]) if isinstance(event, dict) else len(event)
    data = (str(i % 255) for i in range(size))
    data = "".join(data)

    return data