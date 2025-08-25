#!/usr/bin/env python3
#
# Got Your Back - Database Functions
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
import datetime
import sqlite3
from .utils import __version__, systemErrorExit

__db_schema_version__ = '6'
__db_schema_min_version__ = '6'        #Minimum for restore

def initializeDB(sqlconn, email):
  sqlconn.execute('''CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT);''')
  sqlconn.execute('''INSERT INTO settings (name, value) VALUES (?, ?);''',
       ('email_address', email))
  sqlconn.execute('''INSERT INTO settings (name, value) VALUES (?, ?);''',
       ('db_version', __db_schema_version__))
  sqlconn.execute('''CREATE TABLE messages(message_num INTEGER PRIMARY KEY,
                         message_filename TEXT,
                         message_internaldate TIMESTAMP);''')
  sqlconn.execute('''CREATE TABLE labels (message_num INTEGER, label TEXT);''')
  sqlconn.execute('''CREATE TABLE uids (message_num INTEGER, uid TEXT PRIMARY KEY);''')
  sqlconn.execute('''CREATE UNIQUE INDEX labelidx ON labels (message_num, label);''')
  sqlconn.commit()

def get_db_settings(sqlcur):
  sqlcur.execute('SELECT name, value FROM settings')
  db_settings = dict(sqlcur.fetchall())
  return db_settings

def check_db_settings(db_settings, action, user_email_address):
  if (db_settings['db_version'] < __db_schema_min_version__  or
      db_settings['db_version'] > __db_schema_version__):
    print("\\n\\nSorry, this backup folder was created with version %s of the \
database schema while GYB %s requires version %s - %s for restores"
% (db_settings['db_version'], __version__, __db_schema_min_version__,
__db_schema_version__))
    sys.exit(4)

  # Only restores are allowed to use a backup folder started with another
  # account (can't allow 2 Google Accounts to backup/estimate from same folder)
  if action not in ['restore', 'restore-group', 'restore-mbox']:
    if user_email_address.lower() != db_settings['email_address'].lower():
      print("\\n\\nSorry, this backup folder should only be used with the %s \
account that it was created with for incremental backups. You specified the\
 %s account" % (db_settings['email_address'], user_email_address))
      sys.exit(5)

def convertDB(sqlconn, uidvalidity, oldversion):
  print("Converting database")
  try:
    with sqlconn:
      if oldversion < '3':
        # Convert to schema 3
        sqlconn.executescript('''
          BEGIN;
          CREATE TABLE uids 
              (message_num INTEGER, uid INTEGER PRIMARY KEY); 
          INSERT INTO uids (uid, message_num) 
               SELECT message_num as uid, message_num FROM messages;
          CREATE INDEX labelidx ON labels (message_num);
          CREATE INDEX flagidx ON flags (message_num);
        ''')
      if oldversion < '4':
        # Convert to schema 4
        sqlconn.execute('''
          ALTER TABLE messages ADD COLUMN rfc822_msgid TEXT;
        ''')
      if oldversion < '5':
        # Convert to schema 5
        sqlconn.executescript('''
          DROP INDEX labelidx;
          DROP INDEX flagidx;
          CREATE UNIQUE INDEX labelidx ON labels (message_num, label);
          CREATE UNIQUE INDEX flagidx ON flags (message_num, flag);
        ''')
      if oldversion < '6':
        # Convert to schema 6 
        sqlconn.executescript('''
          DROP INDEX flagidx;
          DROP TABLE flags;
        ''')
      # Update version in database
      sqlconn.execute('''UPDATE settings SET value = ? WHERE name = ?''',
           (__db_schema_version__, 'db_version'))
  except sqlite3.OperationalError as e:
    systemErrorExit(1, e)

def getMessageIDs (sqlconn, backup_folder):   
  sqlcur = sqlconn.cursor()
  sqlcur.execute('SELECT message_num, message_filename FROM messages')
  results = sqlcur.fetchall()
  for x in results:
    message_filename = x[1]
    if not os.path.isfile(os.path.join(backup_folder, message_filename)):
      sqlcur.execute('DELETE FROM messages WHERE message_num = ?', (x[0],))
      sqlcur.execute('DELETE FROM labels WHERE message_num = ?', (x[0],))
      sqlcur.execute('DELETE FROM uids WHERE message_num = ?', (x[0],))
  sqlconn.commit()

def rebuildUIDTable(sqlconn):
  sqlcur = sqlconn.cursor()
  sqlcur.execute('DELETE FROM uids')
  sqlcur.execute('INSERT INTO uids (message_num, uid) SELECT message_num, message_num FROM messages')
  sqlconn.commit()

def message_is_backed_up(message_num, sqlcur, sqlconn, backup_folder):
  sqlcur.execute(
   'SELECT message_filename FROM messages WHERE message_num = ? LIMIT 1',
    (message_num,))
  sqlresults = sqlcur.fetchall()
  for x in sqlresults:
    filename = x[0]
    if os.path.isfile(os.path.join(backup_folder, filename)):
      return True
    else:
      # Oops, the file got deleted, remove the entry
      print("WARNING! File %s was deleted manually, removing entry from the database." % 
        os.path.join(backup_folder, filename))
      sqlcur.execute('DELETE FROM messages WHERE message_num = ?', (message_num,))
      sqlcur.execute('DELETE FROM labels WHERE message_num = ?', (message_num,))
      sqlcur.execute('DELETE FROM uids WHERE message_num = ?', (message_num,))
      sqlconn.commit()
      return False
  return False

# SQLite adapter and converter functions for date/datetime handling
def adapt_date_iso(val):
    """Adapt datetime.date to ISO 8601 date."""
    return val.isoformat()

def adapt_datetime_iso(val):
    """Adapt datetime.datetime to timezone-naive ISO 8601 date."""
    return val.isoformat()

def adapt_datetime_epoch(val):
    """Adapt datetime.datetime to Unix timestamp."""
    return int(val.timestamp())

def convert_date(val):
    """Convert ISO 8601 date to datetime.date object."""
    return datetime.date.fromisoformat(val.decode())

def convert_datetime(val):
    """Convert ISO 8601 datetime to datetime.datetime object."""
    return datetime.datetime.fromisoformat(val.decode())

def convert_timestamp(val):
    """Convert Unix timestamp to datetime.datetime object."""
    return datetime.datetime.fromtimestamp(int(val))