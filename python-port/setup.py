"""Setup configuration for gan-web-bluetooth Python port."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="gan-web-bluetooth",
    version="0.1.0",
    author="Python Port Contributors",
    description="Python library for GAN Smart Timers and Smart Cubes via Bluetooth",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/gan-web-bluetooth-python",
    packages=find_packages(exclude=["tests", "examples"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "bleak>=0.21.0",
        "cryptography>=41.0.0",
        "numpy>=1.24.0",
        "pyee>=11.0.0",
        "typing-extensions>=4.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "mypy>=1.5.0",
            "ruff>=0.1.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "gan-timer=gan_web_bluetooth.cli:timer_cli",
            "gan-cube=gan_web_bluetooth.cli:cube_cli",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/yourusername/gan-web-bluetooth-python/issues",
        "Source": "https://github.com/yourusername/gan-web-bluetooth-python",
    },
)