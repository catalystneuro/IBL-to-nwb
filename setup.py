"""Setup and package the ibl-to-nwb project."""
from pathlib import Path

from setuptools import setup

root = Path(__file__).parent


with open(root / "README.md") as file:
    long_description = file.read()

with open(root / "requirements.txt") as f:
    install_requires = f.readlines()

with open(root / "ibl_to_nwb" / "updated_conversion" / "requirements.txt") as f:
    brainwide_map_requires = f.readlines()

extras_require = dict(brainwide_map=brainwide_map_requires)

setup(
    name="ibl_to_nwb",
    version="0.2.0",
    description="Tools to convert IBL data to NWB format.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Cody Baker and Ben Dichter",
    author_email="ben.dichter@catalystneuro.com",
    url="https://github.com/catalystneuro/IBL-to-nwb",
    keywords=["nwb", "ibl"],
    package_data={},
    include_package_data=False,
    install_requires=install_requires,
    extras_require=extras_require,
    python_requires=">=3.8",
)
