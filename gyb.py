#!/usr/bin/env python3
#
# Got Your Back - Main Script (Compatibility Layer)
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
Got Your Back (GYB) - Gmail Backup Tool

This is a compatibility layer that imports the modular version of GYB
and provides the same interface as the original gyb.py script.

The functionality has been broken down into logical modules:
- gyb.main: Main entry point and coordination
- gyb.cli: Command line argument parsing
- gyb.auth: Authentication and OAuth handling
- gyb.google_api: Google API interactions
- gyb.database: SQLite database operations
- gyb.actions: Backup and restore actions
- gyb.utils: Utility functions
"""

import sys

if __name__ == "__main__":
    # Import and run the modular version
    from gyb.main import main

    main(sys.argv[1:])
else:
    # When imported as a module, expose the library interface
    # trunk-ignore(ruff/F403)
    from gyb import *
