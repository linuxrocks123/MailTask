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

import threading
import imaplib
import smtplib
import os
import socket
import subprocess
import sys
import time

import mt_utils
from ontask_messages import *

##Should we mark messages read, as a normal client, or leave everything unread?
MARK_MESSAGES_READ=True

##Global lock
glock = threading.Lock()

##Account Info list
account_info = []

##Initialize account info dictionary
# Format of file: five lines per account
# 0. Username
# 1. Password
# 2. IMAP server
# 3. SMTP server
# 4. From Address String
def initialize_account_info():
    global server_password
    aifile = open("ACCOUNT_INFO")
    lines = aifile.readlines()
    lines = map(str.rstrip,lines)
    server_password = lines[0]
    for i in range(1,len(lines),5):
        account_info.append((lines[i],lines[i+1],lines[i+2],lines[i+3],lines[i+4]))

##IMAP Connection Holder
# List of sockets, index is account index
imap_conns = []

##Server notify socket dictionary
# cid -> socket
server_notify = {}

##This contains the definition for the client service thread.
# One of these is spawned to service every client socket.
class client_service_thread:
    def __init__(self, clientsock,cid):
        self.socket = clientsock
        self.cid = cid

    #Define some functions to handle different operations

    ##NODE-UPDATE command:
    # Handles updates, copies, moves, and deletes
    # Body format:
    # - First line: relative pathname of task from root (or "NEWMESSAGE")
    # - Second line: modification time of task (seconds since 1970)
    # - Third line: RFC822 body of node
    #Uploads have "NEWMESSAGE" filename.
    def node_update(self,body,flush_it=False):
        line0 = body[:body.find('\n')]
        line1 = body[(body.find('\n')+1):find_nth_substring('\n',2,body)]

        #Security check: can't go outside of file store dir
        if line0.find("..")!=-1 or line0[0]=='/':
            self.socket.write(OnTask_Message("FECC-OFF","Illegal filename passed").get_message_string())
            self.socket.close()
            raise IOError("Invalid data received on file/socket")

        #Parse first line
        account=line0[:line0.find('/')]
        stripped_name = line0[line0.rfind('/')+1:]
        imap_folder = line0[line0.find('/')+1:line0.rfind('/')]
        
        #Handle Task new message uploads: change name to current time
        if account=="Tasks" and stripped_name=="NEWMESSAGE":
            stripped_name=repr(int(time.time()))
            line0 = line0.replace("NEWMESSAGE",stripped_name,1)
            body = body.replace("NEWMESSAGE",stripped_name,1)

        #Need to handle special case names
        special_names = ("ADDRESSBOOK","READ_MESSAGES")
        
        #Write updated file to disk
        if not os.path.isfile(line0) or os.stat(line0)[8]<int(line1):
            #If we're an email message, we need to delete ourselves
            #Even if this is a "modification" ... that's implemented
            #as a delete+append
            if account!="Tasks" and stripped_name not in special_names:
                uid = int(stripped_name)
                conn = imap_conns[int(account)]
                if imap_folder=="Sent":
                    imap_folder = account_info[int(account)][5]
                conn.select(imap_folder)
                conn.uid("store",uid,"+FLAGS","(\\Deleted)")
                conn.expunge()

            #Empty body means we're deleting the file
            if find_nth_substring('\n',2,body)+1 == len(body):
                try:
                    os.remove(line0)
                except OSError: #in case file already deleted
                    pass
            else:
                filestore = open(line0,'w')
                rfc822 = body[find_nth_substring('\n',2,body)+1:]
                filestore.write(rfc822)
                filestore.close()

                #If this is an IMAP folder, must upload modified message
                if account!="Tasks" and stripped_name not in ("ADDRESSBOOK","READ_MESSAGES"):
                    conn = imap_conns[int(account)]
                    conn.append(imap_folder,"",time.time(),rfc822)
        else: #os.path.isfile(line0) and os.stat[8](line0)>=int(line1)
            self.socket.write(OnTask_Message("NAK","").get_message_string())
            self.socket.flush()
            return

        self.socket.write(OnTask_Message("ACK","").get_message_string())
        if flush_it: #for atomic_update; could probably do all the time but whatev
            self.socket.flush()

        #Iterate over sockets, tell everyone about the update
        #Clients will have to implement logic to delete modified emails
        for server_socket in server_notify.items():
            try:
                server_socket[1].write(OnTask_Message("NODE-UPDATE-NOTIFY",body).get_message_string())
                server_socket[1].flush()
                ack = OnTask_Message.message_from_socket(server_socket[1])
                if ack.cmd_id!="ACK":
                    server_socket[1].write(OnTask_Message("FECC-OFF","Protocol error").get_message_string())
                    server_socket[1].close()
                    raise IOError("Protocol error")
            except:
                del server_notify[server_socket[0]]

        #Done!
        return

    ##SEND-EMAIL command
    # Format:
    # - First line: ID of account
    # - Second line: list of email addresses separated by ','
    # - Subsequent lines: encoded email message
    def send_email(self,body):
        line0 = body[:body.find('\n')]
        accid = int(line0)
        line1 = body[(body.find('\n')+1):find_nth_substring('\n',2,body)]
        tosend = body[find_nth_substring('\n',2,body)+1:]

        #Create SMTP connection
        if accid not in range(len(account_info)):
            self.socket.write(OnTask_Message("FECC-OFF","Illegal account ID").get_message_string())
            self.socket.close()
            raise IOError("Invalid account ID")
        ainfo = account_info[accid]

        if ainfo[3].find("starttls:")!=0:
            server_name = ainfo[3]
            smtpconn = smtplib.SMTP_SSL(*mt_utils.server_args(server_name))
        else:
            server_name = ainfo[3].split(":")[1]
            smtpconn = smtplib.SMTP(*mt_utils.server_args(server_name))
            smtpconn.starttls()
        smtpconn.login(ainfo[0],ainfo[1])

        #Some SMTP servers will reject messages with long lines
        #As sites with this behavior are founded, they will be added here
        flattened = False
        if server_name in ["smtp.aol.com"]:
            flattened = True
            tosend = mt_utils.rfc2822_flatten(tosend)

        smtpconn.sendmail(ainfo[4],line1.split(','),tosend)

        #Upload email to sent folder
        imapconn = imap_conns[accid]
        while not imapconn:
            glock.release()
            time.sleep(10)
            print "No IMAP connection for sent message: sleeping"
            glock.acquire()
            imapconn = imap_conns[accid]

        #Some IMAP servers will reject messages that have long lines
        #Flatten message if it wasn't already flattened:
        if not flattened:
            tosend = mt_utils.rfc2822_flatten(tosend)

        #GMail doesn't like it when you upload your own copy of sent messsages.
        #As other sites with this behavior are found, they will be added here.
        if ainfo[2] not in ["imap.gmail.com"]:
            imapconn.append(ainfo[5],"",time.time(),tosend)

        self.socket.write(OnTask_Message("ACK","").get_message_string())

    ##ATOMIC-UPDATE command
    # Client request format:
    # - First line: path to file
    # Server reply format (NODE-BODY-FULL):
    # - Content: file data
    # Client reply format (NODE-UPDATE):
    # - Content: replacement file data
    def atomic_update(self,body):
        self.node_request(body)
        self.socket.flush()
        reply = OnTask_Message.message_from_socket(self.socket)
        if reply.cmd_id!="NODE-UPDATE":
            self.socket.write(OnTask_Message("FECC-OFF","Invalid atomic update coda.").get_message_string())
            raise IOError("Invalid atomic update coda.")
        self.node_update(reply.body,True)

    ##NODE-REQUEST command
    # Format:
    # - Single line: path to file
    def node_request(self,body):
        #Attempt at countering trivial information disclosure.  Primitive.
        if body.find("..")!=-1 or body[0]=='/' or body[0]=='.' or body=="ACCOUNT_INFO":
            self.socket.write(OnTask_Message("FECC-OFF","Illegal filename passed").get_message_string())
            self.socket.close()
            raise IOError("Invalid data received on file/socket")

        self.socket.write(OnTask_Message("NODE-BODY-FULL",(open(body)).read()).get_message_string())

    ##FOLDER-UPDATE-REQ command
    # Format:
    # - Single line: path to directory
    def folder_update_req(self,body):
        #Attempt at countering trivial information disclosure.  Primitive.
        if body.find("..")!=-1 or body[0]=='/':
            self.socket.write(OnTask_Message("FECC-OFF","Illegal filename passed").get_message_string())
            self.socket.close()
            raise IOError("Invalid data received on file/socket")

        #Build string to return:
        #List of files in directory, one per line
        #Newlines are separators -- no newline after final file
        files="\n".join(os.listdir(body))
        self.socket.write(OnTask_Message("FOLDER-UPDATE-NOTIFY",files).get_message_string())

    ##KEEPALIVE-NOTIFY command
    # Format:
    # - No body
    def keepalive_notify(self,body):
        self.socket.write(OnTask_Message("ACK","").get_message_string())

    ##Dictionary of supported client requests
    # Why?  Because Python doesn't have a switch statement
    clientreq = {"NODE-UPDATE" : node_update, "SEND-EMAIL" : send_email,
                 "ATOMIC-UPDATE" : atomic_update,
                 "NODE-REQUEST" : node_request,
                 "FOLDER-UPDATE-REQ" : folder_update_req,
                 "KEEPALIVE-NOTIFY" : keepalive_notify}

    ##We get here just after the thread is created
    def __call__(self):
        holding_lock = False
        abnormal_termination = False
        try:
            while True:
                msg = OnTask_Message.message_from_socket(self.socket)
                glock.acquire()
                holding_lock = True
                if msg.cmd_id not in client_service_thread.clientreq:
                    if msg.cmd_id!="SIGN-OFF":
                        abnormal_termination = True
                    break

                #This is like switch, but Python
                client_service_thread.clientreq[msg.cmd_id](self,msg.body)
                self.socket.flush()
                glock.release()
                holding_lock = False
        except Exception as e:
            print("Abnormal termination by thread "+repr(self.cid)+": "+repr(e))
            abnormal_termination = True
            
        if not holding_lock:
            glock.acquire()

        if self.cid in server_notify:
            if abnormal_termination:
                disconnect_msg = OnTask_Message("FECC-OFF","Invalid data received on companion file/socket")
            else:
                disconnect_msg = OnTask_Message("SIGN-OFF","Client-initiated sign off")

            try:
                server_notify[self.cid].write(disconnect_msg.get_message_string())
                server_notify[self.cid].close()
            except:
                print("Abnormal disconnection of server notify socket for thread "+repr(self.cid))
            
            del server_notify[self.cid]
        
        glock.release()

