import os
import sys
import pkg_resources

sys.path.insert(0, os.path.abspath('..'))

release = pkg_resources.get_distribution('urconf').version

master_doc = 'index'
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']
