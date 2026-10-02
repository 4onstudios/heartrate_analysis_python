import setuptools

with open("README.md", "r", encoding = "utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="heartpy",
    version="1.2.9",
    author="Paul van Gent",
    author_email="P.vanGent@tudelft.nl",
    description="Heart Rate Analysis Toolkit",
    license="MIT",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/paulvangentcom/heartrate_analysis_python",
    packages=setuptools.find_packages(include=["heartpy", "heartpy.*"]),
    python_requires=">=3.10",
    install_requires=[
        "numpy>=1.23,<3",
        "scipy>=1.9,<2",
        "matplotlib>=3.6,<4",
    ],
    extras_require={
        "backend": ["fastapi>=0.115,<1", "pydantic>=2.9,<3", "uvicorn>=0.30,<1"],
        "dev": ["pytest>=8,<10", "httpx>=0.27,<1", "build>=1,<2"],
    },
    entry_points={
        "console_scripts": ["heartpy-backend=heartpy.backend.__main__:main"],
    },
    include_package_data=True,
    package_data={
        '': ['data/*.csv', 'data/*.mat', 'data/*.log']       
    },
    classifiers=[
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
    ],
)
