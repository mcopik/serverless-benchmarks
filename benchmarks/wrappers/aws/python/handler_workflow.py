
import datetime
import io
import json
import os
import sys
import uuid
import importlib

# Add current directory to allow location of packages
sys.path.append(os.path.join(os.path.dirname(__file__), '.python_packages/lib/site-packages'))

from redis import Redis

def probe_cold_start():
    is_cold = False
    fname = os.path.join("/tmp", "cold_run")
    if not os.path.exists(fname):
        is_cold = True
        container_id = str(uuid.uuid4())[0:8]
        with open(fname, "a") as f:
            f.write(container_id)
    else:
        with open(fname, "r") as f:
            container_id = f.read()

    return is_cold, container_id


def handler(event, context):
    start = datetime.datetime.now().timestamp()

    workflow_name, func_name = context.function_name.split("___")
    function = importlib.import_module(f"function.{func_name}")
    res = function.handler(event)

    end = datetime.datetime.now().timestamp()

    is_cold, container_id = probe_cold_start()
    payload = json.dumps({
        "func": func_name,
        "start": start,
        "end": end,
        "is_cold": is_cold,
        "container_id": container_id
    })

    redis = Redis(host={{REDIS_HOST}},
                  port=6379,
                  decode_responses=True,
                  socket_connect_timeout=10)

    key = os.path.join(workflow_name, func_name, str(uuid.uuid4())[0:8])
    redis.set(key, payload)

    return res
