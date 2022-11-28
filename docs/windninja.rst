WindNinja
============

WindMapper requires a working WindNinja install and intalling WindMapper does not installs WindNinja.
Windmapper depends on the `WindNinja <https://github.com/firelab/windninja>`__ program to compute the windfields.
WindNinja may be installed separately, or it can be built and installed via Conan. These instructions will show how to do so via Conan.

.. note::

    Building WindNinja with conan will use a different gdal library than what was used for the python bindings! This is ok, just please be aware of this.

- conan >= 1.21
- cmake >= 3.16
- C++11 compiler (gcc 7.x+ recommended)

Setup conan
***********

Install conan

::

   pip install conan

If cmake is not installed system wide:

::

   pip install cmake

or install via system package manager.

Initialize a new conan profile (if required)

::

    conan profile new default --detect
    conan remote add bincrafters https://api.bintray.com/conan/bincrafters/public-conan
    conan remote add CHM https://api.bintray.com/conan/chrismarsh/CHM
    conan profile update settings.compiler.cppstd=14 default  


conan needs to be told to use new C++11 ABI. If using clang (e.g., MacOs), do
::

    conan profile update settings.compiler.libcxx=libc++ default  #with clang


and if using gcc, do
::

    conan profile update settings.compiler.libcxx=libstdc++11 default  #with gcc


If you change compilers, such as on a cluster with a modules system, you can rerun 
::
    
    conan profile new default --detect --force


to detect the new compiler settings. The ``cppstd`` and ``libcxx`` settings need to be reapplied once this is done.

and then install WindNinja from Conan

::

    mkdir /opt/windninja && cd /opt/windninja #this could be any directory you wish to install to
    conan install windninja/3.7.5@CHM/stable -g deploy


.. note::

   Currently the MacOS OpenMP build of WindNinja does not work
   https://github.com/firelab/windninja/issues/355