#!/usr/bin/env python

import sys
import rasterio as rio
import rasterio.merge as merge
import numpy as np


def copy_mean(merged_data, new_data, merged_mask, new_mask, **kwargs):
    mask = np.empty_like(merged_mask, dtype="bool")
    np.logical_or(merged_mask, new_mask, out=mask)
    np.logical_not(mask, out=mask)
    np.add(merged_data, new_data, out=merged_data, where=mask)
    np.logical_not(new_mask, out=mask)
    np.logical_and(merged_mask, mask, out=mask)
    np.copyto(merged_data, new_data, where=mask)






if __name__ == '__main__':
    files = []

    outfile = sys.argv[1]
    for f in sys.argv[2:]:
        files.append(f)

    dest, output_transform = merge.merge([rio.open(f) for f in files], method='max')

    with rio.open(files[0]) as src:
        out_meta = src.meta.copy()
        out_meta.update({"driver": "GTiff",
                          "height": dest.shape[1],
                          "width": dest.shape[2],
                          "transform": output_transform,
                        "nodata":-9999})

        with rio.open(outfile, "w", **out_meta) as dest1:
            dest1.write(dest)

