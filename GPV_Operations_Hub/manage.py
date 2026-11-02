#!/usr/bin/env python
"""Django command-line entry point for GPV Operations Hub."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gpvhub.settings")
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        os.environ.setdefault("GPV_ENV", "test")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
