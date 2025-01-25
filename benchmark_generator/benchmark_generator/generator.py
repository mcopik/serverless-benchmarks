import sys
import json
import code_composer
import requirements_composer
import input_composer
import os

def read_config_file(file_path):
    try:
        with open(file_path, 'r') as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Failed to parse JSON from {file_path}.")
        sys.exit(1)

def write_to_file(file_path, content):
    try:
        with open(file_path, 'w+') as file:
            file.write(content)
    except Exception as e:
        print(f"Error writing to {file_path}: {e}")
        sys.exit(1)

def generate_and_write_code(config, language, path_to_benchmark):
    if language == "python":
        write_to_file(os.path.join(path_to_benchmark, "function.py"), code_composer.compose(config, "python"))
        write_to_file(os.path.join(path_to_benchmark, "requirements.txt"), requirements_composer.compose(config, "python"))
    elif language == "async_nodejs":
        write_to_file(os.path.join(path_to_benchmark, "function.js"), code_composer.compose(config, "async_nodejs"))
        write_to_file(os.path.join(path_to_benchmark, "package.json"), requirements_composer.compose(config, "async_nodejs"))

if len(sys.argv) < 2:
    print("Missing argument: path to config")
    sys.exit(1)

total_config = read_config_file(sys.argv[1])

config = total_config["config"]
language = total_config["language"]

path_to_benchmark_base = "./../benchmarks/600.generated/620.generated"

if language == "python":
    path_to_benchmark = os.path.join(path_to_benchmark_base, "python")
    if not os.path.exists(path_to_benchmark):
        os.makedirs(path_to_benchmark)
elif language == "async_nodejs":
    path_to_benchmark = os.path.join(path_to_benchmark_base, "nodejs")
    if not os.path.exists(path_to_benchmark):
        os.makedirs(path_to_benchmark)

generate_and_write_code(config, language, path_to_benchmark)

# Ensure path_to_benchmark is initialized before calling input_composer.compose
if "path_to_benchmark" in locals():
    write_to_file(os.path.join(path_to_benchmark, "../input.py"), input_composer.compose(config))
