# shell_scripts/install.ps1

# Install Evennia with its dependencies
pip install evennia==3.1.1

# Install the rest of the requirements, overriding with Django 5.1.3
pip install -r ..\requirements.txt

# Note, if you get a permission error, may need to run 'Set-ExecutionPolicy RemoteSigned -Scope Process'
