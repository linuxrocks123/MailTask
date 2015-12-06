#! /usr/bin/env python

# MailTask Alpha: The Email Manager
# Copyright (C) 2015  Patrick Simmons

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import httplib2
import os

from apiclient import discovery
import oauth2client
from oauth2client import client
from oauth2client import tools

import datetime
import argparse

flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args(["--noauth_local_webserver"])
SCOPES = 'https://www.googleapis.com/auth/calendar'
CLIENT_SECRET_FILE = 'api_key_do_not_upload.json'
APPLICATION_NAME = 'MailTask Calendar Synchronization Module'

def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    credential_path = 'client_secret_do_not_upload.json'

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        credentials = tools.run_flow(flow, store, flags)
        print('Storing credentials to ' + credential_path)
    return credentials

def initialize():
    global credentials
    global http
    global service
    global events

    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('calendar', 'v3', http=http)
    events = service.events()

##Insert a calendar event from a tuple
def insert_gcal_event(caltuple):
    events.insert(calendarId="primary",body={"summary" : caltuple[0], "start" : {"dateTime" : datetime.datetime.utcfromtimestamp(caltuple[2]).isoformat()+'Z'},"end" : {"dateTime" : datetime.datetime.utcfromtimestamp(caltuple[3]).isoformat()+'Z'},"description" : caltuple[1]}).execute()
