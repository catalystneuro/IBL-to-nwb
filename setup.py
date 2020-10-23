from setuptools import setup, find_packages
from codecs import open
from os import path


here = path.abspath(path.dirname(__file__))


with open(path.join(here, 'README.md')) as f:
    long_description = f.read()

setup(
    name='ibl_to_nwb',
    version='0.1.2',
    description='Tools to convert IBL data to NWB format',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Saksham Sharda, Ben Dichter',
    author_email='saksham20.sharda@gmail.com',
    url='https://github.com/catalystneuro/IBL-to-nwb',
    keywords=['nwb', 'ibl'],
    packages=['ibl_to_nwb'],
    package_data={},
    include_package_data=False,
    install_requires=[
        'pynwb', 'numpy', 'pandas', 'scipy >= 1.4.1',
        'tqdm', 'tzlocal', 'ndx_ibl_metadata',
        'ndx-spectrum==0.2.2',
        'ibllib',
        'lazy_ops',
    ],
    python_requires='>=3.6'
)