##Set of unclaimed CIDs
unclaimed_cids = set()

##Thread for handling creation of new client service threads
def client_thread_manager():
    cservsock = socket.socket()
    cservsock.bind(('',int(sys.argv[2])))
    cservsock.listen(5)
    while True:
        try:
            client_sock_ = cservsock.accept()[0]
            client_sock_.settimeout(600)
            client_sock = client_sock_.makefile()
        except:
            continue
        glock.acquire()
        try:
            id_data = OnTask_Message.message_from_socket(client_sock)
            given_cid = int(id_data.body)
            if id_data.cmd_id!="CID-INFO" or given_cid not in unclaimed_cids:
                print "WARNING: invalid connection to client thread manager."
                client_sock.write(OnTask_Message("FECC-OFF","Protocol error.").get_message_string())
                client_sock.close()
                continue

            #Still here?  Good.
            #Delete given CID from unclaimed_cids
            unclaimed_cids.remove(given_cid)

            #Send ACK to client
            client_sock.write(OnTask_Message("ACK","").get_message_string())
            client_sock.flush()
        except:
            continue
        finally:
            #Release lock
            glock.release()

        #Create socket manager thread.
        csock_runner = client_service_thread(client_sock,given_cid)
        threading.Thread(target=csock_runner).start()

## IMAP status array
REAUTHENTICATION_TIMEOUT = 600
imap_status = []

