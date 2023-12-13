Use
===


WindMapper may be run in one of two modes:

1) download a SRTM tile that corresponds to a lat/long bounding box
   defined by the user or;
2) use a user-supplied DEM

Two examples are given, one for each use case. These are available in the source tree under ``examples``.

Download
---------
The example given in ``examples/download_DEM`` can be run as

::

   wind_mapper_generic.py examples/download_DEM/param_download_DEM.py

Existing
---------
The example given in ``examples/existing_DEM`` can be run as

::

   wind_mapper_generic.py examples/download_DEM/param_existing_DEM.py

Output
-------
Once Windmapper has run, the output folder will have a set of files:

.. confval:: ref-DEM-utm.tif

    The entire domain to be run on

.. confval:: tmp_X_Y.tif

    Windmapper tiles the domain to ensure a tractable solution. Each tile will be named tmp_X_Y.tif for example tmp_0_0.

.. confval:: ref-DEM-utm-*.vrt

    A VRT file is an xml meta-file that is a collection of underlying rasters that make up a larger raster. These underlying
    rasters are in the ``tmp_dir_X_Y`` directories. The number in the vrt name, e.g., 180 in ``ref-DEM-utm_180_V.vrt`` is the direction
    the wind comes from. The U/V refer to either the U or V component speedup. And the ``_spd_up_X`` suffix, e.g., ``_spd_up_1000``, is the
    wind speed (:math:`W=sqrt(U^2+V^2)`) with the given averaging distanced as specified in the configuration (1000 m default).


Troubleshooting
-------------------

MPI slots
**********
If an error about MPI slots is raised, set the MPI_nworkers configuration parameter to a smaller number. If it hasn't been
set, set it to 1 or 2 less than the slots reported in the error. On single-core machines you will need to enable
oversubscription. This can be done for OpenMPI

::

    export OMPI_MCA_rmaps_base_oversubscribe=true; windmapper.py my-config.py

or by pernamentally enabling it

::

    echo rmaps_base_oversubscribe=true >> $HOME/.openmpi/mca-params.conf



GDAL
*****

If you recieve an error about GDAL ``_gdal_array``, like:

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


Then force the reinstall of gdal via

::

    python -m pip install --no-cache-dir --force-reinstall gdal[numpy]


This error results from gdal being install after numpy.