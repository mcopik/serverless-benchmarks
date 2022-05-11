def handler(event):
    return {
        "many_astros": True,
        **event
    }