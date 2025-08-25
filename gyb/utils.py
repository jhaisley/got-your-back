#!/usr/bin/env python3
#
# Got Your Back - Utility Functions
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import os.path
import platform
import time
import re
import socket
import ssl
import email
import hashlib
import json
from importlib.metadata import version as lib_version
from urllib.parse import urlencode, urlparse, parse_qs
import httplib2

# Program metadata
__program_name__ = 'Got Your Back: Gmail Backup'
__author__ = 'Jay Lee'
__email__ = 'jay0lee@gmail.com'
__version__ = '1.83'
__license__ = 'Apache License 2.0 (https://www.apache.org/licenses/LICENSE-2.0)'
__website__ = 'jaylee.us/gyb'

def getGYBVersion(divider="\n"):
  api_client_ver = lib_version('google-api-python-client')
  return ('Got Your Back %s~DIV~%s~DIV~%s - %s~DIV~Python %s.%s.%s %s-bit '
    '%s~DIV~google-api-client %s~DIV~%s %s' % (__version__, __website__,
    __author__, __email__, sys.version_info[0], sys.version_info[1],
    sys.version_info[2], struct.calcsize('P') * 8, sys.version_info[3],
    api_client_ver, platform.platform(), platform.machine())).replace('~DIV~', divider)

def getProgPath():
  return os.path.dirname(os.path.realpath(sys.argv[0]))

def percentage(part, whole):
  return 100 * float(part) / float(whole)

suffixes = ['b', 'kb', 'mb', 'gb', 'tb', 'pb']
def humansize(myobject):
  nbytes = 0
  if isinstance(myobject, str):
    if myobject.isdigit():
      nbytes = int(myobject)
    else:
      try:
        nbytes = os.path.getsize(myobject)
      except OSError:
        return myobject
  else:
    nbytes = int(myobject)
  if nbytes == 0:
    return '0 B'
  i = 0
  while nbytes >= 1024 and i < len(suffixes)-1:
    nbytes /= 1024.
    i += 1
  f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
  return '%s %s' % (f, suffixes[i])

def bytes_to_larger(myval):
  myval = int(myval)
  if myval < 1024:
    return '%s bytes' % myval
  elif myval < (1024 ** 2):
    return '%.1f KB' % (myval / 1024)
  elif myval < (1024 ** 3):
    return '%.1f MB' % (myval / (1024 ** 2))
  elif myval < (1024 ** 4):
    return '%.1f GB' % (myval / (1024 ** 3))
  elif myval < (1024 ** 5):
    return '%.1f TB' % (myval / (1024 ** 4))

def rewrite_line(mystring, debug=False):
  if not debug:
    print(' ' * 80, end='\r')
  else:
    print()
  print(mystring, end='\r')

def readFile(filename, mode='r', continueOnError=False, displayError=True, encoding=None):
  if encoding is None and mode.find('b') == -1:
    encoding = 'utf-8'
  try:
    if encoding is not None:
      with open(filename, mode, encoding=encoding, newline='') as f:
        content = f.read()
    else:
      with open(filename, mode) as f:
        content = f.read()
    return content
  except IOError as e:
    if continueOnError:
      if displayError:
        sys.stderr.write(f'ERROR: {e}\n')
      return None
    else:
      systemErrorExit(6, f'file {filename}: {e}')
  except UnicodeDecodeError:
    if displayError:
      sys.stderr.write(f'ERROR: file {filename}: encoding error\n')
    if continueOnError:
      return None
    else:
      systemErrorExit(2, f'file {filename}: encoding error')

def writeFile(filename, data, mode='wb', continueOnError=False, displayError=True):
  try:
    with open(filename, mode) as f:
      if mode.find('b') != -1:
        f.write(data.encode('utf-8'))
      else:
        f.write(data)
    return True
  except IOError as e:
    if continueOnError:
      if displayError:
        sys.stderr.write(f'ERROR: {e}\n')
      return False
    else:
      systemErrorExit(6, f'file {filename}: {e}')

def systemErrorExit(code=1, error_text='Unknown Error'):
  sys.stderr.write(f'\nERROR: {error_text}\n')
  sys.exit(code)

