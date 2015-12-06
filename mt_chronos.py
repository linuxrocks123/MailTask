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

#Note: This library should have no dependencies on other parts of MailTask.
#This is to allow Chronos-Ananke messages to be generated and parsed
#from external software.

#Just to be clear, the license to this file is still GPLv3, though.

##Given a string representing the body of an email message,
# return a four-tuple with the information necessary to create
# a calendar event from it using the MT-CHRONOS-ANANKE format.
# The format of the return tuple:
# ("summary","description",epoch-starttime,epoch-endtime)
def extract_calendar_event(email_body):
    inside_calendar=False
    lines = email_body.splitlines()
    i=0
    while i<len(lines):
        if lines[i].find("MT-CHRONOS-ANANKE")!=-1:
            try:
                to_return=(lines[i+1],lines[i+2],int(lines[i+3]),int(lines[i+4]))
                return to_return
            except:
                pass
            
        i+=1
    return None

##Generate the MT-CHRONOS-ANANKE event string to put in the body of an email message
def gen_calendar_event(summary,description,starttime,endtime):
    to_return="MT-CHRONOS-ANANKE\n"
    to_return+=summary+"\n"
    to_return+=description+"\n"
    to_return+=repr(starttime)+"\n"
    to_return+=repr(endtime)+"\n"
    return to_return
