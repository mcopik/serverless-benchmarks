
import datetime, io, json, os, uuid

import azure.functions as func


if 'NOSQL_STORAGE_DATABASE' in os.environ:

    from . import nosql

    nosql.nosql.get_instance(
        os.environ['NOSQL_STORAGE_DATABASE'],
        os.environ['NOSQL_STORAGE_URL'],
        os.environ['NOSQL_STORAGE_CREDS']
    )

if 'STORAGE_CONNECTION_STRING' in os.environ:

    from . import storage
    client = storage.storage.get_instance(os.environ['STORAGE_CONNECTION_STRING'])

# TODO: usual trigger
# implement support for blob and others
def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    income_timestamp = datetime.datetime.now().timestamp()
    req_json = req.get_json()

    req_json['request-id'] = context.invocation_id
    req_json['income-timestamp'] = income_timestamp
    begin = datetime.datetime.now()
    # We are deployed in the same directory
    from . import function
    ret = function.handler(req_json)
    end = datetime.datetime.now()

    log_data = {
        'output': ret['result']
    }
    if 'measurement' in ret:
        log_data['measurement'] = ret['measurement']
    if 'logs' in req_json:
        log_data['time'] = (end - begin) / datetime.timedelta(microseconds=1)
        results_begin = datetime.datetime.now()
        from . import storage
        storage_inst = storage.storage.get_instance()
        b = req_json.get('logs').get('bucket')
        req_id = context.invocation_id
        storage_inst.upload_stream(b, '{}.json'.format(req_id),
                io.BytesIO(json.dumps(log_data).encode('utf-8')))
        results_end = datetime.datetime.now()
        results_time = (results_end - results_begin) / datetime.timedelta(microseconds=1)
    else:
        results_time = 0

    # cold test
    is_cold = False
    fname = os.path.join('/tmp','cold_run')
    if not os.path.exists(fname):
        is_cold = True
        container_id = str(uuid.uuid4())[0:8]
        with open(fname, 'a') as f:
            f.write(container_id)
    else:
        with open(fname, 'r') as f:
            container_id = f.read()

    is_cold_worker = False
    global cold_marker
    try:
        _ = cold_marker
    except NameError:
        cold_marker = True
        is_cold_worker = True

    return func.HttpResponse(
        json.dumps({
            'begin': begin.strftime('%s.%f'),
            'end': end.strftime('%s.%f'),
            'results_time': results_time,
            'result': log_data,
            'is_cold': is_cold,
            'is_cold_worker': is_cold_worker,
            'container_id': container_id,
            'environ_container_id': os.environ['CONTAINER_NAME'],
            'request_id': context.invocation_id
        }),
        mimetype="application/json"
    )

