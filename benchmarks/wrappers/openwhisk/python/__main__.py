import logging
import datetime
import os


def main(args):
    logging.getLogger().setLevel(logging.INFO)
    begin = datetime.datetime.now()
    args['request-id'] = os.getenv('__OW_ACTIVATION_ID')
    args['income-timestamp'] = begin.timestamp()

    from function import function
    ret = function.handler(args)

    end = datetime.datetime.now()
    logging.info("Function result: {}".format(ret))
    log_data = {"result": ret["result"]}
    if "measurement" in ret:
        log_data["measurement"] = ret["measurement"]

    results_time = (end - begin) / datetime.timedelta(microseconds=1)

    is_cold = False
    fname = "cold_run"
    if not os.path.exists(fname):
        is_cold = True
        open(fname, "a").close()

    return {
        "begin": begin.strftime("%s.%f"),
        "end": end.strftime("%s.%f"),
        "request_id": os.getenv('__OW_ACTIVATION_ID'),
        "results_time": results_time,
        "is_cold": is_cold,
        "result": log_data,
    }
