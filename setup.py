from setuptools import setup, find_packages
from codecs import open
from os import path


here = path.abspath(path.dirname(__file__))


with open(path.join(here, 'README.md')) as f:
    long_description = f.read()

setup(
    name='ibl_to_nwb',
    version='0.1.0',
    description='Tools to convert IBL data to NWB format',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Saksham Sharda, Ben Dichter',
    author_email='saksham20.sharda@gmail.com',
    url='https://github.com/catalystneuro/IBL-to-nwb',
    keywords=['nwb', 'ibl'],
    packages=find_packages(),
    package_data={},
    include_package_data=True,
    install_requires=[
        'pynwb', 'numpy', 'nwbwidgets', 'pandas', 'pyarrow', 'scipy >= 1.4.1',
        'tqdm', 'tzlocal', 'datajoint', 'mtscomp', 'ndx_ibl_metadata',
        'git+https://github.com/catalystneuro/nwb-conversion-tools.git@fb9703f8e86072f04356883975e5dfffa773913e#egg=nwb-conversion-tools',
        'ndx-spectrum==0.2.2',
        'ndx-icephys-meta==0.1.0',
        'ibllib',
        'lazy_ops',
        'pyrsistent==0.16.0'
    ]
)