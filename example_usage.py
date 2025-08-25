#!/usr/bin/env python3
"""
Example usage of GYB as a library.

This demonstrates how to import and use GYB functionality
programmatically in other Python projects.
"""

import gyb

def main():
    """Example of using GYB as a library."""
    
    # Display version information
    print("GYB Library Example")
    print("=" * 50)
    print(f"Version: {gyb.__version__}")
    print(f"Author: {gyb.__author__}")
    print(f"Email: {gyb.__email__}")
    print()
    
    # List some available functions
    print("Some available functions:")
    functions = [
        'buildGAPIObject', 'buildGAPIServiceObject', 
        'backup_message', 'restore_msg_to_group',
        'getSizeOfMessages', 'message_is_backed_up'
    ]
    
    for func_name in functions:
        if hasattr(gyb, func_name):
            func = getattr(gyb, func_name)
            print(f"  {func_name}: {func.__doc__.split('.')[0] if func.__doc__ else 'Available'}")
    
    print()
    print("To use the original command-line functionality,")
    print("see the original main function in main.py.bak")

if __name__ == '__main__':
    main()