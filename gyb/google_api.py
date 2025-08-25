#!/usr/bin/env python3
#
# Got Your Back - Google API Functions
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
import configparser
import time
import random
import socket
import ssl

import httplib2
import google_auth_httplib2
import googleapiclient
from googleapiclient.discovery import build, build_from_document, V2_DISCOVERY_URI
from googleapiclient.http import MediaIoBaseUpload, BatchHttpRequest
import googleapiclient.errors

from .utils import _createHttpObj, systemErrorExit, readFile, getGYBVersion
from .auth import getValidOauth2TxtCredentials, getSvcAcctCredentials

# Global variable to hold extra API arguments
extra_args = {'prettyPrint': False}

def getAPIVer(api):
  if api == 'oauth2':
    return 'v2'
  elif api == 'gmail':
    return 'v1'
  elif api == 'groupsmigration':
    return 'v1'
  elif api == 'drive':
    return 'v3'
  elif api == 'cloudresourcemanager':
    return 'v1'
  else:
    return 'v1'

def getAPIScope(api):
  if api == 'oauth2':
    return ['https://www.googleapis.com/auth/userinfo.email',]
  elif api == 'gmail':
    return ['https://mail.google.com/',]
  elif api == 'groupsmigration':
    return ['https://www.googleapis.com/auth/apps.groups.migration',]
  elif api == 'drive':
    return ['https://www.googleapis.com/auth/drive.appdata',]
  elif api == 'cloudresourcemanager':
    return ['https://www.googleapis.com/auth/cloudresourcemanager',]

def getClientOptions():
    from . import options
    
    client_options = None
    ca_certs_file = getattr(options, 'ca_file', None)
    if ca_certs_file:
        import google.api_core.client_options
        client_options = google.api_core.client_options.ClientOptions(ca_certs_file=ca_certs_file)
    return client_options

def buildGAPIObject(api, httpc=None):
  global extra_args
  from . import options
  
  if not httpc:
    credentials = getValidOauth2TxtCredentials()
    httpc = google_auth_httplib2.AuthorizedHttp(credentials, _createHttpObj())
  if options.debug:
    extra_args['prettyPrint'] = True
  if os.path.isfile(os.path.join(options.config_folder, 'extra-args.txt')):
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(os.path.join(options.config_folder, 'extra-args.txt'))
    extra_args.update(dict(config.items('extra-args')))
  version = getAPIVer(api)
  client_options = getClientOptions()
  try:
    service = build(
            api,
            version,
            http=httpc,
            cache_discovery=False,
            client_options=client_options,
            static_discovery=False)
  except googleapiclient.errors.UnknownApiNameOrVersion:
    disc_file = os.path.join(options.config_folder, f'{api}-{version}.json')
    if os.path.isfile(disc_file):
      with open(disc_file, 'r') as f:
        discovery = f.read()
      service = build_from_document(
              discovery,
              http=httpc,
              cache_discovery=False,
              client_options=client_options)
    else:
      print('ERROR: %s API version %s is not available' % (api, version))
      raise
  except (httplib2.ServerNotFoundError, RuntimeError) as e:
    systemErrorExit(4, e)
  except Exception as e:
    systemErrorExit(5, e)
  return service

def buildGAPIServiceObject(api, soft_errors=False):
  global extra_args
  from . import options
  
  auth_as = options.use_admin if options.use_admin else options.email
  scopes = getAPIScope(api)
  credentials = getSvcAcctCredentials(scopes, auth_as)
  if options.debug:
    extra_args['prettyPrint'] = True
  if os.path.isfile(os.path.join(options.config_folder, 'extra-args.txt')):
    config = configparser.ConfigParser()
    config.optionxform = str
    ex_args_file = os.path.join(options.config_folder, 'extra-args.txt')
    config.read(ex_args_file)
    extra_args.update(dict(config.items('extra-args')))
  httpc = _createHttpObj()
  request = google_auth_httplib2.Request(httpc)
  credentials.refresh(request)
  version = getAPIVer(api)
  client_options = getClientOptions()
  try:
    service = build(
            api,
            version,
            http=httpc,
            cache_discovery=False,
            client_options=client_options,
            static_discovery=False)
    service._http = google_auth_httplib2.AuthorizedHttp(credentials, http=httpc)
    return service
  except (httplib2.ServerNotFoundError, RuntimeError) as e:
    systemErrorExit(4, e)
  except google.auth.exceptions.RefreshError as e:
    if isinstance(e.args, tuple):
      e = e.args[0]
    systemErrorExit(5, e)

