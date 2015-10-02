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

import client

import cPickle
import os
import sys

#Name of program and intro text
print "MailTask Alpha: The Email Manager"
print "(c) 2015 by Patrick Simmons"
print
print "This program is free software: you can redistribute it and/or modify"
print "it under the terms of the GNU General Public License as published by"
print "the Free Software Foundation, either version 3 of the License, or"
print "(at your option) any later version."

print "This program is distributed in the hope that it will be useful,"
print "but WITHOUT ANY WARRANTY; without even the implied warranty of"
print "MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the"
print "GNU General Public License for more details."
print
print "Libraries used:"
print "html2text (c) 2012 Aaron Swartz (GPLv3)"
print "requests_structures.py (c) The Requests Project (original Apachev2; any modifications GPLv3)"
print
print "This program is dedicated to the memory of Aaron Swartz."
    
client.c_state = client.ClientState() #I no longer think this is needed, but just in case.
client.cachedir = os.path.abspath(sys.argv[1])
client.initialize_account_info()
client.password = open(os.path.join(client.cachedir,"settings")).readline().rstrip()

client.ClientNetSync.connmanager = lambda(self): None
nsync = client.ClientNetSync()

#Local function to add all files in a folder to cache
def folder_cache_add(folder):
    nsync.cache[folder]=[]
    for fname in os.listdir(os.path.join(client.cachedir,folder)):
        nsync.add_to_cache(folder+"/"+fname,open(os.path.join(client.cachedir,folder+"/"+fname)).read(),False)

#If we have a pickle, use it; otherwise, read in all emails and parse them (slow)
if os.path.isfile(client.cachedir+"/client.pickle"):
    nsync.cache = cPickle.load(open(client.cachedir+"/client.pickle","rb"))
else:
    #Add all account folders to cache
    for x in range(len(client.account_info)):
        folder_cache_add(repr(x)+"/INBOX")
        folder_cache_add(repr(x)+"/Sent")
    folder_cache_add("Tasks")

cPickle.dump(nsync.cache,open(client.cachedir+"/client.pickle",'w'),cPickle.HIGHEST_PROTOCOL)