## IMAP handler
def imap_handler(username,password,server,status_index):
    #Dictionary containing current UIDNEXT
    uidnext_dict = { "INBOX" : 1, "Sent" : 1 }
    for entry in uidnext_dict.items():
        for cachedmessage in os.listdir(repr(status_index)+"/"+entry[0]):
            try:
                val = int(cachedmessage)+1
                if uidnext_dict[entry[0]] < val:
                    uidnext_dict[entry[0]]=val
            except ValueError:
                pass
    
    while True:
        time.sleep(30)
        print server+": acquiring lock"
        sys.stdout.flush()
        glock.acquire()
        try:
            if imap_status[status_index] + REAUTHENTICATION_TIMEOUT > time.time():
                for folder in ('INBOX', 'Sent'):
                    print server+"/"+folder+": Checking for new messages"
                    sys.stdout.flush()
                    #GMail IMAP is farked up and names its "Sent" folder "[Gmail]/Sent Mail"
                    real_folder = folder
                    if folder=="Sent":
                        real_folder=account_info[status_index][5]

                    server_uidnext = int(conn.status(real_folder,"(UIDNEXT)")[1][0].split("UIDNEXT ")[1].rstrip(" )"))
                    print server+"/"+folder+": UIDNEXT="+repr(server_uidnext)
                    sys.stdout.flush()
                    if server_uidnext==uidnext_dict[folder]:
                        continue

                    #Still here?  We've got some downloading to do.
                    conn.select(real_folder, readonly=(not MARK_MESSAGES_READ))
                    for uid in conn.uid("search",None,"ALL")[1][0].split():
                        if int(uid) < uidnext_dict[folder]:
                            continue

                        #Download message
                        downloaded_msg = conn.uid("fetch",uid,"(RFC822)")[1][0][1]

                        #Weird bug -- files where downloaded message is just like "2" or something
                        while len(downloaded_msg) < 10:
                            print server+": strange and invalid email received on IMAP socket.  Sleeping 30 seconds."
                            sys.stdout.flush()
                            glock.release()
                            time.sleep(30)
                            glock.acquire()
                            downloaded_msg = conn.uid("fetch",uid,"(RFC822)")[1][0][1]

                        #Write to file
                        open(repr(status_index)+"/"+folder+"/"+uid,'w').write(downloaded_msg)

                        #Notify clients
                        mtime = repr(int(time.time()))
                        for server_socket in server_notify.items():
                            try:
                                server_socket[1].write(OnTask_Message("NODE-UPDATE-NOTIFY",repr(status_index)+"/"+folder+"/"+uid+"\n"+mtime+"\n"+downloaded_msg).get_message_string())
                                server_socket[1].flush()
                                if OnTask_Message.message_from_socket(server_socket[1]).cmd_id!="ACK":
                                    raise IOError("Protocol error.")
                            except:
                                del server_notify[server_socket[0]]

                    #Update UIDNEXT dict
                    uidnext_dict[folder]=server_uidnext
            else:
                #Login
                print server+": logging in"
                sys.stdout.flush()
                conn = imaplib.IMAP4_SSL(*mt_utils.server_args(server))
                imap_conns[status_index] = conn
                conn.login(username,password)

                #Get folders: INBOX, Sent
                for folder in ('INBOX','Sent'):
                    #GMail IMAP is farked up and names its "Sent" folder "[Gmail]/Sent Mail"
                    #There are other instances of stupidity on other servers.
                    real_folder = folder
                    if real_folder=="Sent" and len(account_info[status_index]) >= 6:
                        real_folder = account_info[status_index][5]
                    elif real_folder=="Sent":
                        if server=="imap.gmail.com" and folder=="Sent":
                            real_folder="[Gmail]/Sent Mail"
                        elif conn.select(real_folder)[0]!="NO":
                            real_folder="Sent"
                        elif conn.select("Sent Items")[0]!="NO":
                            real_folder="Sent Items"
                        else:
                            print server+": couldn't find Sent folder; things probably won't work."
                        account_info[status_index]=account_info[status_index]+(real_folder,)
                    
                    conn.select(real_folder)
                    validity = open(repr(status_index)+"/"+folder+"/UIDVALIDITY").read().rstrip()

                    #Do we need to invalidate folder?
                    if validity!=conn.status(real_folder,"(UIDVALIDITY)")[1][0].split("UIDVALIDITY ")[1].rstrip(" )"): #yup
                        print "Critical situation: Invalid UIDVALIDITY"
                        print "old validity: "+validity
                        print "new validity: "+conn.status(real_folder,"(UIDVALIDITY)")[1][0].split("UIDVALIDITY ")[1].rstrip(" )")
                        print "Sleeping 15 seconds so you can Ctrl-C if you want."
                        sys.stdout.flush()
                        time.sleep(15)

                        #Notify everyone of situation
                        for server_socket in server_notify.items():
                            try:
                                server_socket[1].write(OnTask_Message("FOLDER-INVALIDATE-NOTIFY",repr(status_index)+"/"+folder).get_message_string())
                                if OnTask_Message.message_from_socket(server_socket[1]).cmd_id!="ACK":
                                    raise IOError("Protocol error.")
                            except:
                                del server_notify[server_socket[0]]

                        #Delete and redownload entire folder

                        #Delete everything
                        for f in os.listdir(repr(status_index)+"/"+folder):
                            if f!="UIDVALIDITY":
                                os.remove(repr(status_index)+"/"+folder+"/"+f)

                        #Rewrite UIDVALIDITY file
                        open(repr(status_index)+"/"+folder+"/UIDVALIDITY",'w').write(conn.status(real_folder,"(UIDVALIDITY)")[1][0].split("UIDVALIDITY ")[1].rstrip(" )")+"\n")

                        #Everything will be redownloaded next iteration
                        uidnext_dict[folder]=0
                    else: #set uidnext_dict[folder] to highest downloaded index
                        for f in os.listdir(repr(status_index)+"/"+folder):
                            try:
                                nextindex = int(f)+1
                                if nextindex > uidnext_dict[folder]:
                                    uidnext_dict[folder] = nextindex
                            except ValueError:
                                pass

                #If we got all the way here, we successfully connected.
                imap_status[status_index]=time.time()
        except Exception as e:
            print server+" exception: "+repr(e)
            sys.stdout.flush()
            imap_status[status_index]=0
        finally:
            print server+": releasing lock"
            sys.stdout.flush()
            glock.release()