def doGYBCheckForUpdates(forceCheck=False, debug=False, config_folder=None):
  import configparser
  import calendar
  
  if config_folder is None:
    config_folder = getProgPath()
  
  config_file = os.path.join(config_folder, 'gyb.cfg')
  config = configparser.ConfigParser()
  if os.path.isfile(config_file):
    config.read(config_file)
  last_update_check_str = config.get('DEFAULT', 'last_update_check', fallback='0')
  last_update_check = int(last_update_check_str)
  now_time = calendar.timegm(time.gmtime())
  one_week = 604800
  if forceCheck or (now_time - last_update_check) > one_week:
    check_url = 'https://api.github.com/repos/GAM-team/got-your-back/releases'
    headers = {'User-Agent': getGYBVersion(' | ')}
    anonhttpc = _createHttpObj()
    try:
      resp, content = anonhttpc.request(check_url, headers=headers)
      if debug:
        sys.stderr.write(f'GYB update check.\n  Request: {check_url}\n  Response: {resp["status"]}\n  Content: {content[:100]}...\n')
      try:
        releases = json.loads(content.decode('utf-8'))
      except (UnicodeDecodeError, ValueError):
        if debug:
          sys.stderr.write(f'GYB update check: failed to decode JSON\n')
        return
      if isinstance(releases, list) and len(releases) > 0:
        release = releases[0]
        latest_version = release['tag_name']
        if latest_version.startswith('v'):
          latest_version = latest_version[1:]
        latest_version = latest_version.strip()
        if latest_version > __version__:
          print(f'GYB {latest_version} release notes:\n{release["body"]}\n\nUpgrade GYB with the following commands:\n\npip install --upgrade gyb\n\nLatest GYB version: {latest_version}\nThis GYB version: {__version__}\n')
      config.set('DEFAULT', 'last_update_check', str(now_time))
      with open(config_file, 'w') as f:
        config.write(f)
    except (socket.error, httplib2.HttpLib2Error, KeyError):
      if debug:
        import traceback
        traceback.print_exc()
      pass

def _createHttpObj(cache=None, timeout=600, tls_min_version=None, tls_max_version=None):
  http_args = {'cache': cache, 'timeout': timeout}
  if tls_max_version:
    http_args['tls_maximum_version'] = tls_max_version
  if tls_min_version:
    http_args['tls_minimum_version'] = tls_min_version
  httpc = httplib2.Http(**http_args)
  if os.environ.get('GOOGLE_API_CLIENT_CERTIFICATE') and \
     os.environ.get('GOOGLE_API_CLIENT_PRIVATE_KEY'):
    cert, key, _ = get_cert_files()
    httpc.add_certificate(key, cert, "")
  return httpc

def get_cert_files():
    import tempfile
    cert_text = os.environ.get('GOOGLE_API_CLIENT_CERTIFICATE')
    key_text = os.environ.get('GOOGLE_API_CLIENT_PRIVATE_KEY')
    key_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
    key_file.write(key_text)
    key_file.flush()
    cert_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
    cert_file.write(cert_text)
    cert_file.flush()
    return cert_file.name, key_file.name, None

def shorten_url(long_url):
  httpc = _createHttpObj()
  shortened_url = None
  headers = {'User-Agent': getGYBVersion(' | ')}
  try:
    body = {
      'long_url': long_url
    }
    body_data = json.dumps(body).encode('utf-8')
    resp, content = httpc.request('https://gotmybk.shortener.link/',
                                  'POST', body=body_data,
                                  headers=headers)
    try:
      parsed_response = json.loads(content.decode('utf-8'))
      shortened_url = parsed_response['short_url']
    except (ValueError, KeyError):
      shortened_url = long_url
  except (socket.error, httplib2.HttpLib2Error):
    shortened_url = long_url
  return shortened_url

def _localhost_to_ip():
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('8.8.8.8', 80))
    ip = s.getsockname()[0]
    s.close()
    return ip
  except:
    return '127.0.0.1'

def cleanup_from(old_from):
    parsed = email.utils.parseaddr(old_from)
    if not parsed[1] or '@' not in parsed[1]:
        return old_from  # Return original if can't parse
    return email.utils.formataddr(parsed)

def message_hygiene(msg):
    """Clean up message for restore"""
    # Convert bytes to email.message.Message for easier manipulation
    if isinstance(msg, bytes):
        msg_obj = email.message_from_bytes(msg)
    else:
        msg_obj = email.message_from_string(msg)
    
    # Clean up From header if it exists
    if 'From' in msg_obj:
        old_from = msg_obj['From']
        new_from = cleanup_from(old_from)
        if old_from != new_from:
            msg_obj.replace_header('From', new_from)
    
    # Convert back to bytes
    return msg_obj.as_bytes()

def _request_with_user_agent(request_method):
    def wrapper(*args, **kwargs):
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        if 'User-Agent' not in kwargs['headers']:
            kwargs['headers']['User-Agent'] = getGYBVersion(' | ')
        return request_method(*args, **kwargs)
    return wrapper

import struct
import calendar