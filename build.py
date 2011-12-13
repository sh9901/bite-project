#!/usr/bin/python
#
# Copyright 2011 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""Build the BITE Extension."""

__author__ = ('ralphj@google.com (Julie Ralph)'
              'jason.stredwick@gmail.com (Jason Stredwick)')

import logging
import optparse
import os
import shutil
import subprocess
import sys
import urllib
import zipfile


# Common folders.
GENFILES_ROOT = 'genfiles'
OUTPUT_ROOT = 'output'
DEPS_ROOT = 'deps'

# Common roots
BUG_ROOT = os.path.join('tools', 'bug', 'extension')
RPF_ROOT = os.path.join('tools', 'rpf', 'extension')

# Output paths
EXTENSION_DST = os.path.join(OUTPUT_ROOT, 'extension')
SERVER_DST = os.path.join(OUTPUT_ROOT, 'server')
IMGS_DST = os.path.join(EXTENSION_DST, 'imgs')
OPTIONS_DST = os.path.join(EXTENSION_DST, 'options')
STYLES_DST = os.path.join(EXTENSION_DST, 'styles')

# Keywords for DEPS
CHECKOUT_COMMAND = 'checkout'
ROOT = 'root'
URL = 'url'

# Define dependencies that are checkout from various repositories.
DEPS = {
  'ace': {
    ROOT: os.path.join(DEPS_ROOT, 'ace'),
    URL: 'git://github.com/ajaxorg/ace.git',
    CHECKOUT_COMMAND: 'git clone %s %s'
  },
  'gdata-python-client': {
    ROOT: os.path.join(DEPS_ROOT, 'gdata-python-client'),
    URL: 'http://code.google.com/p/gdata-python-client/',
    CHECKOUT_COMMAND: 'hg clone %s %s'
  },
  'selenium-atoms-lib': {
    ROOT: os.path.join(DEPS_ROOT, 'selenium-atoms-lib'),
    URL: 'http://selenium.googlecode.com/svn/trunk/javascript/atoms',
    CHECKOUT_COMMAND: 'svn checkout %s %s'
  },
  'closure-library': {
    ROOT: os.path.join(DEPS_ROOT, 'closure', 'closure-library'),
    URL: 'http://closure-library.googlecode.com/svn/trunk/',
    CHECKOUT_COMMAND: 'svn checkout %s %s'
  }
}

CLOSURE_COMPILER_ROOT = os.path.join(DEPS_ROOT, 'closure')
CLOSURE_COMPILER_JAR = os.path.join(CLOSURE_COMPILER_ROOT, 'compiler.jar')
CLOSURE_COMPILER_URL = ('http://closure-compiler.googlecode.com/files/'
                        'compiler-latest.zip')

SOY_COMPILER_ROOT = os.path.join(DEPS_ROOT, 'soy')
SOY_COMPILER_JAR = os.path.join(SOY_COMPILER_ROOT, 'SoyToJsSrcCompiler.jar')
SOY_COMPILER_URL = ('http://closure-templates.googlecode.com/files/'
                    'closure-templates-for-javascript-latest.zip')
SOY_COMPILER_SRC = os.path.join(DEPS_ROOT, 'soy', 'src')
SOYDATA_URL = ('http://closure-templates.googlecode.com/svn/trunk/javascript/'
               'soydata.js')

# Compiling commands.
CLOSURE_COMPILER = os.path.join(DEPS['closure-library'][ROOT], 'closure',
                                'bin', 'build', 'closurebuilder.py')
COMPILE_CLOSURE_COMMAND = ' '.join([
  sys.executable, CLOSURE_COMPILER,
  ('--root=%s' % os.path.join('common', 'extension')),
  ('--root=%s' % os.path.join('extension', 'src')),
  ('--root=%s' % os.path.join(BUG_ROOT, 'src')),
  ('--root=%s' % os.path.join(RPF_ROOT, 'src')),
  ('--root=%s' % DEPS['closure-library'][ROOT]),
  ('--root=%s' % SOY_COMPILER_SRC),
  ('--root=%s' % GENFILES_ROOT),
  ('--root=%s' % DEPS['selenium-atoms-lib'][ROOT]),
  '--input=%(input)s',
  '--output_mode=compiled',
  '--output_file=%(output)s',
  ('--compiler_jar=%s' % CLOSURE_COMPILER_JAR)])

SOY_COMPILER_COMMAND = ' '.join([('java -jar %s' % SOY_COMPILER_JAR),
                                 '--shouldProvideRequireSoyNamespaces',
                                 '--outputPathFormat %(output)s',
                                 '%(input)s'])


class ClosureError(Exception):
  pass


def Clean():
  """Clean removes the generated files and output."""
  if os.path.exists(OUTPUT_ROOT):
    shutil.rmtree(OUTPUT_ROOT)
  if os.path.exists(GENFILES_ROOT):
    shutil.rmtree(GENFILES_ROOT)


