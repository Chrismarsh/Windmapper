#!/usr/bin/env python

# Wind Mapper
# Copyright (C) 2020 Vincent Vionnet & Christopher Marsh
# Script to build wind maps for CHM based on the Wind Ninja diagnostic wind model
# Take an existing DEM or download it from SRTM-30m the Web
# Split the DEM into several subdomain suitable for WindNinja
# Execute the WN simulations
# Combine the outputs into a single vrt file covering the initial DEM extent


import elevation
import pdb, os, shutil
import subprocess
from osgeo import gdal, ogr, osr
from pyproj import Proj, transform, Transformer
import numpy as np
import sys
import importlib
from functools import partial
import itertools
from scipy import ndimage
from os import environ
from concurrent import futures
from tqdm import tqdm
import random
import time
import rasterio as rio

gdal.UseExceptions()  # Enable exception support


def main():
    #######  load user configurable paramters here    #######
    # Check user defined configuration file

    if len(sys.argv) == 1:
        print(
            'ERROR: wind_mapper.py requires one argument [configuration file] (i.e. wind_mapper.py '
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

    # default path assumes we are running out of pip or we have a symlink @ ./bin/WindNinja_cli
    wn_exe = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)), 'bin', 'WindNinja_cli')

    if hasattr(X, 'wn_exe'):
        wn_exe = X.wn_exe

    if not os.path.exists(wn_exe):
        print('ERROR: Invalid path for WindNinja_cli. Consider specifying a `wn_exe` config option or confirm it is correct.')
        print(f'Path = {wn_exe}')
        exit(-1)

    environ["WINDNINJA_DATA"] = os.path.join(os.path.dirname(wn_exe), '..', 'share', 'windninja')

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

        lat_min = X.lat_min
        lat_max = X.lat_max
        lon_min = X.lon_min
        lon_max = X.lon_max
    else:
        lat_min = X.lat_min
        lat_max = X.lat_max
        lon_min = X.lon_min
        lon_max = X.lon_max

    if not use_existing_dem:
        if lat_min == -9999 or lon_min == -9999 or lat_max == -9999 or lon_max == -9999:
            print('Coordinates of the bounding box must be specified to download SRTM DEM.')
            exit(-1)

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

    # Setup file containing WN configuration
    nworkers = os.cpu_count() or 1

    # on linux we can ensure that we respect cpu affinity
    if 'sched_getaffinity' in dir(os):
        nworkers = len(os.sched_getaffinity(0))

    # ensure correct formatting on the output
    fic_config = F"""num_threads = {nworkers}  
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

    LCC_proj = '+proj=lcc +lon_0=-90 +lat_1=33 +lat_2=45'
    LCC_proj = None
    if use_existing_dem:

        # if we are using a user-provided dem, ensure there are no NoData values that border the
        # DEM which will cause issues
        print('Preparing input DEM')
        # mask data values
        print('...',end='')
        exec_str = """%sgdal_calc.py -A %s --outfile %s --NoDataValue 0 --calc="1*(A>0)" """ % (gdal_prefix,
            dem_filename, user_output_dir + 'out.tif')
        subprocess.check_call([exec_str],   shell=True) #stdout=subprocess.PIPE,  stderr=subprocess.PIPE,
        print('25...', end='')

        # convert to shp file
        exec_str = """%sgdal_polygonize.py -8 -b 1 -f "ESRI Shapefile" %s %s/pols """ % (gdal_prefix,
            user_output_dir + 'out.tif', user_output_dir)
        subprocess.check_call([exec_str],  shell=True)
        print('50...', end='')

        # clip original with the shpfile
        exec_str = """%sgdalwarp -of GTiff -cutline %s/pols/out.shp -crop_to_cutline -dstalpha %s %s """ % (gdal_prefix,
            user_output_dir, dem_filename, fic_lcc)
        subprocess.check_call([exec_str], shell=True)
        print('75...', end='')
        shutil.rmtree("%s/pols" % user_output_dir)
        os.remove("%s/out.tif" % user_output_dir)
        print('100', end='')
        print(' - done')



    else:

        # need to ensure that we request a square domain in LCC projection

        # Properties of the bounding box
        delta_lat = lat_max - lat_min
        delta_lon = lon_max - lon_min

        fac = 0.1  # Expansion factor to make sure that the downloaded SRTM tile is large enough

        # This is a larger extent than what we will use so we ensure perfect coverage
        lon_min_expanded = lon_min - delta_lon * fac
        lat_min_expanded = lat_min - delta_lat * fac
        lon_max_expanded = lon_max + delta_lon * fac
        lat_max_expanded = lat_max + delta_lat * fac

        LCC_proj = '+proj=merc +lat_ts=%.30f' % ((lat_min_expanded + lat_max_expanded)/2.0)

        t_4326_to_lcc = Transformer.from_crs("epsg:4326", LCC_proj)
        lon_lcc, lat_lcc = t_4326_to_lcc.transform(
                                                   [lat_min_expanded, lat_min_expanded, lat_max_expanded, lat_max_expanded],
                                                   [lon_min_expanded, lon_max_expanded, lon_min_expanded, lon_max_expanded],
                                                   )
        lon_lcc_square = [ min(lon_lcc), min(lon_lcc), max(lon_lcc), max(lon_lcc)]
        lat_lcc_square = [ min(lat_lcc), max(lat_lcc), min(lat_lcc), max(lat_lcc)]

        t_merc_to_4326 = Transformer.from_crs(LCC_proj, "epsg:4326",)
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


    srs_out = osr.SpatialReference()
    srs_out.ImportFromEPSG(4326)

    pts_to_shp([[lat_max, lon_min],
                [lat_max, lon_max],
                [lat_min, lon_max],
                [lat_min, lon_min]],
               os.path.join(user_output_dir,'shp','user_bbox.shp'),
               srs_out.ExportToProj4(),
               )

    ds = gdal.Open(fic_lcc)
    wkt = ds.GetProjection()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)

    if LCC_proj is None:
        LCC_proj = srs.ExportToProj4()

    band = ds.GetRasterBand(1)
    gt = ds.GetGeoTransform()

    t_4326_to_merc = Transformer.from_crs("epsg:4326", LCC_proj, always_xy=True)
    x_merc, y_merc = t_4326_to_merc.transform(
        [lon_min, lon_max, lon_min, lon_max],
        [lat_min, lat_min, lat_max, lat_max],
    )

    xmin = min(x_merc)
    xmax = max(x_merc)
    ymin = min(y_merc)
    ymax = max(y_merc)


    is_geographic = srs.IsGeographic()
    if is_geographic:
        raise Exception('Input DEM must be projected ')

    pixel_width = gt[1]
    pixel_height = -gt[5]

    lenx = xmax-xmin
    leny = ymax-ymin

    len_wn = res_wind * nres

    # Number of Wind Ninja tiles
    nopt_x = int(lenx // len_wn + 1)
    nopt_y = int(leny // len_wn + 1)

    nx = lenx/pixel_width / nopt_x
    ny = leny/pixel_height / nopt_y

    if nopt_x == 1 and nopt_y == 1:
        # DEM is small enough for WN
        name_tmp = 'tmp_0_0'
        fic_tmp = user_output_dir + name_tmp + ".tif"
        shutil.copy(fic_lcc, fic_tmp)

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
                                         fic_download,
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

    print(f'Running WindNinja on {len(x_y_wdir)} combinations of direction and sub-area. Please be patient...')
    with futures.ProcessPoolExecutor(max_workers=nworkers) as executor:
        res = list(tqdm(executor.map(partial(call_WN_1dir, gdal_prefix, user_output_dir, fic_config_WN,
                                             list_tif_2_vrt, nopt_x, nopt_y, nx, ny,
                                             pixel_height, pixel_width, res_wind, targ_res, var_transform, wind_average,
                                             wn_exe,
                                             xmin, ymin), x_y_wdir), total=len(x_y_wdir)))

    for d in itertools.product(range(0, nopt_x),
                               range(0, nopt_y)):
        i, j = d
        name_tmp = 'tmp_' + str(i) + "_" + str(j)
        fic_tmp = user_output_dir + name_tmp + ".tif"
        os.remove(fic_tmp)


    print('Building VRTs...')
    # Loop on wind direction to build reference vrt file to be used by mesher
    nwind = np.arange(0, 360., delta_wind)
    with tqdm(total=len(nwind)) as pbar:
        for wdir in nwind:
            for var in list_tif_2_vrt:
                # name_vrt = user_output_dir + name_utm + '_' + str(int(wdir)) + '_' + var + '.vrt'
                # cmd = "find " + user_output_dir[0:-1] + " -type f -name '*_" + str(int(wdir)) + "_10_" + str(
                #     res_wind) + "m_" + var + "*.tif' -exec " + gdal_prefix + "gdalbuildvrt " + name_vrt + " {} +"

                name_tif = user_output_dir + name_utm + '_' + str(int(wdir)) + '_' + var
                cmd = "find " + user_output_dir[0:-1] + " -type f -name '*_" + str(int(wdir)) + "_10_" + str(
                    res_wind) + "m_" + var + "*.tif' -exec rio_merge.py " +  name_tif + '.tmp.tif' + " {} +"
                subprocess.check_call([cmd], stdout=subprocess.PIPE,
                                      shell=True)

                srs_out = osr.SpatialReference()
                srs_out.ImportFromEPSG(4326)
                exec_str = '%sgdalwarp -overwrite -te %f %f %f %f -r "cubicspline" -et 0 -cutline %s -crop_to_cutline -dstnodata -9999 -t_srs "%s" %s %s'
                com_string = exec_str % (gdal_prefix,
                                         X.lon_min, X.lat_min, X.lon_max, X.lat_max,
                                         os.path.join(user_output_dir,'shp', 'user_bbox.shp'),
                                         srs_out.ExportToProj4(),
                                         name_tif+'.tmp.tif',
                                         name_tif+'.tif')
                subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                os.remove(name_tif+'.tmp.tif')

            pbar.update(1)




def call_WN_1dir(gdal_prefix, user_output_dir, fic_config_WN, list_tif_2_vrt, nopt_x, nopt_y, nx, ny,
                 pixel_height, pixel_width, res_wind, targ_res, var_transform, wind_average, wn_exe, xmin, ymin,
                 ijwdir):

    # when launching back to back windninja processes, there is a race condition in the WN check to determine
    # if a directory is writeable
    # https://github.com/firelab/windninja/issues/382
    # so add a little jitter to the process invocation to 'fix' this.
    time.sleep(random.random()*5)

    i, j, wdir = ijwdir

    # Out directory
    dir_tmp = user_output_dir + 'tmp_dir' + "_" + str(i) + "_" + str(j)
    name_tmp = 'tmp_' + str(i) + "_" + str(j)
    fic_dem_in = user_output_dir + name_tmp + ".tif"

    name_base = dir_tmp + '/' + name_tmp + '_' + str(int(wdir)) + '_10_' + str(res_wind) + 'm_'

    exec_cmd = wn_exe + ' ' + \
               fic_config_WN + ' --elevation_file ' + fic_dem_in + ' --mesh_resolution ' + str(
        res_wind) + ' --input_direction ' + str(int(wdir)) + ' --output_path ' + dir_tmp
    try:

        out = subprocess.check_output([exec_cmd],
                              # stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,
                              shell=True)
    except subprocess.SubprocessError as e:
        print('WindNinja failed to run. Something has gone very wrong.\n'
              'Run command was:\n'
              f'{exec_cmd}\n'
              'Please raise an issue on the WindMapper github https://github.com/Chrismarsh/Windmapper')
        print(e.output())
        raise RuntimeError()

    for var in var_transform:
        name_gen = name_base + var
        try:
            subprocess.check_call([gdal_prefix + 'gdal_translate ' + name_gen + '.asc ' + name_gen + '.tif'],
                                  stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                  shell=True)
        except subprocess.SubprocessError as e:
            print('The file gdal was expecting to transform was not present. This is almost certainly due to this issue https://github.com/firelab/windninja/issues/382 '
                  'Please raise an issue on the WindMapper github https://github.com/Chrismarsh/Windmapper')
            raise RuntimeError()

        os.remove(name_gen + '.asc')
        os.remove(name_gen + '.prj')

    # Read geotif for angle and velocity to compute speed up
    gtif = gdal.Open(name_base + 'ang.tif')
    ang = gtif.GetRasterBand(1).ReadAsArray()
    vel_tif = gdal.Open(name_base + 'vel.tif')
    vel = vel_tif.GetRasterBand(1).ReadAsArray()

    # Compute and save wind components
    uu = -1 * np.sin(ang * np.pi / 180.)
    fic_tif = name_base + 'U_large.tif'
    save_tif(uu, vel_tif, fic_tif+'.tmp.tif')
    reproject_to_wgs84(fic_tif+'.tmp.tif', fic_tif, gdal_prefix)
    os.remove(fic_tif+'.tmp.tif')

    vv = -1 * np.cos(ang * np.pi / 180.)
    fic_tif = name_base + 'V_large.tif'
    save_tif(vv, vel_tif, fic_tif+'.tmp.tif')
    reproject_to_wgs84(fic_tif + '.tmp.tif', fic_tif, gdal_prefix)
    os.remove(fic_tif + '.tmp.tif')

    # Compute smooth wind speed
    if wind_average == 'grid':
        nsize = targ_res / res_wind
        vv_large = ndimage.uniform_filter(vel, size=nsize, mode='nearest')
        fic_tif = name_base + 'spd_up_' + str(targ_res) + '_large.tif'
    elif wind_average == 'mean_tile':
        vv_large = np.mean(vel)
        fic_tif = name_base + 'spd_up_tile_large.tif'

    # Compute local speed up and save
    loc_speed_up = vel / vv_large
    save_tif(loc_speed_up, vel_tif, fic_tif + '.tmp.tif')
    reproject_to_wgs84(fic_tif + '.tmp.tif', fic_tif, gdal_prefix)
    os.remove(fic_tif + '.tmp.tif')


    # Reduce the extent of the final tif
    # xbeg = xmin + i * nx * pixel_width
    # ybeg = ymin + j * ny * pixel_height
    # delx = nx * pixel_width
    # dely = ny * pixel_height
    #
    # for var in list_tif_2_vrt:
    #     fic_tif = name_base + var + '_large.tif'
    #     fic_tif_fin = name_base + var + '.tif'
    #     if nopt_x == 1 and nopt_y == 1:
    #         shutil.copy(fic_tif, fic_tif_fin)
    #     else:
    #         clip_tif(fic_tif, fic_tif_fin, xbeg, xbeg + delx, ybeg, ybeg + dely, gdal_prefix)
    #     os.remove(fic_tif)

def reproject_to_wgs84(fin, fout, gdal_prefix):
    exec_str = '%sgdalwarp -overwrite -r "cubicspline" -t_srs "+proj=lcc +lon_0=-90 +lat_1=33 +lat_2=45" %s %s'   #epsg:4326

    com_string = exec_str % (gdal_prefix, fin, fout)
    subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)


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
    srs_out.ImportFromProj4(proj)

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




def save_tif(var, inDs, fic):
    # Create the geotif
    driver = inDs.GetDriver()
    rows = inDs.RasterYSize
    cols = inDs.RasterXSize
    outDs = driver.Create(fic, cols, rows, 1, gdal.GDT_Float32)
    # Create new band
    outBand = outDs.GetRasterBand(1)
    outBand.WriteArray(var, 0, 0)

    # Flush data to disk
    outBand.FlushCache()

    # Georeference the image and set the projection
    outDs.SetGeoTransform(inDs.GetGeoTransform())
    outDs.SetProjection(inDs.GetProjection())

    outDs = None


if __name__ == "__main__":
    main()
