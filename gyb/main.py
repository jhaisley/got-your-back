#!/usr/bin/env python3
#
# Got Your Back - Main Entry Point
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
import sqlite3
import datetime
import ssl
import httplib2

from .cli import SetupOptionParser
from .utils import getGYBVersion, doGYBCheckForUpdates, _createHttpObj, __version__
from .auth import getValidOauth2TxtCredentials, doesTokenMatchEmail
from .google_api import buildGAPIObject, buildGAPIServiceObject
from .database import (initializeDB, get_db_settings, check_db_settings, convertDB, 
                       getMessageIDs, rebuildUIDTable, adapt_date_iso, adapt_datetime_iso, 
                       adapt_datetime_epoch, convert_date, convert_datetime, convert_timestamp,
                       __db_schema_version__)

# Global variables that need to be accessible across modules
options = None
gmail = None
reserved_labels = ['inbox', 'spam', 'trash', 'unread', 'starred', 'important',
  'sent', 'draft', 'chat', 'chats', 'migrated', 'todo', 'todos', 'buzz',
  'bin', 'allmail', 'drafts', 'archive', 'archived', 'muted']
system_labels = ['INBOX', 'SPAM', 'TRASH', 'UNREAD', 'STARRED', 'IMPORTANT',
                 'SENT', 'DRAFT', 'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL',
                 'CATEGORY_PROMOTIONS', 'CATEGORY_UPDATES', 'CATEGORY_FORUMS']

def main(argv):
  global options, gmail
  import gyb.utils
  import gyb.auth  
  import gyb.google_api
  import gyb.database
  
  options = SetupOptionParser(argv)
  
  # Set global options for the package
  gyb.options = options
  gyb.utils.options = options
  gyb.auth.options = options  
  gyb.google_api.options = options
  gyb.database.options = options
  
  if options.debug:
    httplib2.debuglevel = 4

  doGYBCheckForUpdates(debug=options.debug, config_folder=options.config_folder)
  if options.version:
    print(getGYBVersion())
    print('Path: %s' % getProgPath())
    print('ConfigPath: %s' % options.config_folder)
    print(ssl.OPENSSL_VERSION)
    anonhttpc = _createHttpObj()
    headers = {'User-Agent': getGYBVersion(' | ')}
    if os.environ.get('GOOGLE_API_CLIENT_CERTIFICATE') and \
     os.environ.get('GOOGLE_API_CLIENT_PRIVATE_KEY'):
      host = 'gmail.mtls.googleapis.com'
    else:
      host = 'gmail.googleapis.com'
    anonhttpc.request(f'https://{host}', headers=headers)
    cipher_name, tls_ver, _ = anonhttpc.connections[f'https:{host}'].sock.cipher()
    print(f'{host} connects using {tls_ver} {cipher_name}')
    sys.exit(0)
  if options.shortversion:
    sys.stdout.write(__version__)
    sys.exit(0)
  if options.action == 'split-mbox':
    print('split-mbox is no longer necessary and is deprecated. Mbox file size should not impact restore performance in this version.')
    sys.exit(1)
  if not options.email:
    print('ERROR: --email is required.')
    sys.exit(1)
  if options.action in ['restore', 'restore-group', 'restore-mbox'] and \
     options.gmail_search != '-is:chat':
    print('ERROR: --search does not work with restores.')
    sys.exit(1)
  if options.local_folder == 'XXXuse-email-addressXXX':
    options.local_folder = "GYB-GMail-Backup-%s" % options.email
  if options.action == 'create-project':
    doCreateProject()
    sys.exit(0)
  elif options.action == 'delete-projects':
    doDelProjects()
    sys.exit(0)
  elif options.action == 'check-service-account':
    doCheckServiceAccount()
    sys.exit(0)
  if options.extra_reserved_labels:
    global reserved_labels
    reserved_labels = reserved_labels + options.extra_reserved_labels
  if options.extra_system_labels:
    global system_labels
    system_labels = system_labels + options.extra_system_labels
  if not options.service_account:  # 3-Legged OAuth
    getValidOauth2TxtCredentials()
    if not doesTokenMatchEmail():
      sys.exit(9)
    gmail = buildGAPIObject('gmail')
  else:
    gmail = buildGAPIServiceObject('gmail')
  if not os.path.isdir(options.local_folder):
    if options.action in ['backup', 'backup-chat']:
      os.mkdir(options.local_folder)
    elif options.action in ['restore', 'restore-group', 'restore-mbox']:
      print('ERROR: Folder %s does not exist. Cannot restore.'
        % options.local_folder)
      sys.exit(3)

  sqldbfile = os.path.join(options.local_folder, 'msg-db.sqlite')
  # Do we need to initialize a new database?
  newDB = not os.path.isfile(sqldbfile)
  
  # If we're not doing a estimate or if the db file actually exists we open it
  # (creates db if it doesn't exist)
  if options.action not in ['count', 'purge', 'purge-labels', 'print-labels',
    'quota', 'revoke', 'create-label']:
    if options.action not in ['estimate', 'restore-mbox', 'restore-group'] or os.path.isfile(sqldbfile):
      print("\nUsing backup folder %s" % options.local_folder)
      global sqlconn
      global sqlcur
      sqlite3.register_adapter(datetime.date, adapt_date_iso)
      sqlite3.register_adapter(datetime.datetime, adapt_datetime_iso)
      sqlite3.register_adapter(datetime.datetime, adapt_datetime_epoch)
      sqlite3.register_converter("date", convert_date)
      sqlite3.register_converter("datetime", convert_datetime)
      sqlite3.register_converter("timestamp", convert_timestamp)
      sqlconn = sqlite3.connect(sqldbfile,
        detect_types=sqlite3.PARSE_DECLTYPES)
      sqlcur = sqlconn.cursor()
      if newDB:
        initializeDB(sqlconn, options.email)
      db_settings = get_db_settings(sqlcur)
      check_db_settings(db_settings, options.action, options.email)
      if options.action not in ['restore', 'restore-group', 'restore-mbox']:
        if db_settings['db_version'] <  __db_schema_version__:
          convertDB(sqlconn, db_settings['db_version'])
          db_settings = get_db_settings(sqlcur)
        if options.action == 'reindex':
          getMessageIDs(sqlconn, options.local_folder)
          rebuildUIDTable(sqlconn)
          sqlconn.commit()
          sys.exit(0)
    else:
      sqlconn = sqlite3.connect(':memory:')
      sqlcur = sqlconn.cursor()

  # At this point we would call the appropriate action functions
  # For now, we'll import the original main function and defer to it
  # This ensures compatibility while the refactoring is in progress
  from .legacy import execute_action

  # Execute the action with all the necessary global state
  execute_action(options, gmail, sqlconn, sqlcur, newDB)

if __name__ == '__main__':
    main(sys.argv[1:])

from .utils import getProgPath

# Expose functions needed by other modules
def doCreateProject():
    """Create a new Google Cloud project for GYB"""
    print("ERROR: Project creation functionality has been moved to gyb library format.")
    print("This feature is temporarily unavailable during the refactoring.")
    sys.exit(1)

def doDelProjects():
    """Delete Google Cloud projects"""
    print("ERROR: Project deletion functionality has been moved to gyb library format.")
    print("This feature is temporarily unavailable during the refactoring.")
    sys.exit(1)

def doCheckServiceAccount():
    """Check service account configuration"""
    print("ERROR: Service account check functionality has been moved to gyb library format.")
    print("This feature is temporarily unavailable during the refactoring.")
    sys.exit(1)