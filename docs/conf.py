import os
import sys
import pkg_resources

sys.path.insert(0, os.path.abspath('..'))

master_doc = 'index'
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']
