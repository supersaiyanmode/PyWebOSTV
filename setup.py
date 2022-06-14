try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


setup(
    name='pywebostv',
    version='0.8.8',
    url='https://github.com/supersaiyanmode/PyWebOSTV',
    author='Srivatsan Iyer',
    author_email='supersaiyanmode.rox@gmail.com',
    packages=[
        'pywebostv',
    ],
    license='MIT',
    description='Library to remote control LG Web OS TV',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    install_requires=[
        "ws4py",
        "requests[security]",
        "future",
    ],
)