##KEEPALIVE-NOTIFY thread for server sockets.
# Look at me still talking when there's Science to do...
def doing_science():
    while True:
        time.sleep(60)
        glock.acquire()
        for server_socket in server_notify.items():
            try:
                server_socket[1].write(OnTask_Message("KEEPALIVE-NOTIFY","").get_message_string())
                server_socket[1].flush()
                ack = OnTask_Message.message_from_socket(server_socket[1])
                if ack.cmd_id!="ACK":
                    server_socket[1].write(OnTask_Message("FECC-OFF","Protocol error").get_message_string())
                    server_socket[1].close()
                    raise IOError("Protocol error")
            except:
                del server_notify[server_socket[0]]
        glock.release()

##Main method for primary thread
def main():
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
    
    #Read ACCOUNT_INFO, which stores info on how to log into accounts
    initialize_account_info()

    #Socket Timeout Setting
    socket.setdefaulttimeout(300)

    #Create one thread per IMAP connection to handle updates
    for acct in range(len(account_info)):
        imap_conns.append(None)
        imap_status.append(0)
        threading.Thread(target=imap_handler,args=account_info[acct][:3]+(acct,)).start()

    #Start thread to handle creation of new client service threads.
    cservice = threading.Thread(target=client_thread_manager).start()

    #Start thread to handle keepalive-notify on server socket
    stillalive = threading.Thread(target=doing_science).start()

    #Main thread:
    # - Loop waiting for new clients to connect.
    # - When one does:
    #   - Generate CID for client
    #   - Add server socket to server_notify
    #   - Add CID to "unclaimed CIDs"
    #   - Send client its CID.
    server = socket.socket()
    server.bind(('',int(sys.argv[1])))
    server.listen(5)
    i=0
    glock.acquire()
    glock_held=True
    #FIXME: handle exceptions here
    while True:
        try:
            #Release lock
            if glock_held:
                glock.release()
                glock_held=False

            #Accept new connection to server
            conn_socket_ = server.accept()[0]
            conn_socket_.settimeout(600)
            conn_socket = conn_socket_.makefile()

            #Take lock
            glock.acquire()
            glock_held=True

            #Handshake with client

            #Greetings, Earthling
            conn_socket.write(OnTask_Message("HELLO","").get_message_string())
            conn_socket.flush()

            #Read authentication info
            authinfo = OnTask_Message.message_from_socket(conn_socket)

            #Authentication handshake with client

            #Process authentication
            if authinfo.cmd_id!="AUTHINFO":
                conn_socket.write(OnTask_Message("FECC-OFF","Authentication required.").get_message_string())
                conn_socket.close()
                continue

            #Now check password
            if authinfo.body!=server_password:
                conn_socket.write(OnTask_Message("FECC-OFF","Password incorrect.").get_message_string())
                conn_socket.close()
                print "WARNING: client provided incorrect password"
                continue

            #If we're still here, authentication successful.
            conn_socket.write(OnTask_Message("ACK","").get_message_string())
            conn_socket.flush()

            #Client should now request CID
            req = OnTask_Message.message_from_socket(conn_socket)
            if req.cmd_id!="CID-REQUEST":
                conn_socket.write(OnTask_Message("FECC-OFF","Password incorrect.").get_message_string())
                conn_socket.close()
                continue

            #Generate CID for client
            cid=i
            while cid in unclaimed_cids or cid in server_notify:
                i+=1
                i%=1000
                cid=i

            #Add server-initiated communication socket to server_notify
            server_notify[cid]=conn_socket

            #Add cid to unclaimed_cids
            unclaimed_cids.add(cid)

            #Notify client of CID
            conn_socket.write(OnTask_Message("CID-NOTIFY",repr(cid)).get_message_string())
            conn_socket.flush()

            #Take the ACK
            ack = OnTask_Message.message_from_socket(conn_socket)

            ##Local function to push updates to client
            def push_updates_for_folder(folder):
                for f in os.listdir(folder):
                    fname = folder+"/"+f
                    mtime = os.stat(fname)[8]
                    if mtime > timestamp:
                        conn_socket.write(OnTask_Message("NODE-UPDATE-NOTIFY",fname+"\n"+repr(mtime)+"\n"+open(fname).read()).get_message_string())
                        conn_socket.flush()
                        if OnTask_Message.message_from_socket(conn_socket).cmd_id!="ACK":
                            raise IOError("Protocol Error.")
            
            #If the client passed in an update timestamp, deal with it here.
            if req.body!="":
                timestamp = int(req.body)
                for i in range(len(account_info)):
                    for folder in ('INBOX','Sent'):
                        push_updates_for_folder(repr(i)+"/"+folder)
                push_updates_for_folder("Tasks")
        except:
            pass

#Standard "are we really running as a script" check
if __name__=="__main__":
    main()
