import loaders
import subset_ops
import viewers

from glue.config import qt_client
from cube_tools.qt.spectra_widget import SpectraWindow
from cube_tools.qt.table_widget import TableWindow
qt_client.add(SpectraWindow)
qt_client.add(TableWindow)