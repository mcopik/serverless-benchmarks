import uuid

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def handler(event):
    segs = chunks(event["segments"], event["batch_size"])
    input_bucket = event["input_bucket"]
    output_bucket = event["output_bucket"]
    benchmark_bucket = event["benchmark_bucket"]
    quality = event["quality"]

    return {
        "segments": [
            {
                "prefix": str(uuid.uuid4().int & (1<<64)-1)[:8],
                "segments": ss,
                "quality": quality,
                "input_bucket": input_bucket,
                "output_bucket": output_bucket,
                "benchmark_bucket": benchmark_bucket
            } for idx, ss in enumerate(segs)
        ]
    }
