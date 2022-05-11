import datetime
import json
import os
import uuid
import importlib

from azure.storage.blob import BlobServiceClient
import azure.functions as func
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


def main(event):
    start = datetime.datetime.now().timestamp()

    workflow_name = os.getenv("APPSETTING_WEBSITE_SITE_NAME")
    func_name = os.path.basename(os.path.dirname(__file__))

    module_name = f"{func_name}.{func_name}"
    module_path = f"{func_name}/{func_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    function = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(function)

    res = function.handler(event)

    end = datetime.datetime.now().timestamp()

    is_cold, container_id = probe_cold_start()
    payload = json.dumps({
        "func": func_name,
        "start": start,
        "end": end,
        "is_cold": is_cold,
        "container_id": container_id,
    })

    redis = Redis(host={{REDIS_HOST}},
          port=6379,
          decode_responses=True,
          socket_connect_timeout=10)

    key = os.path.join(workflow_name, func_name, str(uuid.uuid4())[0:8])
    redis.set(key, payload)

    return res
