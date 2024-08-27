import glob, os

def buckets_count():
    return (2, 0)

def upload_files(data_root, data_dir, upload_func):

    for root, dirs, files in os.walk(data_dir):
        prefix = os.path.relpath(root, data_root)
        for file in files:
            file_name = prefix + '/' + file
            filepath = os.path.join(root, file)
            upload_func(0, file_name, filepath)

'''
    Generate test, small and large workload for compression test.

    :param data_dir: directory where benchmark data is placed
    :param size: workload size
    :param input_buckets: input storage containers for this benchmark
    :param output_buckets:
    :param upload_func: upload function taking three params(bucket_idx, key, filepath)
'''
def generate_input(data_dir, size, benchmarks_bucket, input_paths, output_paths, upload_func, nosql_func):

    # upload model
    model_name = 'resnet50-19c8e357.pth'
    upload_func(0, model_name, os.path.join(data_dir, 'model', model_name))

    input_images = []
    resnet_path = os.path.join(data_dir, 'fake-resnet')
    with open(os.path.join(resnet_path, 'val_map.txt'), 'r') as f:
        for line in f:
            img, img_class = line.split()
            input_images.append((img, img_class))
            upload_func(1, img, os.path.join(resnet_path, img))
    
    input_config = {'object': {}, 'bucket': {}}
    input_config['object']['model'] = model_name
    input_config['object']['input'] = input_images[0][0]
    input_config['bucket']['bucket'] = benchmarks_bucket
    input_config['bucket']['input'] = input_paths[1]
    input_config['bucket']['model'] = input_paths[0]
    return input_config
