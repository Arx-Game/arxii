#!/bin/bash
# shell_scripts/install.sh

# Install Evennia with its dependencies
pip install evennia==3.1.1

# Install the rest of the requirements, overriding with Django 5.1.3
pip install -r ../requirements.txt
