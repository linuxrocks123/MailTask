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

from ontask_messages import OnTask_Message
from select import select
import socket
import sys
import time

body = sys.stdin.read()
server = sys.argv[1]
server_port = int(sys.argv[2])
csock_port = int(sys.argv[3])
password = sys.argv[4]
uidpath = sys.argv[5]

#Connect to server, set up client sockets

#Server socket
smessage_conn = socket.socket()
smessage_conn.connect((sys.argv[1],int(sys.argv[2])))
smessage_conn_socket = smessage_conn
smessage_conn = smessage_conn.makefile()

#"HELLO" from server
hello = OnTask_Message.message_from_socket(smessage_conn)
if hello.cmd_id!="HELLO":
    smessage_conn.write(OnTask_Message("FECC-OFF","Protocol error").get_message_string())
    smessage_conn.close()
    print "ERROR: Protocol Error"
    sys.exit(1)

#Send password (yes, in the clear)
smessage_conn.write(OnTask_Message("AUTHINFO",password).get_message_string())
smessage_conn.flush()

#"ACK" from server
ack = OnTask_Message.message_from_socket(smessage_conn)
if ack.cmd_id!="ACK":
    smessage_conn.write(OnTask_Message("FECC-OFF","Protocol error").get_message_string())
    smessage_conn.close()
    print "ERROR: Protocol Error"
    sys.exit(1)

#CID-REQUEST is next
smessage_conn.write(OnTask_Message("CID-REQUEST","").get_message_string())
smessage_conn.flush()

#"CID-NOTIFY" from server
cid_message = OnTask_Message.message_from_socket(smessage_conn)
if cid_message.cmd_id!="CID-NOTIFY":
    smessage_conn.write(OnTask_Message("FECC-OFF","Protocol error").get_message_string())
    smessage_conn.close()
    print "ERROR: Protocol Error"
    sys.exit(1)

#Now we have our CID
cid = cid_message.body

#ACK to the server
smessage_conn.write(OnTask_Message("ACK","").get_message_string())
smessage_conn.flush()

#Open connection to client socket
cmessage_conn = socket.socket()
cmessage_conn.connect((sys.argv[1],int(sys.argv[3])))
cmessage_conn_socket = cmessage_conn
cmessage_conn = cmessage_conn.makefile()

#Send CID, so server knows who we are
cmessage_conn.write(OnTask_Message("CID-INFO",cid).get_message_string())
cmessage_conn.flush()


#Reply must be done using queue: server may block otherwise
#So, now we loop trying to send our node_update message
#while ignoring all of the server's notifications
stage = 0
while True:
    #select system call: I finally get to use this!
    retvals = select((smessage_conn_socket,cmessage_conn_socket),(cmessage_conn_socket,),(),0)

    if smessage_conn_socket in retvals[0]:
        smessage = OnTask_Message.message_from_socket(smessage_conn)
        if smessage.cmd_id!="FECC-OFF":
            smessage_conn.write(OnTask_Message("ACK","").get_message_string())
            smessage_conn.flush()
        else:
            print "ERROR: Received FECC-OFF"
            sys.exit(1)
    if stage==0 and cmessage_conn_socket in retvals[0]:
        ack = OnTask_Message.message_from_socket(cmessage_conn)
        if ack.cmd_id!="ACK":
            print "ERROR: Unexpected Reply"
            sys.exit(1)
        stage=1
    elif stage==1 and cmessage_conn_socket in retvals[1]:
        cmessage_conn.write(OnTask_Message("NODE-UPDATE",uidpath+"\n"+repr(int(time.time()))+"\n"+body).get_message_string())
        cmessage_conn.flush()
        stage=2
    elif stage==2 and cmessage_conn_socket in retvals[0]:
        reply = OnTask_Message.message_from_socket(cmessage_conn)
        if reply.cmd_id=="NAK":
            print "WARNING: Server preferred conflicting update"
            sys.exit(2)
        elif reply.cmd_id!="ACK":
            print "ERROR: Unexpected Reply"
            sys.exit(1)
        else:
            cmessage_conn.write(OnTask_Message("SIGN-OFF","").get_message_string())
            cmessage_conn.flush()
            sys.exit(0)
