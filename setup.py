from setuptools import setup, find_packages

setup(
    name         = 'openevmap',
    version      = '1.0',
    packages     = find_packages(),
    entry_points = {'scrapy': ['settings = scrapers.settings']},
    include_package_data = True
)
