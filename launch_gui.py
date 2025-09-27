import runpy
import sys

if __name__ == '__main__':
    # This is a clean way to run a module within a package.
    # It avoids messy sys.path manipulations.
    runpy.run_module('NIDRA.nidra_gui.launcher', run_name='__main__')