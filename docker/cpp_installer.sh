#!/bin/bash

mkdir -p /mnt/function/build
cmake3 -DCMAKE_BUILD_TYPE=Release -S /mnt/function/ -B /mnt/function/build > /mnt/function/build/configuration.log
VERBOSE=1 cmake3 --build /mnt/function/build --target aws-lambda-package-benchmark > /mnt/function/build/compilation.log

