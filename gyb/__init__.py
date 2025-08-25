#!/usr/bin/env python3
#
# Got Your Back - Library Interface
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

"""
Got Your Back (GYB) is a command line tool which allows users to
backup and restore their Gmail.

For more information, see https://git.io/gyb/
"""

# Import key components for library use
from .utils import getGYBVersion, __version__, __author__, __email__, __license__, __website__
from .main import main
from .cli import SetupOptionParser
from .auth import getValidOauth2TxtCredentials, requestOAuthAccess
from .google_api import buildGAPIObject, buildGAPIServiceObject, callGAPI, callGAPIpages
from .database import initializeDB, get_db_settings, check_db_settings
from .actions import backup_message, backup_chat, restore_msg_to_group

# Global variables that other modules may need to access
options = None
gmail = None
sqlconn = None
sqlcur = None

# Reserved and system labels
reserved_labels = ['inbox', 'spam', 'trash', 'unread', 'starred', 'important',
  'sent', 'draft', 'chat', 'chats', 'migrated', 'todo', 'todos', 'buzz',
  'bin', 'allmail', 'drafts', 'archive', 'archived', 'muted']
system_labels = ['INBOX', 'SPAM', 'TRASH', 'UNREAD', 'STARRED', 'IMPORTANT',
                 'SENT', 'DRAFT', 'CATEGORY_PERSONAL', 'CATEGORY_SOCIAL',
                 'CATEGORY_PROMOTIONS', 'CATEGORY_UPDATES', 'CATEGORY_FORUMS']

# Export commonly used functions
__all__ = [
    'main',
    'getGYBVersion',
    'SetupOptionParser',
    'getValidOauth2TxtCredentials',
    'requestOAuthAccess', 
    'buildGAPIObject',
    'buildGAPIServiceObject',
    'callGAPI',
    'callGAPIpages',
    'initializeDB',
    'get_db_settings',
    'check_db_settings',
    'backup_message',
    'backup_chat',
    'restore_msg_to_group',
    '__version__',
    '__author__',
    '__email__',
    '__license__',
    '__website__'
]