import yaml
import sys
import argparse
import math

def create_yaml_config(max_users, frequency, cycles):
    """
    Create a YAML configuration for load testing with a sinusoidal pattern.
    
    :param max_users: Maximum number of concurrent users
    :param frequency: Duration of each cycle in seconds
    :param cycles: Number of cycles to run
    :return: Dictionary containing the YAML configuration
    """
    # Define the initial configuration dictionary
    config = {
        'config': {
            'target': 'http://172.17.0.2:9000',  # Target URL for the load test
            'phases': [],  # List to store the different phases of the load test
            'ensure': {
                'p95': 2000  # Ensure 95% of responses are under 2000ms
            }
        },
        'scenarios': [
            {
                'flow': [
                    {
                        'post': {
                            'url': '/post',
                            'json': '{{ payload }}'  # JSON payload for the POST request
                        }
                    }
                ]
            }
        ],
        'payload': '{{ $processEnvironment.PAYLOAD_FILE }}'  # Reference to the environment variable for payload file
    }

    # Generate phases for each cycle
    for i in range(cycles):
        for j in range(10):  # 10 phases per cycle for a smoother sinusoidal pattern
            phase_duration = max(1, int(frequency / 10))  # Ensure phase duration is at least 1 second
            t = j / 10  # Time variable from 0 to 1
            users = int(max_users * (math.sin(2 * math.pi * t) + 1) / 2)  # Calculate users using sine function
            
            # Append the phase configuration to the phases list
            config['config']['phases'].append({
                'duration': phase_duration,
                'arrivalRate': users,
                'name': f'Cycle {i+1}, Phase {j+1}'
            })

    return config

def main():
    """
    Main function to parse command-line arguments and generate the YAML configuration file.
    """
    # Set up command-line argument parser
    parser = argparse.ArgumentParser(description='Generate YAML config for load testing')
    parser.add_argument('max_users', type=int, help='Maximum number of users (1-1000)')
    parser.add_argument('frequency', type=int, help='Duration of each cycle in seconds (1-50)')
    parser.add_argument('cycles', type=int, help='Number of cycles (1-50)')
    
    args = parser.parse_args()

    # Generate YAML configuration using the input parameters
    config = create_yaml_config(args.max_users, args.frequency, args.cycles)

    # Write YAML configuration to file
    with open('load_test_config.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    print("YAML configuration file 'load_test_config.yaml' has been created.")

if __name__ == '__main__':
    main()
