def handler(event):
    size = int(event["size"])
    buffer = size * ["asdf"]

    return {
        "buffer": buffer
    }