from setuptools import setup, find_packages

with open('./requirements.txt') as reqs:
    requirements = [line.rstrip() for line in reqs]

setup(name="STAC Updater",
      version='0.2',
      author='Jeff Albrecht',
      author_email='geospatialjeff@gmail.com',
      packages=find_packages(exclude=['package']),
      install_requires = requirements,
      entry_points= {
          "console_scripts": [
              "stac-updater=stac_updater.cli:stac_updater"
          ]},
      include_package_data=True
      )