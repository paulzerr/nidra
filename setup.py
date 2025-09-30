from setuptools import setup, Extension

# This is a dummy extension to force the creation of platform-specific wheels.
# It is required for cibuildwheel to work correctly when a project has platform-specific
# dependencies but no compiled code of its own.
dummy_extension = Extension('NIDRA.dummy', sources=['NIDRA/dummy.c'])

setup(
    ext_modules=[dummy_extension]
)