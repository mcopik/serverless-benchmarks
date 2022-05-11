size_generators = {
    'test' : 10,
    'small' : 2**10,
    'large': 2**20
}

def buckets_count():
    return (0, 0)

def generate_input(data_dir, size, input_buckets, output_buckets, upload_func):
    return { 'size': size_generators[size] }