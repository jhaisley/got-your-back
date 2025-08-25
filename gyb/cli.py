#!/usr/bin/env python3
#
# Got Your Back - CLI Argument Parsing
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

import argparse
from .utils import getProgPath

def SetupOptionParser(argv):
  tls_choices = ['TLSv1_2', 'TLSv1_3']
  tls_min_default = tls_choices[-1]
  parser = argparse.ArgumentParser(add_help=False)
  parser.add_argument('--email',
    dest='email',
    help='Full email address of user or group to act against')
  action_choices = ['backup','backup-chat', 'restore', 'restore-group', 'restore-mbox',
    'count', 'purge', 'purge-labels', 'print-labels', 'estimate', 'quota', 'reindex', 'revoke',
    'split-mbox', 'create-project', 'delete-projects', 'check-service-account', 'create-label']
  parser.add_argument('--action',
    choices=action_choices,
    dest='action',
    default='backup',
    help='Action to perform. Default is backup.')
  parser.add_argument('--search',
    dest='gmail_search',
    default='-is:chat',
    help='Optional: On backup, estimate, count and purge, Gmail search to \
scope operation against')
  parser.add_argument('--local-folder',
    dest='local_folder',
    help='Optional: Output folder for backed up email. Default is \
GYB-GMail-Backup-<email>',
    default='XXXuse-email-addressXXX')
  parser.add_argument('--label-restored',
    dest='label_restored',
    action='append',
    help='Optional: Used on restore only. \
Apply this label to restored messages. Default is GYB-Restored.')
  parser.add_argument('--label-prefix',
    dest='label_prefix',
    action='append',
    help='Optional: Used on restore only. \
Add this prefix to all restored labels (except for Unread label).')
  parser.add_argument('--strip-labels',
    dest='strip_labels',
    action='store_true',
    help='Optional: Used on restore only. \
Strip existing labels from messages except for those specified with \
--label-restored.')
  parser.add_argument('--vault',
    dest='vault',
    action='store_true',
    help='Optional: Used on restore only. \
Restore to Google Vault.')
  parser.add_argument('--service-account',
    dest='service_account',
    help='Path to service account file.')
  parser.add_argument('--use-admin',
    dest='use_admin',
    help='Optional: Use this admin user\'s credentials to backup/restore, \
requires service account.')
  parser.add_argument('--batch-size',
    dest='batch_size',
    type=int,
    default=0,
    help='Optional: Sets the number of messages to batch \
together when restoring (default is 10 for restore and 100 for backup).')
  parser.add_argument('--noresume',
    dest='noresume',
    action='store_true',
    help='Optional: Start restore from beginning. Default is to resume where \
last restore left off.')
  parser.add_argument('--fast-incremental',
    dest='refresh',
    action='store_false',
    default=True,
    help='Optional: Skip refreshing labels for existing message on incremental \
backups. WARNING: do not use if message labels have changed.')
  parser.add_argument('--debug',
    dest='debug',
    action='store_true',
    help='Turn on verbose debugging')
  parser.add_argument('--memory-limit',
    dest='memory_limit',
    type=int,
    help='Limit used memory to given amount (MB). Default is to only \
limit memory when backing up chats.')
  parser.add_argument('--spam-trash',
    dest='spamtrash',
    action='store_true',
    help='Include Spam and Trash folders in backup, estimate and count \
operations. \
This is always enabled for purge operations.')
  parser.add_argument('--version',
    action='store_true',
    dest='version',
    help='print GYB version and exit')
  parser.add_argument('--cleanup',
    action='store_true',
    help='Try to fix common email problems during restore. \
WARNING: This is experimental and may corrupt messages.')
  if hasattr(ssl, 'TLSVersion'):
    parser.add_argument('--tls-min-version',
      dest='tls_min_version',
      default=tls_min_default,
      choices=tls_choices,
      help='Set minimum version of TLS HTTPS connections require. Default is TLSv1_3')
    parser.add_argument('--tls-max-version',
      dest='tls_max_version',
      default=None,
      choices=tls_choices,
      help='Set maximum version of TLS HTTPS connections use. Default is no max')
  parser.add_argument('--ca-file',
    dest='ca_file',
    default=None,
    help='specify a certificate authority to use for validating HTTPS hosts.')
  parser.add_argument('--extra-reserved-labels',
    dest='extra_reserved_labels',
    nargs='+',
    help='extra labels that should be treated as reserved.')
  parser.add_argument('--extra-system-labels',
    dest='extra_system_labels',
    nargs='+',
    help='extra labels that should be treated as system labels.')
  parser.add_argument('--config-folder',
    dest='config_folder',
    help='Optional: Alternate folder to store config and credentials',
    default=getProgPath())
  parser.add_argument('--shortversion',
    action='store_true',
    dest='shortversion',
    help='Just print version and quit')
  parser.add_argument('--help',
    action='help',
    help='Display this message.')
  return parser.parse_args(argv)

import ssl