def _backoff(n, retries, reason):
  wait_on_fail = (2 ** n) if (2 ** n) < 60 else 60
  randomness = float(random.randint(1, 1000)) / 1000
  wait_on_fail += randomness
  if n > 3:
    sys.stderr.write('\nTemporary error %s. Backing off %s seconds...' % (reason, int(wait_on_fail)))
  time.sleep(wait_on_fail)
  if n > 3:
    sys.stderr.write('attempt %s/%s\n' % (retries - n, retries))

def callGAPI(service, function, soft_errors=False, throw_reasons=[], retry_reasons=[], **kwargs):
  import google.auth.exceptions
  from . import options, extra_args
  
  retries = 10
  parameters = dict(extra_args.items())
  parameters.update(kwargs)
  for n in range(1, retries+1):
    try:
      if function:
        method = getattr(service, function)
        return method(**parameters).execute()
      else:
        return service.execute()
    except googleapiclient.errors.HttpError as e:
      try:
        error = json.loads(e.content.decode())
        reason = error['error']['errors'][0]['reason']
        message = error['error']['errors'][0]['message']
      except (KeyError, ValueError, UnicodeDecodeError):
        reason = e.resp.status
        message = e.content
      if reason in throw_reasons:
        raise e
      if n != retries and (reason in ['rateLimitExceeded', 'userRateLimitExceeded', 'backendError', 'internalError'] + retry_reasons):
        _backoff(n, retries, reason)
        continue
      if soft_errors:
        sys.stderr.write('Soft error: %s - %s\n' % (reason, message))
        return
      sys.stderr.write('Error: %s - %s\n' % (reason, message))
      sys.exit(5)
    except google.auth.exceptions.RefreshError as e:
      sys.stderr.write('Error: Authentication Token Error - %s' % e)
      sys.exit(403)
    except httplib2.CertificateValidationUnsupported:
      print('\nERROR: You don\'t have the Python ssl module installed so we can\'t\nverify SSL Certificates. You can fix this by installing the\nPython ssl module or you can live on the edge and turn off\nSSL certificate verification by setting:\n\nexport PYTHONHTTPSVERIFY=0\n\nThen run gyb again.')
      sys.exit(8)
    except (httplib2.ServerNotFoundError, socket.error) as e:
      if n != retries:
        _backoff(n, retries, str(e))
        continue
      systemErrorExit(4, str(e))

def callGAPIpages(service, function, items='items',
                 nextPageToken='nextPageToken', page_message=None, message_attribute=None,
                 **kwargs):
  pageToken = None
  all_pages = []
  total_items = 0
  while True:
    this_page = callGAPI(service, function,
      pageToken=pageToken, **kwargs)
    if not this_page:
      this_page = {items: []}
    try:
      page_items = len(this_page[items])
    except KeyError:
      page_items = 0
    total_items += page_items
    if page_message:
      show_message = page_message.replace('%%num_items%%', str(page_items))
      show_message = show_message.replace('%%total_items%%', str(total_items))
      if message_attribute:
        try:
          show_message = show_message.replace('%%first_item%%', str(this_page[items][0][message_attribute]))
          show_message = show_message.replace('%%last_item%%', str(this_page[items][-1][message_attribute]))
        except (IndexError, KeyError):
          show_message = show_message.replace('%%first_item%%', '')
          show_message = show_message.replace('%%last_item%%', '')
      sys.stderr.write('\r%s' % show_message)
    try:
      all_pages.extend(this_page[items])
    except KeyError:
      pass
    try:
      pageToken = this_page[nextPageToken]
    except KeyError:
      if page_message:
        sys.stderr.write('\n')
      return all_pages

import json