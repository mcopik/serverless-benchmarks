# SeBS Load Generator

## Overview

This tool allows the user to specify parameters for entry into a docker container.

## New Prerequisites
- Artillery
- Pyyaml

## Setup

### 1. Install Dependencies

`pip install artillery pyyaml`

### 2. Build Config File

`python artillery_generator <users> <phase duration> <num cycles>`

### 3. Run the File

`export PAYLOAD_FILE=/payloads/<benchmark_number>_payload.json`

`artillery run load_test_config.yml`

### 4. Enjoy!
