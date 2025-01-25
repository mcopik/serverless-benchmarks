import os
import json

def read_file_content(file_path):
    """Read the content of a file."""
    try:
        with open(file_path, "r") as file:
            return file.read()
    except FileNotFoundError:
        print(f"Error: File {file_path} not found.")
        return ""
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return ""

def load_benchmark_requirements(benchmark_name):
    """Load requirements for a specific benchmark."""
    current_dir = os.getcwd()
    path_to_requirements = os.path.join(current_dir, benchmark_name, "python", "requirements.txt")
    
    if os.path.exists(path_to_requirements) and os.path.isfile(path_to_requirements):
        return read_file_content(path_to_requirements)
    else:
        print(f"Path to {path_to_requirements} does not exist.")
        return ""

def prepare_python_file(config):
    """Prepare requirements for Python benchmarks."""
    benchmarks_list = {benchmark for (benchmark, benchmark_config) in config.items()}
    
    requirements_for_all_benchmarks = ""
    for benchmark_name in benchmarks_list:
        requirements_for_all_benchmarks += "\n" + load_benchmark_requirements(benchmark_name)
    
    return requirements_for_all_benchmarks.strip()

def load_benchmark_dependencies(benchmark_name, language):
    """Load dependencies for a specific benchmark."""
    current_dir = os.getcwd()
    path_to_dependencies = os.path.join(current_dir, benchmark_name, language, "package.json")
    
    if os.path.exists(path_to_dependencies) and os.path.isfile(path_to_dependencies):
        try:
            with open(path_to_dependencies, "r") as json_file:
                package_json = json.load(json_file)
                return (package_json.get("dependencies", {}), package_json.get("devDependencies", {}))
        except json.JSONDecodeError:
            print(f"Error: Failed to decode JSON from {path_to_dependencies}.")
            return ({}, {})
    else:
        print(f"Path to {path_to_dependencies} does not exist.")
        return ({}, {})

def prepare_nodejs_file(config):
    """Prepare dependencies for Node.js benchmarks."""
    benchmarks_list = {benchmark for (benchmark, benchmark_config) in config.items()}

    dependencies_list = [load_benchmark_dependencies(benchmark_name, "nodejs") for benchmark_name in benchmarks_list]

    dependencies = {}
    dev_dependencies = {}
    for dependency, dev_dependency in dependencies_list:
        dependencies.update(dependency)
        dev_dependencies.update(dev_dependency)
    
    return json.dumps({
        "name": "generated_benchmark",
        "version": "1.0.0",
        "description": "",
        "author": "",
        "license": "",
        "dependencies": dependencies,
        "devDependencies": dev_dependencies
    })

def compose(config, language):
    """Compose the dependencies based on the language."""
    if language == "python":
        return prepare_python_file(config)
    elif language == "async_nodejs":
        return prepare_nodejs_file(config)
    else:
        print(f"Unsupported language: {language}")
        return ""
