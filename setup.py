#!/bin/env python3

import os
from setuptools import setup


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


setup(
    name="kill hogs",
    version="0.1",
    author="Egon Rijpkema",
    author_email="e.m.a.rijpkema@rug.nl",
    description=(
        "A script that kills processes of users generating excessive load."
        "It is meant with HPC login nodes in mind."),
    license="GPLv3",
    keywords="HPC tools load memory kill",
    url="http://packages.python.org/kill_hogs",
    packages=['kill_hogs', 'unittests'],
    python_requires='>=3.6',
    data_files=[('{}/.kill_hogs/'.format(os.environ['HOME']),
                 ['kill_hogs/kill_hogs.yml'])],
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Topic :: Utilities",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
    entry_points={
        'console_scripts': [
            'kill-hogs=kill_hogs.kill_hogs:main',
            'request-enforcement=kill_hogs.kill_hogs:request_enforcement'
        ],
    })
