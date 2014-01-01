from compmake import logger

from .describe import *
from .safe_write import *
from .wildcards import *
from .coloredterm import *
from .terminal_size import *

from .strings_with_escapes import *
from .capture import *
from .values_interpretation import *
from .debug_pickler import *
from .time_track import *
from .system_stats import *
from .proctitle import *
from .duration_hum import *
from .system_stats import *

from .safe_pickle import * 
from .frozen import *
from .memoize_imp import *

from .instantiate_utils import *

# from .calling_ext_programs import *

def find_print_statements():
    
    class TracePrints(object):
        def __init__(self):    
            self.stdout = sys.stdout
        
        def write(self, s):
            self.stdout.write("Writing %r\n" % s)
            traceback.print_stack(file=self.stdout)

    sys.stdout = TracePrints()