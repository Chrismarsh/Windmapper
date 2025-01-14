import os
import random
import subprocess
import sys
import time
from scipy import ndimage
import cloudpickle
import numpy as np
from mpi4py import MPI
from osgeo import gdal


def str2bool(s: str) -> bool:
    if s.lower() == 'true':
        return True

    return False

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

def reproject_to_wgs84(fin, fout, gdal_prefix):
    exec_str = '%sgdalwarp -overwrite -r "cubicspline" -t_srs "+proj=lcc +lon_0=-90 +lat_1=33 +lat_2=45" -dstnodata -9999 %s %s'

    com_string = exec_str % (gdal_prefix, fin, fout)
    subprocess.check_call([com_string], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)


def call_WN_1dir(WINDNINJA_DATA, gdal_prefix, user_output_dir, fic_config_WN, list_tif_2_vrt, nopt_x, nopt_y, nx, ny,
                 pixel_height, pixel_width, res_wind, targ_res, var_transform, wind_average, wn_exe, xmin, ymin,
                 ijwdir):
    # when launching back to back windninja processes, there is a race condition in the WN check to determine
    # if a directory is writeable
    # https://github.com/firelab/windninja/issues/382
    # so add a little jitter to the process invocation to 'fix' this.
    # This should be resolved in WN 3.8.0 but leave this as is for now
    time.sleep(random.random() * 5)

    i, j, wdir = ijwdir
    i = int(i)
    j = int(j)

    # Out directory
    dir_tmp = user_output_dir + 'tmp_dir' + "_" + str(i) + "_" + str(j)
    name_tmp = 'tmp_' + str(i) + "_" + str(j)
    fic_dem_in = user_output_dir + name_tmp + ".tif"

    name_base = dir_tmp + '/' + name_tmp + '_' + str(int(wdir)) + '_10_' + str(res_wind) + 'm_'

    exec_cmd = wn_exe + ' ' + \
               fic_config_WN + ' --elevation_file ' + fic_dem_in + ' --mesh_resolution ' + str(
        res_wind) + ' --input_direction ' + str(int(wdir)) + ' --output_path ' + dir_tmp

    try:
        os.environ["WINDNINJA_DATA"] = WINDNINJA_DATA
        out = subprocess.check_output([exec_cmd],
                                      # stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT,
                                      shell=True)

    except subprocess.CalledProcessError as e:
        print('WindNinja failed to run. Something has gone very wrong.\n'
              'Run command was:\n'
              f'{exec_cmd}\n'
              'Output was:\n'
              f'{e.output.decode("utf-8")}')
        raise RuntimeError()



    for var in var_transform:
        name_gen = name_base + var
        try:
            subprocess.check_call([gdal_prefix + 'gdal_translate ' + name_gen + '.asc ' + name_gen + '.tif'],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE,
                                  shell=True)
        except subprocess.SubprocessError as e:
            print(
                'The file gdal was expecting to transform was not present. This is almost certainly due to this issue https://github.com/firelab/windninja/issues/382 '
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
    save_tif(uu, vel_tif, fic_tif + '.tmp.tif')
    reproject_to_wgs84(fic_tif + '.tmp.tif', fic_tif, gdal_prefix)
    os.remove(fic_tif + '.tmp.tif')

    vv = -1 * np.cos(ang * np.pi / 180.)
    fic_tif = name_base + 'V_large.tif'
    save_tif(vv, vel_tif, fic_tif + '.tmp.tif')
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


def main(pickle_file: str,
         disconnect: bool):
    # if called from SLURM, etc, these cli are coming in as strings
    if isinstance(disconnect, str):
        disconnect = str2bool(disconnect)

    pickle_file = pickle_file.replace('RANK', str(MPI.COMM_WORLD.rank))

    with open(pickle_file, 'rb') as f:
        param_args = cloudpickle.load(f)

    # print(param_args)

    WINDNINJA_DATA, MPI_nworkers, gdal_prefix, user_output_dir, fic_config_WN, list_tif_2_vrt, nopt_x, nopt_y, nx, ny, \
        pixel_height, pixel_width, res_wind, targ_res, var_transform, wind_average, wn_exe, xmin, ymin, \
        ijwdir = param_args

    if MPI_nworkers != MPI.COMM_WORLD.size:
        print(f'Configuration asked for {MPI_nworkers} MPI workers but MPI.COMM_WORLD.size={MPI.COMM_WORLD.size} ')
        exit(-1)

    # ijwdir is a list of all the combinations we need to run. THis rank will have a section of work to do
    # ijwdir is [ [i,j,wdir], ..., [i,j,wdir] ]
    # so iterate over that
    for ijw in ijwdir:
        call_WN_1dir(WINDNINJA_DATA, gdal_prefix, user_output_dir, fic_config_WN, list_tif_2_vrt, nopt_x, nopt_y, nx,
                     ny,
                     pixel_height, pixel_width, res_wind, targ_res, var_transform, wind_average, wn_exe, xmin, ymin,
                     ijw)

    # have been run from the MPI.spawn, so disconnect from parent
    if disconnect:
        comm = MPI.Comm.Get_parent()
        comm.Disconnect()


if __name__ == '__main__':
    main(*sys.argv[1:])
