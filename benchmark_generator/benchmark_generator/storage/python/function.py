#test
result = {}
config = {
    "entries_number": 1000
}
number = 0
event = {}

#import
import storage
import uuid
import time
import traceback
import io

#function
def generate_data(entries_number):
    dict_to_fill = {}
    for i in range(entries_number):
        dict_to_fill[str(uuid.uuid1())] = str(uuid.uuid1())
    return dict_to_fill

def upload_to_bucket(config, bytes_buffer):
    (client, output_bucket) = config
    try:
        key_name = client.upload_stream(output_bucket, "sebs_test.sth", bytes_buffer)
    except Exception as inst:
        key_name = str(inst) + "\n" + traceback.format_exc()
    return key_name

def download_from_bucket(config, file_key):
    (client, output_bucket) = config
    buffer = client.download_stream(output_bucket, file_key)
    downloaded_size = len(buffer.tobytes())
    return downloaded_size    

def test_bucket_like(config, dict_to_upload):
    string_to_upload = str(dict_to_upload)
    bytes_to_upload = str.encode(string_to_upload)
    buffer_to_upload = io.BytesIO(bytes_to_upload)
    t0 = time.perf_counter()
    key = upload_to_bucket(config, buffer_to_upload)
    t1 = time.perf_counter()
    downloaded_bytes = download_from_bucket(config, key)
    t2 = time.perf_counter()
    return {
        "uploaded_to_bucket_bytes": len(bytes_to_upload),
        "upload_time": t1 - t0,
        "downloaded_from_bucket_bytes": downloaded_bytes,
        "download_time": t2 - t1,
        "key": key
    }

def test_storage(dict_to_upload, config, storage_type="bucket"):
    if storage_type == "bucket":
        return test_bucket_like(config, dict_to_upload)
    # elif other storage types:
    #   return ...
    else:
        return {}   
  
#run
output_bucket = event.get('bucket').get('output')
entries_number = config.get("entries_number", 10)
client = storage.storage.get_instance()
dict_to_upload = generate_data(entries_number)
bucket_config = (client, output_bucket)
result[str(number)] = test_storage(dict_to_upload, bucket_config)
print(result)
