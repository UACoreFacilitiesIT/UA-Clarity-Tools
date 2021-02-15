import os
from setuptools import setup, find_packages


def readme(filename):
    full_path = os.path.join(os.path.dirname(__file__), filename)
    with open(full_path, 'r') as file:
        return file.read()


setup(
    name="ua_clarity_tools",
    version="1.1.4",
    packages=find_packages(),
    author="Stephen Stern, Rafael Lopez, Ryan Johannes-Bland",
    author_email="sterns1@email.arizona.edu",
    include_package_data=True,
    long_description=readme("README.md"),
    long_description_content_type='text/markdown',
    url="https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools",
    license="MIT",
    description=(
        "API that interacts with Illumina's Clarity LIMS software at a higher"
        " level than requests."),
    install_requires=[
        "requests",
        "bs4",
        "lxml",
        "jinja2",
        "ua-clarity-api",
        "nose",
        "dataclasses",
    ],
)
