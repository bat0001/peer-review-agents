"""Setup for GPT2 training framework."""

from setuptools import find_packages, setup

setup(
    name="gpt2-mod",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.9.0",
        "numpy",
        "triton",
        "rustbpe",
        "tiktoken",
        "pyarrow",
        "requests",
        "filelock",
        "hydra-core>=1.3.2",
        "omegaconf>=2.3.0",
        "PyYAML",
        "tqdm",
        "wandb",
        "jinja2",
    ],
) 
