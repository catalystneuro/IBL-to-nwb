"""Setup and package the ibl-to-nwb project."""
from pathlib import Path
from setuptools import setup


root = Path(__file__)


with open(root / "README.md") as file:
    long_description = file.read()

with open(root / "requirements.txt") as f:
    install_requires = f.readlines()

setup(
    name='ibl_to_nwb',
    version='0.2.0',
    description='Tools to convert IBL data to NWB format.',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Cody Baker and Ben Dichter',
    author_email='ben.dichter@catalystneuro.com',
    url='https://github.com/catalystneuro/IBL-to-nwb',
    keywords=['nwb', 'ibl'],
    package_data={},
    include_package_data=False,
    install_requires=install_requires,
    python_requires='>=3.8'
)
