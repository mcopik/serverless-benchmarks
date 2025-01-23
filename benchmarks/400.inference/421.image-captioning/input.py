import glob
import os

def buckets_count():
    return (1, 1)

'''
    Generate test, small, and large workload for image captioning benchmark.

    :param data_dir: Directory where benchmark data is placed
    :param size: Workload size
    :param benchmarks_bucket: Storage container for the benchmark
    :param input_paths: List of input paths
    :param output_paths: List of output paths
    :param upload_func: Upload function taking three params (bucket_idx, key, filepath)
'''
def generate_input(data_dir, size, benchmarks_bucket, input_paths, output_paths, upload_func):
    input_files = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        input_files.extend(glob.glob(os.path.join(data_dir, ext)))
    
    if not input_files:
        raise ValueError("No input files found in the provided directory.")

    for file in input_files:
        img = os.path.relpath(file, data_dir)
        upload_func(0, img, file)

    input_config = {
        'object': {
            'key': img,
            'width': 200,
            'height': 200
        },
        'bucket': {
            'bucket': benchmarks_bucket,
            'input': input_paths[0],
            'output': output_paths[0]
        }
    }
    
    return input_config
