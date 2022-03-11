#!/usr/bin/env python

import sys
import rasterio as rio
import rasterio.merge as merge
import numpy as np


def copy_mean(merged_data, new_data, merged_mask, new_mask, index, **kwargs):
    """
    :param merged_data: array to update with new_data
    :param new_data:    data to merge same shape as merged_data
    :param merged_mask: boolean masks where merged/new data pixels are invalid same shape as merged_data
    :param new_mask:    boolean masks where merged/new data pixels are invalid same shape as merged_data
    :param kwargs:
    :return:
    """
    mask = np.empty_like(merged_mask, dtype="bool")

    #mask = True -> don't do
    np.logical_or(merged_mask, new_mask, out=mask)

    # At locations where the condition is True, the out array will be set to the ufunc result.
    # Elsewhere, the out array will retain its original value.
    # thus invert for use with minimum, not needed here
    # np.logical_not(mask, out=mask)

    # logical_or treatment for the mask
    md = np.ma.masked_array(merged_data, mask=merged_mask)
    nd = np.ma.masked_array(new_data,    mask=new_mask)

    # stack the arrays
    a = np.ma.masked_array((md, nd))

    # Merge  along vertical direction
    m = np.ma.median(a,axis=0)

    np.logical_not(new_mask, out=mask)
    np.logical_and(merged_mask, mask, out=mask)

    # dst, src, <...>
    np.copyto(merged_data, m.data, where=mask, casting="unsafe")



if __name__ == '__main__':
    files = []

    outfile = sys.argv[1]
    for f in sys.argv[2:]:
        files.append(f)

    dest, output_transform = merge.merge([rio.open(f) for f in files], method=copy_mean)

    with rio.open(files[0]) as src:
        out_meta = src.meta.copy()
        out_meta.update({"driver": "GTiff",
                          "height": dest.shape[1],
                          "width": dest.shape[2],
                          "transform": output_transform,
                        "nodata":-9999})

        with rio.open(outfile, "w", **out_meta) as dest1:
            dest1.write(dest)

