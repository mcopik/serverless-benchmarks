def handler(event):
    return {
        "many_astros": False,
        **event
    }