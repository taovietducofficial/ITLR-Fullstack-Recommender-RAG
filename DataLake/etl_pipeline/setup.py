from setuptools import find_packages, setup

setup(
    name="etl_pipeline",
    author="Tào Việt Đức",
    author_email="taovietduc.work@gmail.com",
    packages=find_packages(exclude=["etl_pipeline_tests"]),
    install_requires=[
        "dagster",
        "dagster-cloud"
    ],
    extras_require={"dev": ["dagit", "pytest"]},
)
