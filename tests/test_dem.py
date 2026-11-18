import itertools
import tempfile
import unittest
from pathlib import Path

import numpy as np
from osgeo import gdal, osr
from pyproj import Transformer

from windmapper.dem import largest_valid_window, prepare_existing_dem, tile_window


class TestDemWindows(unittest.TestCase):
    def test_largest_rectangle_against_exhaustive_search(self):
        ds = gdal.GetDriverByName('MEM').Create('', 3, 3, 1, gdal.GDT_Float32)
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999)
        intervals = list(itertools.combinations(range(4), 2))
        for bits in itertools.product([False, True], repeat=9):
            valid = np.array(bits).reshape(3, 3)
            band.WriteArray(np.where(valid, -125, -9999))
            for anchor in (None, (1, 1)):
                candidates = []
                for (left, right), (top, bottom) in itertools.product(intervals, repeat=2):
                    if anchor and not (left <= anchor[0] < right and top <= anchor[1] < bottom):
                        continue
                    if valid[top:bottom, left:right].all():
                        candidates.append((left, top, right - left, bottom - top))
                if candidates:
                    window = largest_valid_window(ds, anchor)
                    self.assertIn(window, candidates)
                    self.assertEqual(window[2] * window[3], max(w * h for _, _, w, h in candidates))
                else:
                    with self.assertRaises(ValueError):
                        largest_valid_window(ds, anchor)

    def test_masks_and_nonfinite_values(self):
        ds = gdal.GetDriverByName('MEM').Create('', 7, 1, 2, gdal.GDT_Float32)
        band = ds.GetRasterBand(1)
        band.WriteArray(np.array([[17, -120, 0, np.nan, -9999, np.inf, 3]]))
        band.CreateMaskBand(gdal.GMF_PER_DATASET)
        band.GetMaskBand().WriteArray(np.array([[0, 255, 255, 255, 255, 255, 255]], dtype='uint8'))
        alpha = ds.GetRasterBand(2)
        alpha.SetColorInterpretation(gdal.GCI_AlphaBand)
        alpha.WriteArray(np.array([[255, 255, 255, 255, 255, 255, 0]]))
        self.assertEqual(largest_valid_window(ds), (1, 0, 2, 1))
        for x in (0, 3, 4, 5, 6):
            with self.assertRaises(ValueError):
                largest_valid_window(ds, (x, 0))

    def test_project_crop_and_anchor(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = str(Path(tmp) / 'dem.tif')
            ds = gdal.GetDriverByName('GTiff').Create(src, 16, 12, 1, gdal.GDT_Float32)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(32608)
            ds.SetProjection(srs.ExportToWkt())
            ds.SetGeoTransform((450000, 30, 0, 7600000, 0, -30))
            band = ds.GetRasterBand(1)
            band.SetNoDataValue(-9999)
            z = np.full((12, 16), -120, dtype=np.float32)
            z[:8, 8:] = -9999
            band.WriteArray(z)
            ds = None

            to_geo = Transformer.from_crs('EPSG:32608', 'EPSG:4326', always_xy=True)
            anchor = to_geo.transform(450000 + 14.5 * 30, 7600000 - 10.5 * 30)
            out = str(Path(tmp) / 'cropped.tif')
            for native in (True, False):
                cropped = prepare_existing_dem(src, out, native, anchor)
                self.assertTrue((cropped.ReadAsArray() == -120).all())
                if native:
                    self.assertEqual((cropped.RasterXSize, cropped.RasterYSize), (16, 4))
                    self.assertEqual(cropped.GetGeoTransform(), (450000, 30, 0, 7599760, 0, -30))
                cropped = None

            with self.assertRaisesRegex(ValueError, 'outside'):
                prepare_existing_dem(src, out, True, (-110, 50))

    def test_rectify_non_square_cells_in_simulation_crs(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = str(Path(tmp) / 'mercator.tif')
            ds = gdal.GetDriverByName('GTiff').Create(src, 40, 20, 1, gdal.GDT_Float32)
            srs = osr.SpatialReference()
            srs.ImportFromProj4('+proj=merc +lat_ts=0 +datum=WGS84')
            ds.SetProjection(srs.ExportToWkt())
            ds.SetGeoTransform((0, 90, 0, 300, 0, -30))
            ds.GetRasterBand(1).Fill(10)
            ds = None
            for native in (True, False):
                cropped = prepare_existing_dem(src, str(Path(tmp) / 'out.tif'), native)
                gt = cropped.GetGeoTransform()
                self.assertEqual(gt[1], -gt[5])
                self.assertEqual((gt[2], gt[4]), (0, 0))
                self.assertTrue((cropped.ReadAsArray() == 10).all())
                cropped = None

    def test_tile_overlap_and_coverage(self):
        for nx, ny in [(1, 1), (1, 3), (3, 1), (3, 2)]:
            covered = np.zeros((73, 101), dtype=bool)
            for i, j in itertools.product(range(nx), range(ny)):
                x, y, w, h = tile_window(101, 73, i, j, nx, ny, 25)
                self.assertTrue(0 <= x < x + w <= 101 and 0 <= y < y + h <= 73)
                covered[y:y + h, x:x + w] = True
            self.assertTrue(covered.all())
        self.assertEqual(tile_window(101, 73, 0, 0, 3, 2, 25), (0, 12, 58, 61))
