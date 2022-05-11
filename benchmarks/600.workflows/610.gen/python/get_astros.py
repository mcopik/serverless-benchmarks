import requests

def handler(event):
    res = requests.get("http://api.open-notify.org/astros.json")

    return {
        "astros": res.json()
    }