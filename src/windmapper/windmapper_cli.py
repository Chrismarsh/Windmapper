#!/usr/bin/env python

# Wind Mapper
# Copyright (C) 2017 Christopher Marsh and Vincent Vionnet

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import math

import elevation
import pdb, os, shutil
import subprocess
from osgeo import gdal, ogr, osr
from pyproj import Proj, transform, Transformer
import numpy as np
import sys
import importlib
import itertools
from tqdm import tqdm
import cloudpickle
from mpi4py import MPI
from . import windmapper_utls as wm
from .dem import prepare_existing_dem, tile_window



gdal.UseExceptions()  # Enable exception support
ogr.UseExceptions()  # Enable exception support
osr.UseExceptions()  # Enable exception support


def main():
    #######  load user configurable paramters here    #######
    # Check user defined configuration file

    if len(sys.argv) == 1:
        print(
            'ERROR: windmapper.py requires one argument [configuration file] (i.e. windmapper.py '
            'param_existing_DEM.py)')
        exit(-1)

    # Get name of configuration file/module
    configfile = sys.argv[-1]

    # Load in configuration file as module
    X = importlib.machinery.SourceFileLoader('config', configfile)
    X = X.load_module()

    # Resolution of WindNinja simulations (in m)
    res_wind = X.res_wind

    # path to Wind Ninja executable

    # Priority: explicit configuration, environment, then PATH.
    requested = (
        getattr(X, "wn_exe", None)
        or os.environ.get("WINDNINJA_EXE")
        or "WindNinja_cli"
    )

    wn_exe = shutil.which(os.path.expanduser(os.fspath(requested)))

    if wn_exe is None:
        raise FileNotFoundError(
            f"WindNinja executable not found or not executable: {requested!r}. "
            "Set wn_exe in the configuration, set WINDNINJA_EXE, "
            "or put WindNinja_cli on PATH."
        )

    # Resolve Spack view symlinks before deriving the data directory.
    wn_exe = os.path.realpath(wn_exe)

    MPI_exec_str = None
    if hasattr(X, 'MPI_exec_str'):
        MPI_exec_str = X.MPI_exec_str

    # on macos M1, the 2 efficiency cores don't seem to be targetable by OpenMPI?
    # Setup file containing WN configuration
    MPI_nworkers = os.cpu_count() or 1

    # on linux we can ensure that we respect cpu affinity, more reliable than cpu_count()
    if 'sched_getaffinity' in dir(os):
        MPI_nworkers = len(os.sched_getaffinity(0))

    if hasattr(X, 'MPI_nworkers'):
        MPI_nworkers = X.MPI_nworkers
    elif not hasattr(X, 'MPI_nworkers') and MPI_exec_str:
        raise RuntimeError('If MPI_exec_str is provided, then MPI_nworkers must also be provided')

    print(f'Using {MPI_nworkers} MPI workers')

    num_threads = 1
    if hasattr(X, 'num_threads'):
        num_threads = X.num_threads

    print(f'Using {num_threads} threads for Windninja')

    # This is used later in the MPI subprocess call
    WINDNINJA_DATA = os.path.join(os.path.dirname(wn_exe), '..', 'share', 'windninja')

    # Parameter for atmospheric stability in Wind Ninja mass conserving (default value)
    alpha = 1

    # Number of wind speed categories (every 360/ncat degrees)
    ncat = 4
    if hasattr(X, 'ncat'):
        ncat = X.ncat

    if ncat < 1:
        print('ERROR ncat must be > 0 ')
        exit(-1)

    use_existing_dem = True

    lat_min = -9999
    lon_min = -9999
    lat_max = -9999
    lon_max = -9999
    if hasattr(X, 'use_existing_dem'):
        use_existing_dem = X.use_existing_dem
    if use_existing_dem:
        dem_filename = X.dem_filename
    else:
        lat_min = X.lat_min
        lat_max = X.lat_max
        lon_min = X.lon_min
        lon_max = X.lon_max

        if lat_min == -9999 or lon_min == -9999 or lat_max == -9999 or lon_max == -9999:
            print('Coordinates of the bounding box must be specified to download SRTM DEM.')
            exit(-1)


    skip_mercator_proj = False
    if hasattr(X, "skip_mercator_proj"):
        skip_mercator_proj = X.skip_mercator_proj

    # Method to compute average wind speed used to derive transfert function
    wind_average = 'grid'
    targ_res = 1000
    if hasattr(X, 'wind_average'):
        wind_average = X.wind_average
        if wind_average == 'grid':
            targ_res = X.targ_res

    list_options_average = ['mean_tile', 'grid']
    if wind_average not in list_options_average:
        print('wind average must be "mean_tile" or "grid"')

        exit(-1)

    if targ_res < 0:
        print('Target resolution must be>0')
        exit(-1)

    # output to the specific directory, instead of the root dir of the calling python script
    user_output_dir = os.getcwd() + '/' + configfile[:-3] + '/'  # use the config filename as output path

    if hasattr(X, 'user_output_dir'):
        user_output_dir = X.user_output_dir
        if user_output_dir[-1] is not os.path.sep:
            user_output_dir += os.path.sep

    # Delete previous dir (if exists)
    if os.path.isdir(user_output_dir):
        shutil.rmtree(user_output_dir, ignore_errors=True)

    # make new output dir
    os.makedirs(user_output_dir)



    # ensure correct formatting on the output
    fic_config = F"""num_threads = {num_threads}  
initialization_method = domainAverageInitialization 
units_mesh_resolution = m 
input_speed = 10.0 
input_speed_units = mps 
input_wind_height = 40.0 
units_input_wind_height = m 
output_wind_height = 40.0 
units_output_wind_height = m 
output_speed_units = mps 
vegetation = grass 
diurnal_winds = false 
write_goog_output = false 
write_shapefile_output = false 
write_ascii_output = true 
write_farsite_atm = false """

    if hasattr(X, 'fic_config_WN'):
        fic_config_WN = X.fic_config_WN

        if not os.path.exists(fic_config_WN):
            print('ERROR: Invalid path for cli_massSolver.cfg given in `fic_config_WN` config options.')
            exit(-1)
    else:
        fic_config_WN = os.path.join(user_output_dir, 'default_cli_massSolver.cfg')
        with open(fic_config_WN, 'w') as fic_file:
            fic_file.write(fic_config)

    os.mkdir(os.path.join(user_output_dir, 'shp'))

    # we need to make sure we pickup the right paths to all the gdal scripts
    gdal_prefix = ''
    try:
        gdal_prefix = subprocess.run(["gdal-config", "--prefix"], stdout=subprocess.PIPE).stdout.decode()
        gdal_prefix = gdal_prefix.replace('\n', '')
        gdal_prefix += '/bin/'
    except:
        raise Exception(""" ERROR: Could not find gdal-config, please ensure it is installed and on $PATH """)

    # Wind direction increment
    delta_wind = 360. / ncat

    # List of variable to transform from asc into tif
    var_transform = ['ang', 'vel']
    if wind_average == 'grid':
        list_tif_2_vrt = ['U', 'V', 'spd_up_' + str(targ_res)]
    elif wind_average == 'mean_tile':
        list_tif_2_vrt = ['U', 'V', 'spd_up_tile']

    # Optimal size for wind ninja
    nres = 600

    # Additional grid point to ensure correct tile overlap
    nadd = 25

    # Define DEM file to use for WN
    fic_download = user_output_dir + 'ref-DEM.tif'

    name_utm = 'ref-DEM-proj'
    fic_lcc = user_output_dir + '/' + name_utm + '.tif'

    if use_existing_dem:
        ds = prepare_existing_dem(dem_filename, fic_lcc, skip_mercator_proj,
                                  getattr(X, 'dem_anchor_lonlat', None))
        gt = ds.GetGeoTransform()
        xmin, ymax = gt[0], gt[3]
        xmax = xmin + ds.RasterXSize * gt[1]
        ymin = ymax + ds.RasterYSize * gt[5]
        bbox = [[ymax, xmin], [ymax, xmax], [ymin, xmax], [ymin, xmin]]
        bbox_srs = ds.GetProjection()
    else:

        # need to ensure that we request a square domain in LCC projection
        fac = 0.1  # Expansion factor to make sure that the downloaded SRTM tile is large enough

        # Properties of the bounding box
        delta_lat = lat_max - lat_min
        delta_lon = lon_max - lon_min

        # This is a larger extent than what we will use so we ensure perfect coverage
        lon_min_expanded = lon_min - delta_lon * fac
        lat_min_expanded = lat_min - delta_lat * fac
        lon_max_expanded = lon_max + delta_lon * fac
        lat_max_expanded = lat_max + delta_lat * fac

        LCC_proj = '+proj=merc +lat_ts=%.30f' % ((lat_min_expanded + lat_max_expanded) / 2.0)

        t_4326_to_lcc = Transformer.from_crs("epsg:4326", LCC_proj)

        lon_lcc, lat_lcc = t_4326_to_lcc.transform(
            [lat_min_expanded, lat_min_expanded, lat_max_expanded, lat_max_expanded],
            [lon_min_expanded, lon_max_expanded, lon_min_expanded, lon_max_expanded],
        )

        lon_lcc_square = [min(lon_lcc), min(lon_lcc), max(lon_lcc), max(lon_lcc)]
        lat_lcc_square = [min(lat_lcc), max(lat_lcc), min(lat_lcc), max(lat_lcc)]

        t_merc_to_4326 = Transformer.from_crs(LCC_proj, "epsg:4326", )
        new_4326_square_lat, new_4326_square_lon = t_merc_to_4326.transform(lon_lcc_square, lat_lcc_square)

        lat_max_expanded = max(new_4326_square_lat)
        lat_min_expanded = min(new_4326_square_lat)
        lon_max_expanded = max(new_4326_square_lon)
        lon_min_expanded = min(new_4326_square_lon)

        # Download reference SRTM data
        elevation.clip(bounds=(lon_min_expanded, lat_min_expanded, lon_max_expanded, lat_max_expanded), output=fic_download)

        # Extract a rectangular region of interest in utm at 30 m
        # exec_str = '%sgdalwarp %s %s -overwrite -dstnodata -9999 -t_srs "%s" -te_srs "epsg:4326" -te %.30f %.30f %.30f %.30f  -tr %.30f ' \
        #            '%.30f -r bilinear '
        # com_string = exec_str % (gdal_prefix, fic_download, fic_lcc+'.tmp.tif', LCC_proj,
        #                          X.lon_min, X.lat_min, X.lon_max, X.lat_max, 30, 30)
        # subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        # # Extract a rectangular region of interest in utm at 30 m
        # exec_str = '%sgdalwarp %s %s -overwrite -dstnodata -9999 -t_srs "%s" -te %.30f %.30f %.30f %.30f  -tr %.30f ' \
        #            '%.30f -r bilinear '
        # com_string = exec_str % (gdal_prefix, fic_download, fic_lcc+'.tmp.tif', LCC_proj,
        #                          min(lon_lcc), min(lat_lcc), max(lon_lcc), max(lat_lcc), 30, 30)
        # subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        exec_str = '%sgdalwarp %s %s -overwrite -dstnodata -9999 -t_srs "%s"  -tr %.30f ' \
                   '%.30f -r bilinear '
        com_string = exec_str % (gdal_prefix, fic_download, fic_lcc+'.tmp.tif', LCC_proj,
                                 30, 30)
        subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        exec_str = '%sgdal_translate -ot Float32  %s %s' % (gdal_prefix, fic_lcc+'.tmp.tif', fic_lcc)
        subprocess.check_call([exec_str], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        os.remove(fic_lcc+'.tmp.tif')

        ds = gdal.Open(fic_lcc)
        gt = ds.GetGeoTransform()
        bbox = [[lat_max, lon_min], [lat_max, lon_max],
                [lat_min, lon_max], [lat_min, lon_min]]
        bbox_srs = 'EPSG:4326'
        t_4326_to_merc = Transformer.from_crs(bbox_srs, LCC_proj, always_xy=True)
        x_merc, y_merc = t_4326_to_merc.transform(
            [point[1] for point in bbox], [point[0] for point in bbox])
        xmin, xmax = min(x_merc), max(x_merc)
        ymin, ymax = min(y_merc), max(y_merc)

    cutline = os.path.join(user_output_dir, 'shp', 'user_bbox.shp')
    pts_to_shp(bbox, cutline, bbox_srs)
    pixel_width, pixel_height = gt[1], -gt[5]

    lenx = xmax-xmin
    leny = ymax-ymin

    len_wn = res_wind * nres

    # Number of Wind Ninja tiles
    if use_existing_dem:
        # Balanced integer pixel windows, including exact multiples of the target size.
        nopt_x = min(ds.RasterXSize, max(1, math.ceil(ds.RasterXSize * pixel_width / len_wn)))
        nopt_y = min(ds.RasterYSize, max(1, math.ceil(ds.RasterYSize * pixel_height / len_wn)))
    else:
        nopt_x = int(lenx // len_wn + 1)
        nopt_y = int(leny // len_wn + 1)

    nx = lenx/pixel_width / nopt_x
    ny = leny/pixel_height / nopt_y

    if nopt_x == 1 and nopt_y == 1:
        # DEM is small enough for WN
        name_tmp = 'tmp_0_0'
        fic_tmp = user_output_dir + name_tmp + ".tif"
        gdal.Translate(fic_tmp, ds)

    elif use_existing_dem:
        for i, j in itertools.product(range(nopt_x), range(nopt_y)):
            window = tile_window(ds.RasterXSize, ds.RasterYSize, i, j, nopt_x, nopt_y, nadd)
            gdal.Translate(os.path.join(user_output_dir, f'tmp_{i}_{j}.tif'), ds, srcWin=window)
            x, y, w, h = window
            west, north = gdal.ApplyGeoTransform(gt, x, y)
            east, south = gdal.ApplyGeoTransform(gt, x + w, y + h)
            pts_to_shp([[north, west], [north, east], [south, east], [south, west]],
                       os.path.join(user_output_dir, 'shp', f'utm_{i}_{j}.shp'), bbox_srs)

    else:

        # Split the DEM into smaller DEM for Wind Ninja
        for i in range(0, nopt_x):
            for j in range(0, nopt_y):

                xbeg = xmin + i * nx * pixel_width - nadd * pixel_width
                ybeg = ymin + j * ny * pixel_height - nadd * pixel_height

                delx = nx * pixel_width + 2 * nadd * pixel_width
                dely = ny * pixel_height + 2 * nadd * pixel_height

                if i == 0.:
                    xbeg = xmin
                if i == 0. or i == (nopt_x - 1):
                    delx = nx * pixel_width + nadd * pixel_width

                if j == 0.:
                    ybeg = ymin
                if j == 0. or j == (nopt_y - 1):
                    dely = ny * pixel_height + nadd * pixel_height

                # get UTM zone
                chunk_x_mid = (xbeg + delx/2.)
                chunk_y_mid = (ybeg + dely/2.)

                # this is actually the custom mercator proj
                t_merc_to_4326 = Transformer.from_crs(LCC_proj, "epsg:4326", always_xy=True)
                lon_mid, lat_mid = t_merc_to_4326.transform(chunk_x_mid, chunk_y_mid)

                nepsg_utm = int(32700 - round((45 + lat_mid) / 90, 0) * 100 + round((183 + lon_mid) / 6, 0))

                t_merc_to_utm = Transformer.from_crs(LCC_proj, f"epsg:{nepsg_utm}", always_xy=True)

                utm_x, utm_y = t_merc_to_utm.transform(
                    [xbeg, xbeg + delx, xbeg, xbeg + delx],
                    [ybeg, ybeg       , ybeg + dely, ybeg + dely]
                )

                srs_out = osr.SpatialReference()
                srs_out.ImportFromEPSG(nepsg_utm)


                pts_to_shp([[max(utm_y), min(utm_x)],
                            [max(utm_y), max(utm_x)],
                            [min(utm_y), max(utm_x)],
                            [min(utm_y), min(utm_x)]],
                           os.path.join(user_output_dir,'shp',f'utm_{i}_{j}.shp'),
                           srs_out.ExportToProj4(),
                           )

                name_tmp = 'tmp_' + str(i) + "_" + str(j)
                fic_tmp = user_output_dir + name_tmp + ".tif"

                srs_out = osr.SpatialReference()
                srs_out.ImportFromEPSG(nepsg_utm)

                exec_str = '%sgdalwarp -overwrite -te %f %f %f %f -tr 30 30 -r "cubicspline" -et 0 -cutline %s -crop_to_cutline -dstnodata -9999 -t_srs "%s" %s %s'

                com_string = exec_str % (gdal_prefix,
                                         min(utm_x), min(utm_y),  max(utm_x), max(utm_y),
                                         os.path.join(user_output_dir,'shp',f'utm_{i}_{j}.shp'),
                                         srs_out.ExportToProj4(),
                                         fic_lcc,
                                         fic_tmp+'.tmp.tif')
                subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

                # absolutely make sure there are no missing data. From the cut above can sometimes be missing 1px along the edge
                exec_str = '%sgdal_fillnodata.py %s %s'
                com_string = exec_str % (gdal_prefix, fic_tmp+'.tmp.tif', fic_tmp)
                subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

                os.remove(fic_tmp+'.tmp.tif')
                print(fic_tmp)


    # Build WindNinja winds maps
    x_y_wdir = itertools.product(range(0, nopt_x),
                                 range(0, nopt_y),
                                 np.arange(0, 360., delta_wind))
    x_y_wdir = [p for p in x_y_wdir]

    for d in x_y_wdir:
        i, j, k = d
        dir_tmp = user_output_dir + 'tmp_dir' + "_" + str(i) + "_" + str(j)
        if not os.path.isdir(dir_tmp):
            os.makedirs(dir_tmp)

    x_y_wdir_split = np.array_split(x_y_wdir, MPI_nworkers)

    print(f'Running WindNinja on {len(x_y_wdir)} combinations of direction and sub-area. Please be patient...')

    for rank in range(MPI_nworkers):
        rank_args = [WINDNINJA_DATA, MPI_nworkers, gdal_prefix, user_output_dir, fic_config_WN,
            list_tif_2_vrt, nopt_x, nopt_y, nx, ny,
            pixel_height, pixel_width, res_wind, targ_res, var_transform, wind_average,
            wn_exe, xmin, ymin, x_y_wdir_split[rank]]

        with open(f'pickled_param_args_{rank}.pickle', 'wb') as f:
            cloudpickle.dump(rank_args, f)

    MPI_runWM_path = os.path.join(os.path.join(os.path.dirname(wm.__file__),
                                                        'MPI_call_WN_1dir.py'))

    if MPI_exec_str is not None:
        exec_str = f"""{MPI_exec_str} {MPI_runWM_path} pickled_param_args_RANK.pickle False"""
        print(exec_str)
        subprocess.check_call([exec_str], shell=True, cwd=os.getcwd())
    else:
        comm = MPI.COMM_SELF.Spawn(sys.executable,
                                   args=[MPI_runWM_path,
                                         'pickled_param_args_RANK.pickle', 'True'],
                                   maxprocs=MPI_nworkers)
        comm.Disconnect()


    for d in itertools.product(range(0, nopt_x),
                               range(0, nopt_y)):
        i, j = d
        name_tmp = 'tmp_' + str(i) + "_" + str(j)
        fic_tmp = user_output_dir + name_tmp + ".tif"
        os.remove(fic_tmp)


    print('Merging individual windmaps into TIFFs...')
    # Because the above parallel windmap generation produces small chunks of the domain with partial overlap, they need to merged into a single tif
    # that removes this overlap
    nwind = np.arange(0, 360., delta_wind)
    rio_merge_path = os.path.join(os.path.join(os.path.dirname(wm.__file__),
                                                      'rio_merge.py'))

    with tqdm(total=len(nwind)) as pbar:
        for wdir in nwind:
            for var in list_tif_2_vrt:

                name_tif = user_output_dir + name_utm + '_' + str(int(wdir)) + '_' + var
                cmd = "find " + user_output_dir[0:-1] + " -type f -name '*_" + str(int(wdir)) + "_10_" + str(
                    res_wind) + "m_" + var + "*.tif' -exec " + sys.executable + " " + rio_merge_path + " "  + name_tif + '.tmp.tif' + " {} +"
                subprocess.check_call([cmd], stdout=subprocess.PIPE,
                                      shell=True)

                gdal.Warp(name_tif + '.tif', name_tif + '.tmp.tif',
                          dstSRS='EPSG:4326', cutlineDSName=cutline, cropToCutline=True,
                          resampleAlg='cubicspline', errorThreshold=0, dstNodata=-9999)
                os.remove(name_tif+'.tmp.tif')

            pbar.update(1)

    print('Finished')


def clip_tif(fic_in, fic_out, xmin, xmax, ymin, ymax, gdal_prefix):
    # projwin by default expressed in the SRS of the dataset
    com_string = gdal_prefix + "gdal_translate -of GTIFF  -ot Float32 -projwin " + \
                 str(xmin) + ", " + str(ymax) + ", " + str(xmax) + ", " + str(ymin) +\
                 " " + fic_in + " " + fic_out
    print(com_string)
    subprocess.check_call([com_string], shell=True)# stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)


def pts_to_shp(points, fname, proj):
    driver = ogr.GetDriverByName("ESRI Shapefile")

    try:
        os.remove(fname)  # remove if existing
    except OSError:
        pass

    shp_file = driver.CreateDataSource(fname)

    srs_out = osr.SpatialReference()
    srs_out.SetFromUserInput(proj)

    layer = shp_file.CreateLayer('mesh', srs_out, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn('Extent', ogr.OFTReal))
    ring = ogr.Geometry(ogr.wkbLinearRing)

    for p in points:
        ring.AddPoint(p[1], p[0])

    #complete the ring
    ring.AddPoint(points[0][1], points[0][0])
    tpoly = ogr.Geometry(ogr.wkbPolygon)
    tpoly.AddGeometry(ring)

    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(tpoly)
    layer.CreateFeature(feature)

    shp_file.FlushCache()
    shp_file = None  # close file







if __name__ == "__main__":
    main()
