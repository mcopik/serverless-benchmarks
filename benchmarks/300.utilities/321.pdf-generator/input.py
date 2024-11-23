import os
import glob

def buckets_count():
    return (1, 1)  # One input bucket, one output bucket

def generate_input(data_dir, size, benchmarks_bucket, input_paths, output_paths, upload_func):
    # The HTML file and the images directory
    input_file_path = os.path.join(data_dir, 'template', 'demo.html')
    images_dir = os.path.join(data_dir, 'template', 'images')  # Directory path

    # Initialize input_config with 'object' and 'bucket' fields
    input_config = {'object': {}, 'bucket': {}}
    
    # Upload the HTML file to the input bucket
    upload_func(0, "demo.html", input_file_path)
    
    # Prepare the bucket configuration
    input_config['bucket']['bucket'] = benchmarks_bucket
    input_config['bucket']['input'] = input_paths[0]
    input_config['bucket']['output'] = output_paths[0]

    # Upload each image in the images directory to the input bucket
    for file in glob.glob(os.path.join(images_dir, '*.png')):
        img = os.path.relpath(file, data_dir)
        upload_func(0, img, file)

    # Store the list of image file configurations in 'object'
    input_config['object']['key'] = "images/"
    input_config['object']['input_file'] = 'demo.html'

    return input_config
