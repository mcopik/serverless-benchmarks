import glob, os

def buckets_count():
    return (1, 1)

'''
    Generate test, small and large workload for thumbnailer.

    :param data_dir: directory where benchmark data is placed
    :param size: workload size
    :param input_buckets: input storage containers for this benchmark
    :param output_buckets:
    :param upload_func: upload function taking three params(bucket_idx, key, filepath)
'''
def generate_input(data_dir, size, benchmarks_bucket, input_paths, output_paths, upload_func, nosql_func):

    for file in glob.glob(os.path.join(data_dir, '*.jpg')):
        img = os.path.relpath(file, data_dir)
        upload_func(0, img, file)

    #TODO: multiple datasets
    input_config = {'object': {}, 'bucket': {}}
    input_config['object']['key'] = img
    input_config['object']['width'] = 200
    input_config['object']['height'] = 200
    input_config['bucket']['bucket'] = benchmarks_bucket
    input_config['bucket']['input'] = input_paths[0]
    input_config['bucket']['output'] = output_paths[0]
    return input_config
