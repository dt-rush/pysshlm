"""A setuptools-based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath (path.dirname (__file__))

# Get the long description from the README file
with open (path.join (here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()
    
# Get the requirements from requirements.txt
with open (path.join (here, 'requirements.txt')) as f:
    requirements = f.read().splitlines()
if requirements is None:
    print "/!\\ failed to read requirements.txt, could not run setup.py!!!"
    sys.exit (-1)

setup(
    name='pysshlm',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version='1.0.0',

    description='Wrap an SSH session with hotkey to pop into/out of line-editing mode',
    long_description=long_description,

    # The project's main homepage.
    url='https://github.com/dt-rush/pysshlm',

    # Author details
    author='dt-rush',
    author_email='nick.8.payne@gmail.com',

    # Choose your license
    license='LICENSE.txt',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Utilities',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 2.7'
    ],

    # What does your project relate to?
    keywords='ssh line-editing high-latency tools',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    include_package_data=True,

    # Alternatively, if you want to distribute just a my_module.py, uncomment
    # this:
    #   py_modules=["my_module"],

    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=requirements,

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'pysshlm = pysshlm.__main__:main'
        ],
    },
)
