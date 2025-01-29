import glob, os

def buckets_count():
    return (1, 1)

def generate_input(data_dir, size, benchmarks_bucket, input_paths, output_paths, upload_func):

    for file in glob.glob(os.path.join(data_dir, '*.jpg')):
        img = os.path.relpath(file, data_dir)
        upload_func(0, img, file)

    input_config = {'object': {}, 'bucket': {}}
    input_config['object']['key'] = img
    input_config['bucket']['bucket'] = benchmarks_bucket
    input_config['bucket']['input'] = input_paths[0]
    input_config['bucket']['output'] = output_paths[0]
    return input_config
