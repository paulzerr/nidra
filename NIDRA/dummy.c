#include <Python.h>

// Method definition object for this extension.
// An empty array is sufficient as we don't need any methods.
static PyMethodDef dummy_methods[] = {
    {NULL, NULL, 0, NULL}
};

// Module definition struct.
static struct PyModuleDef dummymodule = {
    PyModuleDef_HEAD_INIT,
    "dummy",
    "A dummy C extension to force platform-specific wheels.",
    -1,
    dummy_methods
};

// Module initialization function.
PyMODINIT_FUNC PyInit_dummy(void) {
    return PyModule_Create(&dummymodule);
}