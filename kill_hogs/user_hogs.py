"""
A mechanism for users to invoke kill hogs.

"""

from pathlib import Path
from kill_hogs import kill_hogs

FLAG_FILE = '/tmp/kill_hogs_flagfile'

def set_flagfile():
    """
    create a flagfile.
    """
    Path(FLAG_FILE).touch()


def run_hogs_when_flagged():
    """
    check for flagfile. run kill hogs if that's the case.
    """
    pass

import ipdb; ipdb.set_trace()

