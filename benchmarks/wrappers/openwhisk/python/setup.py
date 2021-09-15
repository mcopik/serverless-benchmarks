from distutils.core import setup
from glob import glob
from pkg_resources import parse_requirements

with open('requirements.txt') as f:
    requirements = [str(r) for r in parse_requirements(f)]

setup(
    name='function',
    install_requires=requirements,
    packages=['function'],
    package_dir={'function': '.'},
    package_data={'function': glob('**', recursive=True)},
)