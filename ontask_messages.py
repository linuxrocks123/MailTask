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

##Simple function to find nth occurrence of substring
# (WHY is this not BUILT IN????)
def find_nth_substring(needle,occurrence,haystack):
    i=-1
    for _ in range(occurrence):
        i=i+1
        i=haystack.find(needle,i)
        if i==-1:
            return -1
    return i

class OnTask_Message:
    def __init__(self, header, body):
        self.cmd_id = header
        self.body = body
    
    def get_message_string(self):
        to_return = self.cmd_id+"\n~BEGINBODY\n"
        wrapped_body = self.body.replace("\\","\\\\").replace("\n", "\\n")
        to_return += wrapped_body+"\n~ENDBODY\n"
        return to_return

    @staticmethod
    def message_from_socket(socket):
        cmd_id = socket.readline().rstrip()
        beginbody = socket.readline()
        if beginbody!="~BEGINBODY\n":
            socket.write(OnTask_Message("FECC-OFF","Invalid message format: No ~BEGINBODY").get_message_string())
            socket.close()
            raise IOError("Invalid data received on file/socket")
        body = socket.readline().rstrip()
        endbody = socket.readline()
        if endbody!="~ENDBODY\n":
            socket.write(OnTask_Message("FECC-OFF","Invalid message format: No ~ENDBODY").get_message_string())
            socket.close()
            raise IOError("Invalid data received on file/socket")
        body = body.replace("\\n","\n").replace("\\\\","\\")
        return OnTask_Message(cmd_id,body)
