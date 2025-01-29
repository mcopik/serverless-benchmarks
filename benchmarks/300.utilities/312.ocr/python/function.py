import datetime
import io
import os
import sys
import uuid
from urllib.parse import unquote_plus
from PIL import Image
import pytesseract

from . import storage
client = storage.storage.get_instance()

# Memory-based solution
def ocr_image(image_bytes):
    with Image.open(io.BytesIO(image_bytes)) as image:
        ocr_text = pytesseract.image_to_string(image)
        return ocr_text

def handler(event):
  
    bucket = event.get('bucket').get('bucket')
    input_prefix = event.get('bucket').get('input')
    output_prefix = event.get('bucket').get('output')
    key = unquote_plus(event.get('object').get('key'))
    download_begin = datetime.datetime.now()
    img = client.download_stream(bucket, os.path.join(input_prefix, key))
    download_end = datetime.datetime.now()

    process_begin = datetime.datetime.now()
    ocr_result = ocr_image(img)
    process_end = datetime.datetime.now()

    upload_begin = datetime.datetime.now()
    output_key = f"{os.path.splitext(key)[0]}_ocr.txt"
    key_name = client.upload_stream(bucket, os.path.join(output_prefix, output_key), ocr_result.encode('utf-8'))
    upload_end = datetime.datetime.now()

    download_time = (download_end - download_begin) / datetime.timedelta(microseconds=1)
    upload_time = (upload_end - upload_begin) / datetime.timedelta(microseconds=1)
    process_time = (process_end - process_begin) / datetime.timedelta(microseconds=1)
    return {
            'result': {
                'bucket': bucket,
                'key': key_name
            },
            'measurement': {
                'download_time': download_time,
                'download_size': len(img),
                'upload_time': upload_time,
                'upload_size': len(ocr_result),
                'compute_time': process_time
            }
    }
