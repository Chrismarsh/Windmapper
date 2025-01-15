# Windmapper

Windmapper is a python tool and a set of algorithms for producing and using pre-computed libraries of wind field used for wind downscaling. 

![](docs/images/WM-main.png)

# Installation

The default ``pip install windmapper`` will build windmapper without Windninja. However Windninja is required to run.

To build Windninja, ensure gdal, boost, and mpi system libraries are installed and then

``BUILD_WINDNINJA=1 pip install windmapper``

Spack can also be used to install windmapper -- please see documentation below.

# Documentation 
Documentation and full instructions on use can be found [here](https://windmapper.readthedocs.io)

# Implimentation

The directory `implementation/` contains a jupyter notebook with an example implimentation of the code. It is not 
vectorized to aid in readability. However, this makes it very very slow!