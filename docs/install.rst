Install
=========
.. note::

    Windmapper is only supported on Linux and MacOS. Python >= 3.6

WindMapper requires WindNinja to be installed to work and installing WindMapper does not installed WindNinja.
This can automatically be done with setting ``BUILD_WINDNINJA=TRUE`` before installing with pip. Otherwise, please see
`Build`_ for details on building WindNinja.


Install gdal
---------------
Ensure gdal libraries are installed.

Linux
******
On linux, depending on the distro used, you may need to also install the gdal binaries. On Ubuntu this is
::

   sudo apt-get install libgdal-dev
   sudo apt-get install gdal-bin
   sudo apt-get install python-gdal

MacOS
******
On MacOS, homebrew should be used to install gdal. Macport based installs likely work, but have not been tested.

On MacOS, the gdal binaries should be installed from homebrew

::

   brew install gdal


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
Activate the venv (if used), and then install windmapper.

::

    pip install windmapper

or to automatically build WindMapper,

::

    BUILD_WINDNINJA=TRUE pip install windmapper