#!/usr/bin/env python3
#
# Got Your Back - Backup/Restore Action Functions
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
import email
import base64
import json
from io import BytesIO

import googleapiclient
from googleapiclient.http import MediaIoBaseUpload

from .utils import rewrite_line, humansize, bytes_to_larger
from .google_api import callGAPI

# Global label mappings
allLabelIds = dict()
allLabels = dict()

def labelIdsToLabels(labelIds):
  global allLabels
  from . import gmail
  
  labels = []
  if allLabels == {}:
    results = callGAPI(gmail.users().labels(), 'list', userId='me', fields='labels(id,name)')
    for a_label in results['labels']:
      allLabels[a_label['id']] = a_label['name']
  for labelId in labelIds:
    if labelId in allLabels:
      labels.append(allLabels[labelId])
    else:
      labels.append(labelId)
  return labels

def createLabel(label_name):
  from . import gmail
  
  try:
    results = callGAPI(gmail.users().labels(), 'create', userId='me',
      body={'name': label_name, 'messageListVisibility': 'show',
            'labelListVisibility': 'labelShow'})
    return results['id']
  except googleapiclient.errors.HttpError as e:
    if json.loads(e.content.decode())['error']['code'] == 409:
      results = callGAPI(gmail.users().labels(), 'list', userId='me',
        fields='labels(id,name)')
      for a_label in results['labels']:
        if a_label['name'].lower() == label_name.lower():
          return a_label['id']
    raise e

def labelsToLabelIds(labels):
  global allLabelIds
  from . import gmail, reserved_labels, system_labels
  
  labelIds = []
  if allLabelIds == {}:
    results = callGAPI(gmail.users().labels(), 'list', userId='me', fields='labels(id,name)')
    for a_label in results['labels']:
      allLabelIds[a_label['name']] = a_label['id']
  for label in labels:
    if label in allLabelIds:
      labelIds.append(allLabelIds[label])
    elif label in system_labels:
      labelIds.append(label)
    elif label.upper() in system_labels:
      labelIds.append(label.upper())
    elif label.lower() in reserved_labels:
      if label.lower() == 'chat':
        labelIds.append('CHAT')
      elif label.lower() == 'chats':
        labelIds.append('CHAT')
      elif label.lower() in ['draft', 'drafts']:
        labelIds.append('DRAFT')
      else:
        labelIds.append(label.upper())
    else:
      # Need to create the label
      print(f'  Need to create label "{label}"...')
      new_label_id = createLabel(label)
      labelIds.append(new_label_id)
      allLabelIds[label] = new_label_id
  return labelIds

def refresh_message(request_id, response, exception):
  global sqlcur, sqlconn
  
  if exception is not None:
    print("ERROR: %s" % exception)
    return
  message_num = response['id']
  labels = response.get('labelIds', [])
  sqlcur.execute('DELETE FROM labels WHERE message_num = ?', (message_num,))
  for label in labels:
    try:
      sqlcur.execute('INSERT INTO labels (message_num, label) VALUES (?, ?)', (message_num, label))
    except sqlite3.IntegrityError:
      pass

def restored_message(request_id, response, exception):
  global sqlcur, sqlconn
  
  if exception is not None:
    print("ERROR: %s" % exception)
    return
  try:
    sqlcur.execute('INSERT INTO restored_messages (message_num) VALUES (?)', (request_id,))
  except sqlite3.IntegrityError:
    pass

def purged_message(request_id, response, exception):
  print("ERROR: %s" % exception)

def backup_chat(request_id, response, exception):
  import calendar
  global sqlcur, sqlconn, backup_count
  from . import options
  
  if exception is not None:
    print("\nERROR: %s" % exception)
    return
  if response is None:
    return
  message_num = response['id']
  labels = response.get('labelIds', [])
  # Save chat thread
  message_date = int(response['internalDate']) / 1000
  backup_count += 1
  payload = response['payload']
  parts = payload.get('parts', [payload])
  full_message = ''
  for part in parts:
    if part.get('body', {}).get('data'):
      data = part['body']['data']
      try:
        full_message += base64.urlsafe_b64decode(data).decode('utf-8')
      except (UnicodeDecodeError, ValueError):
        pass
  filename = 'chat-%s.json' % message_num
  full_path = os.path.join(options.local_folder, filename)
  chat_data = {
    'id': message_num,
    'threadId': response.get('threadId'),
    'timestamp': response['internalDate'],
    'content': full_message,
    'labels': labels
  }
  with open(full_path, 'w', encoding='utf-8') as f:
    json.dump(chat_data, f, ensure_ascii=False, indent=2)
  try:
    sqlcur.execute('''INSERT INTO messages (message_num, message_filename,
                      message_internaldate) VALUES (?, ?, ?)''',
                   (message_num, filename, message_date))
    sqlcur.execute('DELETE FROM labels WHERE message_num = ?', (message_num,))
    for label in labels:
      sqlcur.execute('INSERT INTO labels (message_num, label) VALUES (?, ?)', (message_num, label))
  except sqlite3.IntegrityError:
    pass

def backup_message(request_id, response, exception):
  import calendar
  global sqlcur, sqlconn, backup_count
  from . import options
  
  if exception is not None:
    print("\nERROR: %s" % exception)
    return
  if response is None:
    return
  message_num = response['id']
  labels = response.get('labelIds', [])
  message_date = int(response['internalDate']) / 1000
  backup_count += 1
  if request_id == message_num:
    filename = '%s.eml' % message_num
  else:
    filename = request_id
  full_filename = os.path.join(options.local_folder, filename)
  raw_message = base64.urlsafe_b64decode(response['raw'])
  with open(full_filename, 'wb') as f:
    f.write(raw_message)
  try:
    sqlcur.execute('''INSERT INTO messages (message_num, message_filename,
                      message_internaldate) VALUES (?, ?, ?)''',
                   (message_num, filename, message_date))
    sqlcur.execute('DELETE FROM labels WHERE message_num = ?', (message_num,))
    for label in labels:
      sqlcur.execute('INSERT INTO labels (message_num, label) VALUES (?, ?)', (message_num, label))
  except sqlite3.IntegrityError:
    pass

def getSizeOfMessages(messages, gmail):
  from . import options
  
  if not messages:
    return {}
  batch_request = gmail.new_batch_http_request()
  message_sizes = {}
  for message in messages:
    batch_request.add(gmail.users().messages().get(userId='me', id=message, format='minimal', fields='id,sizeEstimate'))
  def handle_message_size(request_id, response, exception):
    if exception is not None:
      return
    message_sizes[response['id']] = response['sizeEstimate']
  batch_request.callbacks = [handle_message_size] * len(messages)
  batch_request.execute()
  return message_sizes

def restore_msg_to_group(gmig, full_message, message_num, sqlconn):
  from . import options
  
  rewrite_line("Restoring message %s" % message_num)
  try:
    fstr = BytesIO(full_message)
    media = MediaIoBaseUpload(fstr,
                              mimetype='message/rfc822',
                              chunksize=-1,
                              resumable=True)
    result = callGAPI(gmig.archive(), 'insert',
      groupId=options.email, media_body=media)
    if 'responseCode' in result and result['responseCode'] == 'SUCCESS':
      sqlcur = sqlconn.cursor()
      sqlcur.execute('INSERT INTO restored_messages (message_num) VALUES (?)', (message_num,))
      sqlconn.commit()
  except googleapiclient.errors.HttpError as e:
    print("ERROR: %s" % e)

import sqlite3