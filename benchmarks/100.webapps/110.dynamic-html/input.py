
size_generators = {
    'test' : 10,
    'small' : 1000,
    'large': 100000
}

def generate_input(data_dir, size, benchmarks_bucket, input_paths, output_paths, upload_func, nosql_func):
    input_config = {'username': 'testname'} 
    input_config['random_len'] = size_generators[size]
    return input_config
