import datetime
import io
from urllib.parse import unquote_plus
from PIL import Image
import torch
from transformers import VisionEncoderDecoderModel, ViTImageProcessor, AutoTokenizer
from . import storage

# Load the pre-trained ViT-GPT2 model
model = VisionEncoderDecoderModel.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
image_processor = ViTImageProcessor.from_pretrained("nlpconnect/vit-gpt2-image-captioning")
tokenizer = AutoTokenizer.from_pretrained("nlpconnect/vit-gpt2-image-captioning")

model.eval()

client = storage.storage.get_instance()

def generate_caption(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    pixel_values = image_processor(images=image, return_tensors="pt").pixel_values

    with torch.no_grad():
        generated_ids = model.generate(pixel_values, max_length=16, num_beams=4)
        generated_text = tokenizer.decode(generated_ids[0], skip_special_tokens=True)

    return generated_text

def handler(event):
    bucket = event.get('bucket').get('bucket')
    input_prefix = event.get('bucket').get('input')
    key = unquote_plus(event.get('object').get('key'))
    
    download_begin = datetime.datetime.now()
    img = client.download_stream(bucket, os.path.join(input_prefix, key))
    download_end = datetime.datetime.now()

    process_begin = datetime.datetime.now()
    caption = generate_caption(img)
    process_end = datetime.datetime.now()

    download_time = (download_end - download_begin) / datetime.timedelta(microseconds=1)
    process_time = (process_end - process_begin) / datetime.timedelta(microseconds=1)

    return {
        'result': {
            'caption': caption,
        },
        'measurement': {
            'download_time': download_time,
            'download_size': len(img),
            'compute_time': process_time
        }
    }
