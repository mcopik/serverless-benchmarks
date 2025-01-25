import uuid

def generate_input_dict(benchmark_config):
    """Generate input dictionary based on input_size in benchmark_config."""
    input_dict = {}
    if "input_size" in benchmark_config:
        for _ in range(int(benchmark_config["input_size"])):
            input_dict[str(uuid.uuid1())] = 100
    return input_dict

def generate_buckets_count_code(benchmarks_list):
    """Generate buckets_count function code."""
    if "storage" in benchmarks_list:
        return """def buckets_count():
    return (0, 1)\n"""
    else:
        return """def buckets_count():
    return (0, 0)\n"""

def generate_generate_input_code(benchmarks_list):
    """Generate generate_input function code."""
    if "storage" in benchmarks_list:
        return """def generate_input(data_dir, size, input_buckets, output_buckets, upload_func):
    input_dict = {'bucket': {}}
    input_dict['bucket']['output'] = output_buckets[0]
    return input_dict """
    else:  
        return """def generate_input(data_dir, size, input_buckets, output_buckets, upload_func):
    return input_dict """

def generate_code(config):
    benchmarks_list = {benchmark for (benchmark, _) in config.items()}

    input_dict = {}
    for benchmark, benchmark_config in config.items():
        if benchmark == "function_input":
            input_dict = generate_input_dict(benchmark_config)
            break

    code = ""
    code += "input_dict = " + str(input_dict) + "\n"
    code += generate_buckets_count_code(benchmarks_list)
    code += generate_generate_input_code(benchmarks_list)
    
    return code
