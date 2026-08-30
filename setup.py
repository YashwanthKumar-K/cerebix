from setuptools import setup, find_packages

setup(
    name="cerebix",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "cerebix=cerebix.main:main",
        ],
    },
    install_requires=[
        "requests",
        "rich",
        "colorama"
    ],
)
