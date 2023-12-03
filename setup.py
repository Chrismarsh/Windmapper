import os
import subprocess
from setuptools import find_packages
import packaging.version

# replace disutils as it is deprecated
#https://github.com/drgarcia1986/simple-settings/pull/281/commits/41a0584d693a17400a1922821533260750be40fa
_MAP = {
    'y': True,
    'yes': True,
    't': True,
    'true': True,
    'on': True,
    '1': True,
    'n': False,
    'no': False,
    'f': False,
    'false': False,
    'off': False,
    '0': False
}
def strtobool(value):
    try:
        return _MAP[str(value).lower()]
    except KeyError:
        raise ValueError('"{}" is not a valid bool value'.format(value))

build_wn = True
try:
    build_wn = strtobool(os.environ['BUILD_WINDNINJA'])
except:
    build_wn = True

print(f'Build WindNinja? {build_wn}')

def get_installed_gdal_version():
    try:
        version = subprocess.run(["gdal-config", "--version"], stdout=subprocess.PIPE).stdout.decode()

        version = version.replace('\n', '')
        version = "=="+version+".*"
        return version
    except FileNotFoundError as e:
        raise(""" ERROR: Could not find the system install of GDAL. 
                  Please install it via your package manage of choice.
                """)


setup_requires = []

if build_wn:
    from skbuild import setup
    from skbuild.exceptions import SKBuildError
    from skbuild.cmaker import get_cmake_version

    try:
        # Add CMake as a build requirement if cmake is not installed or is too low a version
        # https://scikit-build.readthedocs.io/en/latest/usage.html#adding-cmake-as-building-requirement-only-if-not-installed-or-too-low-a-version
        if packaging.version.parse(get_cmake_version()) < packaging.version.parse("3.16"):
            setup_requires.append('cmake')
    except SKBuildError:
        setup_requires.append('cmake')

else:
    from setuptools import setup

args =   {'name': 'windmapper',
            'version': '2.1.3',
            'description': 'Windfield library generation',
            'long_description': "Generates windfields",
            'author': 'Chris Marsh',
            'author_email': 'chris.marsh@usask.ca',
            'url': "https://github.com/Chrismarsh/Windmapper",
            'include_package_data': True,
            'packages': find_packages(where="pysrc"),
            'package_dir': {
            '': 'pysrc',
            },
            'scripts': ["windmapper.py", 'scripts/rio_merge.py', "cfg/cli_massSolver.cfg"],
            'install_requires': ['gdal[numpy]' + get_installed_gdal_version()+',>=3.5.0', # >= 3.5 required for this type of gdal python binding install
                                 'numpy', 'scipy', 'elevation', 'pyproj', 'tqdm', 'rasterio', 'mpi4py'],
            'setup_requires': setup_requires,
            'python_requires': '>=3.6'}

if build_wn:
    args['cmake_args'] = ['-DCMAKE_BUILD_TYPE=Release']

setup(**args)
