import six

from os.path import basename
import warnings

import numpy as np
from astropy.table import Table

from glue.core import Data, Component
from glue.core.data import CategoricalComponent
from glue.config import data_factory
from glue.core.data_factories.helpers import has_extension
from glue.core.coordinates import coordinates_from_header, coordinates_from_wcs
from glue.external.astro import fits
from glue.utils import coerce_numeric

from .core.data_objects import CubeData, SpectrumData, ImageData
from .core.custom_registry import CubeDataIOError


@data_factory("STcube", has_extension("fits fit"))
def read_cube(filename, **kwargs):
    cube_data = None
    exclude_exts = []
    data_collection = []
    hdulist = fits.open(filename)
    try:
        cube_data = CubeData.read(hdulist)
    except CubeDataIOError as e:
        warnings.warn('No CubeData found in "{}": {}'.format(
            filename,
            e.message
        ))

    if cube_data is not None:
        data = Data()
        try:
            data.coords = coordinates_from_wcs(cube_data.wcs)
        except AttributeError:
            # There is no wcs. Not to worry now.
            pass
        data.add_component(Component(cube_data), label="cube")
        data_collection.append(data)
        exclude_exts = cube_data.meta.get('hdu_ids')

    # Read in the rest of the FITS file.
    data_collection += _load_fits_generic(hdulist,
                                          exclude_exts=exclude_exts)
    return data_collection


# Removed from the glue data factory. Keeing it internal only.
#@data_factory('Generic FITS', has_extension('fits fit'))
def _load_fits_generic(source, exclude_exts=None, **kwargs):
    """Read in all extensions from a FITS file.

    Parameters
    ----------
    source: str or HDUList
        The pathname to the FITS file.
        If and HDUList is passed in, simply use that.

    exclude_exts: [hdu, ] or [index, ]
        List of HDU's to exclude from reading.
        This can be a list of HDU's or a list
        of HDU indexes.
    """
    exclude_exts = exclude_exts or []
    if not isinstance(source, fits.hdu.hdulist.HDUList):
        hdulist = fits.open(source)
    else:
        hdulist = source
    groups = dict()
    label_base = basename(hdulist.filename()).rpartition('.')[0]

    if not label_base:
        label_base = basename(hdulist.filename())

    for extnum, hdu in enumerate(hdulist):
        hdu_name = hdu.name if hdu.name else str(extnum)
        if hdu.data is not None and \
           hdu_name not in exclude_exts and \
           extnum not in exclude_exts:
            if is_image_hdu(hdu):
                shape = hdu.data.shape
                try:
                    data = groups[shape]
                except KeyError:
                    label = '{}[{}]'.format(
                        label_base,
                        'x'.join(str(x) for x in shape)
                    )
                    data = Data(label=label)
                    data.coords = coordinates_from_header(hdu.header)
                    groups[shape] = data
                data.add_component(component=hdu.data,
                                   label=hdu_name)
            elif is_table_hdu(hdu):
                # Loop through columns and make component list
                table = Table(hdu.data)
                table_name = '{}[{}]'.format(
                    label_base,
                    hdu_name
                )
                for column_name in table.columns:
                    column = table[column_name]
                    shape = column.shape
                    data_label = '{}[{}]'.format(
                        table_name,
                        'x'.join(str(x) for x in shape)
                    )
                    try:
                        data = groups[data_label]
                    except KeyError:
                        data = Data(label=data_label)
                        groups[data_label] = data
                    component = Component(column, units=column.unit)
                    data.add_component(component=component,
                                       label=column_name)
    return [data for data in six.itervalues(groups)]


# Utilities
def is_image_hdu(hdu):
    from astropy.io.fits.hdu import PrimaryHDU, ImageHDU
    return isinstance(hdu, (PrimaryHDU, ImageHDU))


def is_table_hdu(hdu):
    from astropy.io.fits.hdu import TableHDU, BinTableHDU
    return isinstance(hdu, (TableHDU, BinTableHDU))


class MOSCategoricalComponent(CategoricalComponent):
    def __init__(self, data, meta=None, quantity=None, **kwargs):
        super(MOSCategoricalComponent, self).__init__(data, **kwargs)
        self._meta = meta
        self._quantity = quantity

    @property
    def meta(self):
        return self._meta

    @property
    def quantity(self):
        return self._quantity

    def jitter(self, method=None):
        super(MOSCategoricalComponent, self).jitter(method)


class MOSComponent(Component):
    def __init__(self, data, meta=None, quantity=None, **kwargs):
        super(MOSComponent, self).__init__(data, **kwargs)
        self._meta = meta or {}
        self._quantity = quantity

    @property
    def meta(self):
        return self._meta

    @property
    def quantity(self):
        return self._quantity

    def jitter(self, method=None):
        super(MOSComponent, self).jitter(method)

    @classmethod
    def autotyped(cls, data, units=None, meta=None, quantity=None):
        """
        Automatically choose between Component and CategoricalComponent,
        based on the input data type.

        :param data: The data to pack into a Component (array-like)
        :param units: Optional units
        :type units: str

        :returns: A Component (or subclass)
        """
        data = np.asarray(data)

        if np.issubdtype(data.dtype, np.object_):
            return CategoricalComponent(data, units=units)

        n = coerce_numeric(data)
        thresh = 0.5
        try:
            use_categorical = np.issubdtype(data.dtype, np.character) and \
                np.isfinite(n).mean() <= thresh
        except TypeError:  # isfinite not supported. non-numeric dtype
            use_categorical = True

        if use_categorical:
            return MOSCategoricalComponent(data, units=units,
                                           meta=meta, quantity=quantity)
        else:
            return MOSComponent(n, units=units, meta=meta,
                                quantity=quantity)


@data_factory(label="MOS Catalog",
              identifier=has_extension('xml vot csv txt tsv tbl dat fits '
                                       'xml.gz vot.gz csv.gz txt.gz tbl.bz '
                                       'dat.gz fits.gz'))
def load_mos_data(*args, **kwargs):
    path = "/".join(args[0].strip().split('/')[:-1])
    result = Data()

    # Read the table
    from astropy.table import Table

    table = Table.read(*args, format='ascii', **kwargs)

    # Loop through columns and make component list
    for column_name in table.columns:
        print(column_name)
        c = table[column_name]
        d = None
        u = c.unit if hasattr(c, 'unit') else c.units
        m = dict()

        m['cell'] = c
        m['path'] = path

        # if d is not None:
        #     print("Attempting to autotype")
        #     nc = MOSComponent(np.array([np.array(dt))
        #     result.add_component(nc, column_name)
        # else:
        nc = MOSComponent.autotyped(c, units=u, meta=m)
        result.add_component(nc, column_name)

    return result
