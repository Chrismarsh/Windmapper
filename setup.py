import os
import subprocess
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

build_wn = False
try:
    build_wn = strtobool(os.environ['BUILD_WINDNINJA'])
except:
    build_wn = False

print(f'Build WindNinja? {build_wn}')

def get_installed_gdal_version():
    try:
        version = subprocess.run(["gdal-config", "--version"], stdout=subprocess.PIPE).stdout.decode()

        version = version.replace('\n', '')
        #pygdal don'ts always have the most up todate version so we will need to swtich to pygdal-chm if it is not available
        # 3.3.2 is most recent as of this version
        chm=''
        if packaging.version.parse(version) > packaging.version.parse("3.5.1"):
            chm='-chm'

        version = chm + "=="+version+".*"
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
          'version': '1.3.1',
          'description': 'Windfield library generation',
          'long_description': "Generates windfields",
          'author': 'Chris Marsh',
          'author_email': 'chris.marsh@usask.ca',
          'url': "https://github.com/Chrismarsh/Windmapper",
          'include_package_data': True,
          'cmake_args': ['-DCMAKE_BUILD_TYPE=Release'],
          'scripts': ["windmapper.py", 'scripts/rio_merge.py', "cfg/cli_massSolver.cfg"],
          'install_requires': ['pygdal' + get_installed_gdal_version(),
                               'numpy', 'scipy', 'elevation', 'pyproj', 'tqdm', 'rasterio'],
          'setup_requires': setup_requires,
          'python_requires': '>=3.6'}

if build_wn:
    args['cmake_args'] = ['-DCMAKE_BUILD_TYPE=Release']

setup(**args)
