"""setup.py for cryptarchive"""

from setuptools import setup


setup(
    name="fbad",
    version="0.1.0",
    author="bennr01",
    author_email="benjamin99.vogt@web.de",
    description="build tools for docker images",
    long_description=open("README.md").read(),
    license="MIT",
    keywords="docker build tools",
    url="https://github.com/bennr01/fbad/",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python",
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        ],
    packages=[
        "fbad",
        ],
    install_requires=[
        "twisted",
        ],
    entry_points={
        "console_scripts": [
            "fbad-server=fbad.runner:server_main",
        ],
    }
)
