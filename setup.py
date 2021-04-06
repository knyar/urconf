from setuptools import setup, find_packages

setup(
    name="urconf",
    version="2021.1",
    url="http://github.com/knyar/urconf",
    license="MIT",
    author="Anton Tolchanov",
    description="Declarative configuration library for Uptime Robot",
    long_description=open("README.rst", "r").read(),
    packages=find_packages(),
    platforms="any",
    install_requires=["requests", "typedecorator"],
    keywords=["monitoring", "api", "uptime robot"],
)