def CleanExpunge():
  """Cleans up the generated and output files plus the dependencies."""
  if os.path.exists(DEPS_ROOT):
    shutil.rmtree(DEPS_ROOT)
  Clean()


def CompileScript(filename_base, filepath, suffix_in, suffix_out, command):
  """Compile a script based on the given input file.

  Args:
    filename: The base name of the script to compile. (string)
    filepath: The location of the the script. (string)
    suffix_in: The suffix to add to the basename for input. (string)
    suffix_out: The suffix to add to the basename for output. (string)
    command: The compile command to use.

  Raises:
    ClosureError: If closure fails to compile the given input file.
  """
  input = os.path.join(filepath, ('%s%s' % (filename_base, suffix_in)))
  output = os.path.join(GENFILES_ROOT, ('%s%s' % (filename_base, suffix_out)))

  # For speed, only compile the script if it is not already compiled.
  if os.path.exists(output):
    return

  data = {'input': input,
          'output': output}
  result = ExecuteCommand(command % data)
  if result or not os.path.exists(output):
    raise ClosureError('Failed while compiling %s.' % input)


def ExecuteCommand(command):
  """Execute the given command and return the output.

  Args:
    command: A string representing the command to execute.

  Returns:
    The return code of the process.
  """
  print 'Running command: %s' % command
  process = subprocess.Popen(command.split(' '),
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
  results = process.communicate()
  if process.returncode:
    logging.error(results[1])
  return process.returncode


def SetupClosureCompiler():
  """Setup the closure library and compiler.

  Checkout the closure library using svn if it doesn't exist. Also, download
  the closure compiler.

  Raises:
    ClosureError: If the setup fails.
  """
  # Download the compiler jar if it doesn't exist.
  if not os.path.exists(CLOSURE_COMPILER_JAR):
    print('Downloading closure compiler jar file.')
    (compiler_zip, _) = urllib.urlretrieve(CLOSURE_COMPILER_URL)
    compiler_zipfile = zipfile.ZipFile(compiler_zip)
    compiler_zipfile.extract('compiler.jar', CLOSURE_COMPILER_ROOT)
    if not os.path.exists(CLOSURE_COMPILER_JAR):
      logging.error('Could not download the closure compiler jar.')
      raise ClosureError('Could not find the closure compiler.')


def SetupDep(dep_name):
  """Download the dependency to the correct location.

  Args:
    dep_name: The name of the dependency to setup. (string)
  """
  dep = DEPS[dep_name]
  if not os.path.exists(dep[ROOT]):
    ExecuteCommand(dep[CHECKOUT_COMMAND] % (dep[URL], dep[ROOT]))
    if not os.path.exists(dep[ROOT]):
      logging.error('Could not checkout %s from %s.' % (dep_name, dep[URL]))
      raise ClosureError('Could not set up %s.' % dep_name)


def SetupSoyCompiler():
  """Setup the closure library and compiler.

  Checkout the closure library using svn if it doesn't exist. Also, download
  the closure compiler.

  Raises:
    ClosureError: If the setup fails.
  """
  # Download the soy compiler jar if it doesn't exist.
  soyutils_src = os.path.join(SOY_COMPILER_SRC, 'soyutils_usegoog.js')
  if (not os.path.exists(SOY_COMPILER_JAR) or
      not os.path.exists(soyutils_src)):
    print('Downloading soy compiler and utils.')
    (soy_compiler_zip, _) = urllib.urlretrieve(SOY_COMPILER_URL)
    soy_compiler_zipfile = zipfile.ZipFile(soy_compiler_zip)
    soy_compiler_zipfile.extract('SoyToJsSrcCompiler.jar', SOY_COMPILER_ROOT)
    soy_compiler_zipfile.extract('soyutils_usegoog.js', SOY_COMPILER_SRC)
    if (not os.path.exists(SOY_COMPILER_JAR) or
        not os.path.exists(soyutils_src)):
      logging.error('Could not download the soy compiler jar.')
      raise ClosureError('Could not find the soy compiler.')

  # Download required soydata file, which is required for soyutils_usegoog.js
  # to work.
  soydata_src = os.path.join(SOY_COMPILER_SRC, 'soydata.js')
  if not os.path.exists(soydata_src):
    urllib.urlretrieve(SOYDATA_URL, soydata_src)
    if not os.path.exists(soydata_src):
      logging.error('Could not download soydata.js.')
      raise ClosureError('Could not fine soydata.js')


def main():
  usage = 'usage: %prog [options]'
  parser = optparse.OptionParser(usage)
  parser.add_option('--clean', dest='build_clean',
                    action='store_true', default=False,
                    help='Clean the build directories.')
  parser.add_option('--expunge', dest='build_expunge',
                    action='store_true', default=False,
                    help='Clean the build directories and deps.')
  (options, _) = parser.parse_args()

  # Exit if only want to clean.
  if options.build_clean:
    Clean()
    exit()
  elif options.build_expunge:
    CleanExpunge()
    exit()

  # Set up the directories that will be built into.
  paths = [GENFILES_ROOT, DEPS_ROOT]
  for path in paths:
    if not os.path.exists(path):
      os.mkdir(path)

  # Get external resources.
  for dep_name in DEPS:
    SetupDep(dep_name)
  SetupClosureCompiler()
  SetupSoyCompiler()

  # Compile the closure scripts.
  # Soy
  soy_files = {
    'popup': os.path.join('extension', 'templates'),
    'consoles': os.path.join(BUG_ROOT, 'templates'),
    'newbug_console': os.path.join(BUG_ROOT, 'templates'),
    'newbug_type_selector': os.path.join(BUG_ROOT, 'templates'),
    'rpfconsole': os.path.join(RPF_ROOT, 'templates'),
    'rpf_dialogs': os.path.join(RPF_ROOT, 'templates'),
    'locatorsupdater': os.path.join(RPF_ROOT, 'templates'),
    'explore': os.path.join('extension', 'src', 'project', 'templates'),
    'general': os.path.join('extension', 'src', 'project', 'templates'),
    'member': os.path.join('extension', 'src', 'project', 'templates'),
    'settings': os.path.join('extension', 'src', 'project', 'templates')
  }

  for soy_filename in soy_files:
    soy_filepath = soy_files[soy_filename]
    CompileScript(soy_filename, soy_filepath, '.soy', '.soy.js',
                  SOY_COMPILER_COMMAND)

  # JavaScript
  js_targets = {
    'background': os.path.join('extension', 'src'),
    'content': os.path.join('extension', 'src'),
    'getactioninfo': os.path.join(RPF_ROOT, 'src'),
    'console': os.path.join(RPF_ROOT, 'src'),
    'elementhelper': os.path.join('extension', 'src'),
    'popup': os.path.join('extension', 'src'),
    'page': os.path.join('extension', 'src', 'options')
  }

  for target in js_targets:
    target_filepath = js_targets[target]
    CompileScript(target, target_filepath, '.js', '_script.js',
                  COMPILE_CLOSURE_COMMAND)

  # Remove the outputs, so they will be created again.
  if os.path.exists(OUTPUT_ROOT):
    shutil.rmtree(OUTPUT_ROOT)
  os.mkdir(OUTPUT_ROOT)

  # Create extension bundle.
  print('Creating extension bundle.')
  #   Create the extension bundle and options path.
  paths = [EXTENSION_DST, OPTIONS_DST, STYLES_DST]
  for path in paths:
    if not os.path.exists(path):
      os.mkdir(path)

  #   Manifest
  shutil.copy(os.path.join('extension', 'manifest.json'), EXTENSION_DST)

  #   Styles
  styles = [os.path.join('extension', 'styles', 'consoles.css'),
            os.path.join('extension', 'styles', 'options.css'),
            os.path.join('extension', 'styles', 'popup.css'),
            os.path.join('extension', 'styles', 'rpf_console.css'),
            os.path.join(RPF_ROOT, 'styles', 'recordmodemanager.css')]
  for style in styles:
    shutil.copy(style, STYLES_DST)

  #   Images
  shutil.copytree(os.path.join('extension', 'imgs'), IMGS_DST)

  #   HTML
  html = [os.path.join('extension', 'html', 'background.html'),
          os.path.join('extension', 'html', 'popup.html'),
          os.path.join('extension', 'src', 'options', 'options.html'),
          os.path.join(RPF_ROOT, 'html', 'console.html')]
  for html_file in html:
    shutil.copy(html_file, EXTENSION_DST)

  #   Scripts
  scripts = []
  for target in js_targets:
    shutil.copy(os.path.join(GENFILES_ROOT, ('%s_script.js' % target)),
                EXTENSION_DST)

  #   Copy the required ACE files.
  ace_dst = os.path.join(EXTENSION_DST, 'ace')
  ace_src = os.path.join(DEPS['ace'][ROOT], 'build', 'src')
  if os.path.exists(ace_dst):
    shutil.rmtree(ace_dst)
  shutil.copytree(ace_src, ace_dst)

  # Create server bundle.
  print('Creating server bundle.')
  server_src = 'server'
  shutil.copytree(server_src, SERVER_DST)

  gdata_src = os.path.join(DEPS['gdata-python-client'][ROOT], 'src', 'gdata')
  shutil.copytree(gdata_src, os.path.join(SERVER_DST, 'gdata'))

  atom_src = os.path.join(DEPS['gdata-python-client'][ROOT], 'src', 'atom')
  shutil.copytree(atom_src, os.path.join(SERVER_DST, 'atom'))

if __name__ == '__main__':
  main()