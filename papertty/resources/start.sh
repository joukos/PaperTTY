#!/bin/sh

## Put your options here - the service unit will run this script, so that
## you don't need to 'daemon-reload' every time you want to change settings.
##
## It's a good idea to allow only root to write to this file: 
##
## sudo chown root:root start.sh; sudo chmod 700 start.sh
##

VENV="/home/pi/.virtualenvs/papertty/bin/python3"
${VENV} papertty --driver epd2in13 terminal --autofit
