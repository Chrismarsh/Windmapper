"""Prepare a rectangular, fully populated elevation grid for WindNinja."""

import math

import numpy as np
from osgeo import gdal
from pyproj import Transformer


def largest_valid_window(ds, anchor=None):
    """Find the maximum-area valid pixel window, optionally containing (col, row)."""
    band = ds.GetRasterBand(1)
    mask = band.GetMaskBand()
    nodata = band.GetNoDataValue()
    if nodata is None:
        nodata = -9999  # WindNinja's fallback for untagged elevation rasters.
    alpha = None
    for i in range(2, ds.RasterCount + 1):
        other = ds.GetRasterBand(i)
        if other.GetColorInterpretation() == gdal.GCI_AlphaBand:
            alpha = other
            break

    width = ds.RasterXSize
    heights = np.zeros(width + 1, dtype=np.int32)  # trailing zero closes the last run
    best = None
    best_area = 0
    for row in range(ds.RasterYSize):
        z = band.ReadAsArray(0, row, width, 1)[0]
        valid = np.isfinite(z) & (z != nodata)
        valid &= mask.ReadAsArray(0, row, width, 1)[0] != 0
        if alpha is not None:
            valid &= alpha.ReadAsArray(0, row, width, 1)[0] > 0
        heights[:-1] = np.where(valid, heights[:-1] + 1, 0)

        # Consecutive valid heights form a histogram. A falling edge closes
        # every taller rectangle on the stack at this column (exclusive).
        stack = []
        for right in np.flatnonzero(np.diff(heights, prepend=0)).tolist():
            height = int(heights[right])
            left = right
            while stack and stack[-1][1] > height:
                left, h = stack.pop()
                top = row + 1 - h
                area = (right - left) * h
                if area > best_area and (
                    anchor is None or (left <= anchor[0] < right and top <= anchor[1] <= row)
                ):
                    best = (left, top, right - left, h)
                    best_area = area
            if height and (not stack or stack[-1][1] < height):
                stack.append((left, height))

    if best is None:
        if anchor is not None:
            raise ValueError(f"DEM anchor at pixel {anchor} has no valid elevation")
        raise ValueError("The DEM contains no valid elevations")
    return best


def prepare_existing_dem(filename, output, skip_mercator_proj=False, anchor_lonlat=None):
    """Select the rectangle on the projected grid from which all tiles are copied."""
    src = gdal.Open(filename)
    srs = src.GetSpatialRef()
    if srs is None:
        raise ValueError(f"DEM has no coordinate system: {filename}")

    gt = src.GetGeoTransform()
    if skip_mercator_proj:
        if not srs.IsProjected() or not math.isclose(srs.GetLinearUnits(), 1.0):
            raise ValueError("skip_mercator_proj requires a projected DEM in metres")
        target = src.GetProjection()
    else:
        x, y = gdal.ApplyGeoTransform(gt, src.RasterXSize / 2, src.RasterYSize / 2)
        _, lat = Transformer.from_crs(src.GetProjection(), 'EPSG:4326', always_xy=True).transform(x, y)
        target = f"+proj=merc +lat_ts={lat} +datum=WGS84 +units=m"

    grid = src
    north_up_square = gt[1] > 0 and gt[2] == gt[4] == 0 and math.isclose(gt[1], -gt[5], rel_tol=1e-12)
    if not skip_mercator_proj or not north_up_square:
        # GDAL can suggest non-square cells when the input already uses the
        # chosen CRS. Keep the suggested pixel area while enforcing dx == dy.
        suggested = gdal.AutoCreateWarpedVRT(src, None, target).GetGeoTransform()
        resolution = math.sqrt(abs(suggested[1] * suggested[5] - suggested[2] * suggested[4]))
        nodata = src.GetRasterBand(1).GetNoDataValue()
        grid = gdal.Warp(
            '', src, format='VRT', dstSRS=target, resampleAlg='bilinear',
            xRes=resolution, yRes=resolution, outputType=gdal.GDT_Float32,
            srcNodata=nodata if nodata is not None else -9999, dstNodata=-9999,
        )

    anchor = None
    if anchor_lonlat is not None:
        transform = Transformer.from_crs('EPSG:4326', grid.GetProjection(), always_xy=True)
        x, y = transform.transform(*anchor_lonlat, errcheck=True)
        col, row = gdal.ApplyGeoTransform(gdal.InvGeoTransform(grid.GetGeoTransform()), x, y)
        anchor = (math.floor(col), math.floor(row))
        if not (0 <= anchor[0] < grid.RasterXSize and 0 <= anchor[1] < grid.RasterYSize):
            raise ValueError(f"DEM anchor {anchor_lonlat} lies outside the projected grid")

    window = largest_valid_window(grid, anchor)
    x, y, width, height = window
    print(f"Selected valid DEM window at ({x}, {y}): {width} x {height} "
          f"of {grid.RasterXSize} x {grid.RasterYSize} pixels")
    return gdal.Translate(output, grid, format='GTiff', srcWin=window, bandList=[1],
                          maskBand='none', creationOptions=['TILED=YES', 'BIGTIFF=IF_SAFER'])


def tile_window(width, height, i, j, count_x, count_y, overlap):
    """Return an overlapping pixel window. Tile (0, 0) is the southwest tile."""
    left = max(0, i * width // count_x - overlap)
    right = min(width, (i + 1) * width // count_x + overlap)
    top = max(0, height - (j + 1) * height // count_y - overlap)
    bottom = min(height, height - j * height // count_y + overlap)
    return left, top, right - left, bottom - top
