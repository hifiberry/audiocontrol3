from setuptools import setup, find_packages

setup(
    name="audiocontrol3",
    version="xxx",
    description="AudioControl3 - Audio control system",
    author="HiFiBerry",
    author_email="info@hifiberry.com",
    packages=find_packages(),
    install_requires=[
        "flask>=2.0.0",
    ],
    entry_points={
        'console_scripts': [
            'audiocontrol3-server=ac3.server:start_server',
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)