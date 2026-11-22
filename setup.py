from setuptools import setup

setup(
    name="orchestration-engine",
    version="1.0.0",
    description="Lightweight asynchronous multi-agent orchestration engine with DAG pipelines and consensus",
    author="Roman Pokushko",
    author_email="pokusko.roman@gmail.com",
    url="https://github.com/pokushko/orchestration-engine",
    py_modules=["orchestrator"],
    python_requires=">=3.10",
    extras_require={
        "dev": ["pytest>=7.0.0"],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
