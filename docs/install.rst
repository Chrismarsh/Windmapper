Install
=========
.. note::

    Windmapper is only supported on Linux and MacOS. Python >= 3.6

WindMapper requires WindNinja to be installed to work and installing WindMapper does not installed WindNinja.
This can automatically be done with setting ``BUILD_WINDNINJA=TRUE`` before installing with pip. Otherwise, please see
`windninja`_ for details on building WindNinja.


Dependencies
---------------
GDAL >= 3.5 with netcdf, curl
Boost >= 1.41.0 with date_time, program_options, test

Linux
******
On linux, depending on the distro used, you may need to also install the gdal binaries. On Ubuntu this is
::

      sudo apt-get update
      sudo apt-get install libgdal-dev
      sudo apt-get install gdal-bin
      sudo apt-get install libboost-all-dev

MacOS
******
On MacOS, homebrew should be used to install gdal. Macport based installs likely work, but have not been tested.

On MacOS, the gdal binaries should be installed from homebrew

::

   brew install gdal boost


Setup Python environment
-------------------------
It is recommended that Windmapper be installed into a Python3 virtual environment. For example:

::

    python -m venv /path/to/new/virtual/environment


The following python requirements will be installed by ``pip``:

::

    'pygdal','numpy','scipy','elevation','pyproj','tqdm','rasterio'


Install Windmapper
--------------------
Activate the venv (if used), and then build and install windmapper.

::

    pip install windmapper

To not automatically build WindMapper,

::

    BUILD_WINDNINJA=FALSE pip install windmapper