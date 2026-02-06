Install
=========
.. note::

    Windmapper is only supported on Linux and MacOS. Python >= 3.6

WindMapper requires WindNinja to be installed to work and installing WindMapper will automatically build WindNinja by default.


Spack
------
Installing with Spack is the easiest way of handling the (compled) Dependencies


Install spack
+++++++++++++++
Install `spack <https://spack-tutorial.readthedocs.io/en/latest/tutorial_basics.html>`__

Use the git repository and use the develop branch, as significant bug fixes to packages CHM uses have been made in
this branch.

Configure Spack
+++++++++++++++++++
It is critical to ensure spack is correctly
configured, as described in the `Spack Getting Started <https://spack.readthedocs.io/en/latest/getting_started.html>`__
guide.

If you need to build a compiler via spack to use and the spack libraries, this is the time to do it.
Otherwise, ensure
the `external compiler is found by
spack <https://spack.readthedocs.io/en/latest/getting_started.html#spack-compiler-find>`__ and correctly configured.

If you use a system MPI or intel-oneapi-(mkl|tbb) (i.e., a not-spack built version), this is when it should be configured
`as a spack external <https://spack.readthedocs.io/en/latest/packages_yaml.html#external-packages>`__ package.

Install windmapper
+++++++++++++++++++++++++

::

  spack repo add https://github.com/Chrismarsh/spack-repo.git
  spack install py-windmapper




Hard way
=========
This is also barely tested anymore so YMMV

Dependencies
---------------
GDAL >= 3.5 with netcdf, curl
Boost >= 1.41.0 with date_time, program_options, test
An MPI compatible with mpi4py

Linux
******
On Ubuntu this  can be done like
::

      sudo apt-get update
      sudo apt-get install libgdal-dev
      sudo apt-get install gdal-bin
      sudo apt-get install libboost-all-dev
      sudo apt-get install python3-gdal
      sudo apt-get install openmpi-bin libopenmpi-dev



MacOS
******
On MacOS, homebrew should be used to install gdal. Macport based installs likely work, but have not been tested.

On MacOS, the gdal binaries should be installed from homebrew

::

    brew install gdal
    brew install boost
    brew install open-mpi


Setup Python environment
-------------------------
It is recommended that Windmapper be installed into a Python3 virtual environment. For example:

::

    python -m venv /path/to/new/virtual/environment



Install Windmapper
--------------------
Activate the venv (if used), and then build and install windmapper.

::

    pip install windmapper


To not automatically build WindMapper,

::

    BUILD_WINDNINJA=FALSE pip install windmapper


Troublshooting
--------------------
If you get an error about ``_gdal_array``

::

 Traceback (most recent call last):
  File "/Users/runner/hostedtoolcache/Python/3.8.18/x64/lib/python3.8/site-packages/windmapper_utls/MPI_call_WN_1dir.py", line 190, in <module>
    main(*sys.argv[1:])
  File "/Users/runner/hostedtoolcache/Python/3.8.18/x64/lib/python3.8/site-packages/windmapper_utls/MPI_call_WN_1dir.py", line 178, in main
    call_WN_1dir(WINDNINJA_DATA, gdal_prefix, user_output_dir, fic_config_WN, list_tif_2_vrt, nopt_x, nopt_y, nx,
  File "/Users/runner/hostedtoolcache/Python/3.8.18/x64/lib/python3.8/site-packages/windmapper_utls/MPI_call_WN_1dir.py", line 105, in call_WN_1dir
    ang = gtif.GetRasterBand(1).ReadAsArray()
  File "/Users/runner/hostedtoolcache/Python/3.8.18/x64/lib/python3.8/site-packages/osgeo/gdal.py", line 5278, in ReadAsArray
    from osgeo import gdal_array
  File "/Users/runner/hostedtoolcache/Python/3.8.18/x64/lib/python3.8/site-packages/osgeo/gdal_array.py", line 10, in <module>
    from . import _gdal_array
  ImportError: cannot import name '_gdal_array' from 'osgeo' (/Users/runner/hostedtoolcache/Python/3.8.18/x64/lib/python3.8/site-packages/osgeo/__init__.py)


Then reinstall gdal with numpy

::

    python -m pip install --no-cache-dir --force-reinstall gdal[numpy]




