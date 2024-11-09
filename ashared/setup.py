from setuptools import setup, find_packages

setup(
    name='monster-shared',
    version='0.1',
    packages=find_packages(),
    description='LLMonster shared logic',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='scottp',
    author_email='scottp@supercog.ai',
)
