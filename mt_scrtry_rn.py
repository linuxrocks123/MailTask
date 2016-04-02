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
import email
import email.message
import email.parser
import email.utils
from ontask_messages import *
import os
import mt_chronos
import mt_utils
from select import select
import shutil
import sys
import time

try:
    import mt_gcal_sync
    do_gcal = True
    print "Google Calendar extension enabled"
except ImportError:
    do_gcal = False
    print "Google Calendar extension disabled"

##l_timedep_tasks: uidpath->msg
l_timedep_tasks = {}

##UIDPaths of entities that we've modified; necessary to avoid feedback loop due to reflections
mirror = set()

class Msg_Dict:
    def __init__(self):
        ##mid_dict: Format: { "Message-ID" : set(["reverse_ref_mid1", ...]), ... }
        # Note: "reverse_ref_mid1" is the message ID of a message or task with Message-ID in its 'References' header.
        # For tasks, since they have no message IDs, "reverse_ref_mid1" is instead a UIDPath.
        self.rev_mid_dict = {}

        ##uid_lookup_dict: Format: { "Message-ID" : "uidpath" }
        self.uid_lookup_dict = {}

    ##Process the 'References' header of msg and add information to rev_mid_dict and uidpath
    def process_msg(self,msg,uidpath):
        print "In process_msg for "+uidpath
        sys.stdout.flush()
        if 'Message-ID' in msg:
            self.uid_lookup_dict[msg['Message-ID']]=uidpath
        if 'References' in msg:
            #Unlike for normal headers, we must sanitize References differently:
            #They can use either a comma, a space, or a newline as a separator.  Bastards.
            related_mids = msg['References'].replace("\r","").replace("\n",",").replace("\t",",").replace(" ",",")
            print "process_msg: related_mids: "+repr(related_mids)
            sys.stdout.flush()
            for rmid_ in related_mids.split(","):
                rmid = rmid_.strip()
                if rmid=="":
                    continue
                print "process_msg: updating rev_mid_dict key "+rmid
                sys.stdout.flush()
                if rmid not in self.rev_mid_dict:
                    self.rev_mid_dict[rmid]=set()
                print "Before: rev_mid_dict["+rmid+"]: "+repr(self.rev_mid_dict[rmid])
                sys.stdout.flush()
                if 'Message-ID' in msg:
                    self.rev_mid_dict[rmid].add(msg['Message-ID'])
                else:
                    self.rev_mid_dict[rmid].add(uidpath)
                print "After: rev_mid_dict["+rmid+"]: "+repr(self.rev_mid_dict[rmid])
                sys.stdout.flush()

    ##Use the stale cache data to remove a deleted or modified message's references from the dictionary
    def delete_msg(self,msg,uidpath):
        if 'Message-ID' in msg and msg['Message-ID'] in self.uid_lookup_dict:
            del self.uid_lookup_dict[msg['Message-ID']]
        if 'References' in msg:
            #Unlike for normal headers, we must sanitize References differently:
            #They can use either a comma, a space, or a newline as a separator.  Bastards.
            related_mids = msg['References'].replace("\r","").replace("\n",",").replace("\t",",").replace(" ",",")
            for rmid_ in related_mids.split(","):
                rmid = rmid_.strip()
                if rmid=="":
                    continue
                if rmid in self.rev_mid_dict:
                    if 'Message-ID' in msg:
                        self.rev_mid_dict[rmid].discard(msg['Message-ID'])
                    else:
                        self.rev_mid_dict[rmid].discard(uidpath)
                    if not len(self.rev_mid_dict[rmid]):
                        del self.rev_mid_dict[rmid]

##handle_msg: analyze a new message and, if it's important,
#             act in whatever way is appropriate
def handle_msg(uidpath,rfc822):
    global l_timedep_tasks

    print "In handle_msg for "+uidpath
    sys.stdout.flush()
    
    #Ignore reflections except for MID dictionary processing
    if uidpath in mirror:
        print "Found in mirror."
        #Examine References header and update msg_dict
        msg_dict.process_msg(email.parser.Parser().parsestr(rfc822),uidpath)
        print "removing from mirror: done."
        mirror.remove(uidpath)
        print "mirror: "+repr(mirror)
        sys.stdout.flush()
        return

    msg = email.parser.Parser().parsestr(rfc822)
    
    #Ignore specified accounts, unless sender in unignored_senders
    if 'From' in msg and client.get_email_addr_from_header(msg['From']) not in unignored_senders and client.get_nick_from_header(msg['From']) not in unignored_senders:
        for acct in ignored_accounts:
            if uidpath.find(acct+"/")==0:
                print "In ignored account: done."
                sys.stdout.flush()
                return
    else:
        print "Sender in unignored_senders or not in ignored account."
    
    #We need to handle an updated Task, following protocol
    if uidpath.find("Tasks")==0:
        task_revised = False
        if msg['X-MailTask-Completion-Status']=="Incomplete" and uidpath!="Tasks/BLACKHOLE":
            if 'X-MailTask-Virgin' not in msg and (type(msg.get_payload())==str or len(msg.get_payload())==1) or 'X-MailTask-Forced-Complete' in msg:
                del msg['X-MailTask-Completion-Status']
                msg['X-MailTask-Completion-Status']="Completed"
                task_revised = True
            elif 'X-MailTask-Virgin' in msg and len(msg.get_payload())>1:
                del msg['X-MailTask-Virgin']
                task_revised = True
        elif msg['X-MailTask-Completion-Status']=="Completed":
            del msg['X-MailTask-Forced-Complete']
            del msg['X-MailTask-Completion-Status']
            msg['X-MailTask-Completion-Status']="Incomplete"
            if 'X-MailTask-Virgin' not in msg and (type(msg.get_payload())==str or len(msg.get_payload())==1):
                msg['X-MailTask-Virgin']=""
            task_revised = True
        elif msg['X-MailTask-Completion-Status']=="Time-Dependent":
            l_timedep_tasks[uidpath]=msg
        elif uidpath!="Tasks/BLACKHOLE":
            print "*BUG!*: We found a Task with no or invalid X-MailTask-Completion-Status."
            sys.stdout.flush()

        #Examine References header and update msg_dict
        msg_dict.process_msg(msg,uidpath)

        #Handle Google Calendar Sync
        try:
            if do_gcal:
                dinfo = None
                gcal_id = msg['X-MailTask-GCalID']
                subject_str = "MailTask: "+msg.get('Subject',"No Subject")
                body_str = mt_utils.get_body(msg).get_payload()
                if 'X-MailTask-Date-Info' in msg:
                    dinfo = mt_utils.gtstfxmdis(msg['X-MailTask-Date-Info'])
                    if len(dinfo)==1:
                        dinfo = (dinfo[0],dinfo[0])

                if not gcal_id and 'X-MailTask-Date-Info' in msg:
                    gcal_id = mt_gcal_sync.insert_gcal_event((subject_str,body_str,dinfo[0],dinfo[1]))
                    msg['X-MailTask-GCalID']=gcal_id
                    task_revised = True
                elif gcal_id and 'X-MailTask-Date-Info' not in msg:
                    mt_gcal_sync.delete_gcal_event(gcal_id)
                    del msg['X-MailTask-GCalID']
                    task_revised = True
                elif gcal_id and 'X-MailTask-Date-Info' in msg:
                    mt_gcal_sync.update_gcal_event(gcal_id,(subject_str,body_str,dinfo[0],dinfo[1]))
        except Exception as e:
            print "WARNING: Google Calendar Error: "+e.message

        #If necessary, update task
        if task_revised:
            nsync.node_update(uidpath,msg.as_string())
            mirror.add(uidpath)
            print "handle_msg: update "+uidpath+" and add to mirror"
            print "mirror: "+repr(mirror)
            sys.stdout.flush()
    else: #not a Task: scan email headers and, if appropriate, create a new related task or update an existing one
        if 'From' not in msg or 'Message-ID' not in msg or client.get_email_addr_from_header(msg['From']) in ignored_senders:
            print "handle_msg: "+uidpath+" is from an ignored sender."
            sys.stdout.flush()
            return

        #If we're doing the calendar thing, check for the codeword in the subject
        if do_gcal and 'Subject' in msg and msg['Subject'].find(mt_gcal_sync.codeword)!=-1:
            chronos_tuples = []
            def scan_component(component):
                result = mt_chronos.extract_calendar_event(component.get_payload(decode=True))
                if result!=None:
                    chronos_tuples.append(result)

            try:
                mt_utils.walk_attachments(msg,scan_component)
                for entry in chronos_tuples:
                    mt_gcal_sync.insert_gcal_event(entry)
                return
            except Exception as e:
                print "ERROR: Attempted to schedule calendar event and failed; probable bug."
                print "The exception: "+repr(e)
                sys.stdout.flush()
        
        #Okay, now, first check if there is a Task out there that refers to a Message-ID that is also referred to by this message
        task_mid = None
        if 'References' in msg:
            print "handle_msg: searching "+uidpath+" related_mids for referring Task"
            sys.stdout.flush()
            related_mids = msg['References'].replace("\r","").replace("\n",",").replace("\t",",").replace(" ",",")
            print "handle_msg: "+repr(related_mids)
            sys.stdout.flush()
            for rmid_ in related_mids.split(","):
                rmid = rmid_.strip()
                if rmid=="":
                    continue
                print "handle_msg: examining "+rmid
                sys.stdout.flush()
                if rmid in msg_dict.rev_mid_dict:
                    print "handle_msg: msg_dict.rev_mid_dict["+rmid+"]: "+repr(msg_dict.rev_mid_dict[rmid])
                    sys.stdout.flush()
                    for referring_mid in msg_dict.rev_mid_dict[rmid]:
                        if referring_mid.find("Tasks/")==0:
                            task_mid = referring_mid
                            break
                    if task_mid!=None:
                        break
        
        #We found one: update its References and Date headers and completion status.
        if task_mid!=None:
            print "handle_msg: Updating reference header of task "+task_mid
            sys.stdout.flush()
            task_msg = email.parser.Parser().parse(open(os.path.join(client.cachedir,task_mid)))

            #Update related IDs
            relmids = mt_utils.get_related_ids(task_msg)
            relmids.append(msg['Message-ID'])
            mt_utils.set_related_ids(task_msg,relmids)

            #Update task_msg Date field
            del task_msg['Date']
            task_msg['Date']=email.utils.formatdate(localtime=True)

            #Update task completion status
            del task_msg['X-MailTask-Forced-Complete']
            del task_msg['X-MailTask-Completion-Status']
            task_msg['X-MailTask-Completion-Status']="Incomplete"
            
            nsync.node_update(task_mid,task_msg.as_string())
            mirror.add(task_mid)
        else: #No existing task, so we must make one
            print "handle_msg: Creating new task referencing MID "+msg['Message-ID']
            sys.stdout.flush()
            newtask=email.message.Message()
            nt_body = email.message.Message()
            nt_body['Content-Type'] = "text/plain"
            payload=""
            if client.get_email_addr_from_header(msg['From']) in email_info:
                payload=email_info[client.get_email_addr_from_header(msg['From'])]
            elif client.get_nick_from_header(msg['From']) in email_info:
                payload=email_info[client.get_nick_from_header(msg['From'])]
            nt_body.set_payload(payload)
            mt_utils.attach_payload(newtask,nt_body)
            newtask['Content-Type']="multipart/x.MailTask"
            newtask['Date']=email.utils.formatdate(localtime=True)
            newtask['Subject'] = client.get_nick_from_header(msg['From'])+": "+msg['Subject'] if 'Subject' in msg and 'From' in msg and client.get_nick_from_header(msg['From']) else "New Task"
            newtask['X-MailTask-Type'] = "Checklist"
            newtask['X-MailTask-Completion-Status'] = "Incomplete"
            newtask['X-MailTask-Virgin'] = "Yes"
            mt_utils.set_related_ids(newtask,[msg['Message-ID']])
            nsync.node_update("Tasks/NEWMESSAGE",newtask.as_string())

##Update cache and send info to server
# Returns True if any messages processed, False otherwise
# nsync.server_update_queue is a deque of pending client socket communiques
def server_synchronize():
    global nsync
    
    #select system call: I finally get to use this!
    retvals = select((nsync.smessage_conn_socket,nsync.cmessage_conn_socket),(nsync.cmessage_conn_socket,),(),0)

    #This is what we return: did we process messages?
    messages_processed = False
    
    #First: read from server notification socket if data is available
    #These are the possible server-initiated messages:
    #NODE-UPDATE-NOTIFY, CONNECT-STATUS-NOTIFY, FOLDER-INVALIDATE-NOTIFY,
    #KEEPALIVE-NOTIFY, and FECC-OFF.
    #We will ignore CONNECT-STATUS-NOTIFY.
    if nsync.smessage_conn_socket in retvals[0]:
        messages_processed = True
        smessage = OnTask_Message.message_from_socket(nsync.smessage_conn)
        if smessage.cmd_id=="NODE-UPDATE-NOTIFY":
            #Parse message body
            body = smessage.body
            uidpath = body[:body.index('\n')]
            modtime = int(body[(body.index('\n')+1):find_nth_substring('\n',2,body)])
            rfc822 = body[find_nth_substring('\n',2,body)+1:]

            print "NODE-UPDATE-NOTIFY: "+uidpath
            sys.stdout.flush()
            
            cacheadd_necessary = True

            #Special case the address book
            if uidpath=="ADDRESSBOOK":
                os.remove(os.path.join(client.cachedir,uidpath))
                open(os.path.join(client.cachedir,uidpath),'w').write(rfc822)
                client.initialize_addrbook()
                cacheadd_necessary = False
            
            #Add body to cache if necessary
            tokens = uidpath.rpartition('/')
            if tokens[0] in nsync.cache:
                for record in nsync.cache[tokens[0]]:
                    if record[1]["UID"]==tokens[2] and record[0] >= modtime:
                        cacheadd_necessary = False
                        break

            if cacheadd_necessary:
                gcal_id = None
                try: #if file already exists, we need to remove it from our memory and disk caches
                    os.stat(os.path.join(client.cachedir,uidpath))
                    print "In NODE-UPDATE-NOTIFY: deleting stale cache data"
                    sys.stdout.flush()
                    msg = email.parser.Parser().parse(open(os.path.join(client.cachedir,uidpath)))
                    gcal_id = msg['X-MailTask-GCalID']
                    msg_dict.delete_msg(msg,uidpath)
                    nsync.remove_from_cache(uidpath)
                except OSError:
                    pass
                if rfc822!="": #only add to cache if file would not be empty
                    print "In NODE-UPDATE-NOTIFY: adding to cache"
                    sys.stdout.flush()
                    nsync.add_to_cache(uidpath,rfc822)
                    handle_msg(uidpath,rfc822) #Scan message, see if it's important
                elif gcal_id and do_gcal:
                    mt_gcal_sync.delete_gcal_event(gcal_id)

            #Update last mod time
            client.last_mod_time = modtime

        elif smessage.cmd_id=="FOLDER-INVALIDATE-NOTIFY":
            #Delete all files in cached folder
            shutil.rmtree(os.path.join(client.cachedir,smessage.body)) #oh yeah this is secure yup
            os.mkdir(os.path.join(client.cachedir,smessage.body))
            
            #Clear entry in nsync.cache
            nsync.cache[smessage.body] = []

        elif smessage.cmd_id=="KEEPALIVE-NOTIFY":
            print "Received server's keepalive-notify"
            sys.stdout.flush()
            nsync.keepalive_notify()

        elif smessage.cmd_id=="FECC-OFF":
            #Disconnect/reconnect after notifying user of bug
            print "Server terminated connection and indicated protocol error:\n\n"+smessage.body
            sys.stdout.flush()
            raise Exception("FECC-OFF received from server")

        #Send ACK message to server
        nsync.smessage_conn.write(OnTask_Message("ACK","").get_message_string())
        nsync.smessage_conn.flush()
        
    if len(nsync.server_update_queue):
        print "nsync.server_update_queue: "+repr(nsync.server_update_queue)
        sys.stdout.flush()
    
    #Now, handle client-initiated messages through server_update_queue.
    if not len(nsync.server_update_queue):
        return messages_processed #No client-initiated messages if queue empty

    #Callables with f_1 in name only need cmessage_conn to be writeable.
    #f_2 (and others, theoretically) need cmessage_conn ready for reading.
    if repr(nsync.server_update_queue[0]).find("f_1")!=-1 and nsync.cmessage_conn_socket in retvals[1] or nsync.cmessage_conn_socket in retvals[0]:
        queued_cmessage_handler = nsync.server_update_queue.popleft()
        handler_retval = queued_cmessage_handler()
        nsync.cmessage_conn.flush()
        if handler_retval!=None:
            nsync.server_update_queue.appendleft(handler_retval)
        if handler_retval!=queued_cmessage_handler:
            messages_processed = True
    return messages_processed

def initialize_email_info_and_ignored_senders_accounts():
    global email_info
    global ignored_senders
    global ignored_accounts
    global unignored_senders

    email_info={}
    ignored_senders=set()
    ignored_accounts=set()
    unignored_senders=set()

    f_email_info = open("email_info.txt")
    try:
        while True:
            ot_m = OnTask_Message.message_from_socket(f_email_info)
            email_info[ot_m.cmd_id]=ot_m.body
    except:
        pass

    for line in map(str.rstrip,open("ignored_senders.txt").readlines()):
        ignored_senders.add(line)
    for line in map(str.rstrip,open("ignored_accounts.txt").readlines()):
        ignored_accounts.add(line)
    for line in map(str.rstrip,open("unignored_senders.txt").readlines()):
        unignored_senders.add(line)

def do_timedep_check():
    for entry in l_timedep_tasks.items():
        tasktype = mt_utils.get_task_type(entry[1])
        current_time = time.time()
        if tasktype=="Deadline" and current_time > email.utils.mktime_tz(email.utils.parsedate_tz(entry[1]['X-MailTask-Date-Info'])) or tasktype=="Meeting" and current_time > email.utils.mktime_tz(email.utils.parsedate_tz(entry[1]['X-MailTask-Date-Info'].split("/")[1].strip())):
            del entry[1]['X-MailTask-Completion-Status']
            entry[1]['X-MailTask-Completion-Status']="Completed"
            nsync.node_update(entry[0],entry[1].as_string())
            del l_timedep_tasks[entry[0]]

def main():
    global msg_dict
    global nsync
    global l_timedep_tasks
    
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
    client.cachedir = os.path.abspath(".")
    client.initialize_account_info()

    settings = open(os.path.join(client.cachedir,"settings"))
    client.password = settings.readline().rstrip()

    if do_gcal:
        mt_gcal_sync.codeword = settings.readline().rstrip()

    try:
        client.last_mod_time = int(settings.readline().rstrip())
    except:
        print "WARNING: no mod time in settings file; using 1/1/1970."
        client.last_mod_time = 0
    
    msg_dict = Msg_Dict()
    nsync = client.ClientNetSync()

    #Local function to add all files in a folder to cache
    def folder_cache_add(folder,process_instead=False):
        if not process_instead:
            nsync.cache[folder]=[]
        for fname in os.listdir(os.path.join(client.cachedir,folder)):
            if not process_instead:
                nsync.add_to_cache(folder+"/"+fname,open(os.path.join(client.cachedir,folder+"/"+fname)).read(),False)
            else:
                msg_dict.process_msg(email.parser.Parser().parse(open(os.path.join(client.cachedir,folder+"/"+fname))),folder+"/"+fname)

    #If we have a pickle, use it; otherwise, read in all emails and parse them (slow)
    if os.path.isfile(client.cachedir+"/client.pickle"):
        nsync.cache = cPickle.load(open(client.cachedir+"/client.pickle","rb"))
        if os.path.isfile(client.cachedir+"/l_timedep_tasks.pickle"):
            l_timedep_tasks = cPickle.load(open(client.cachedir+"/l_timedep_tasks.pickle","rb"))    
    else:
        #Add all account folders to cache
        for x in range(len(client.account_info)):
            folder_cache_add(repr(x)+"/INBOX")
            folder_cache_add(repr(x)+"/Sent")
        folder_cache_add("Tasks")

    if os.path.isfile(client.cachedir+"/msg_dict.pickle"):
        msg_dict = cPickle.load(open(client.cachedir+"/msg_dict.pickle","rb"))
    else:
        for x in range(len(client.account_info)):
            folder_cache_add(repr(x)+"/INBOX",True)
            folder_cache_add(repr(x)+"/Sent",True)
        folder_cache_add("Tasks",True)

    nsync.initialize_cache()
    if do_gcal:
        mt_gcal_sync.initialize()

    #email_info and ignored_senders
    initialize_email_info_and_ignored_senders_accounts()

    def dump_data():
        cPickle.dump(nsync.cache,open(client.cachedir+"/client.pickle","wb"),cPickle.HIGHEST_PROTOCOL)
        cPickle.dump(msg_dict,open(client.cachedir+"/msg_dict.pickle","wb"),cPickle.HIGHEST_PROTOCOL)
        cPickle.dump(l_timedep_tasks,open(client.cachedir+"/l_timedep_tasks.pickle","wb"),cPickle.HIGHEST_PROTOCOL)
        settings = open(os.path.join(client.cachedir,"settings"),'w')
        settings.write(client.password+"\n")
        if do_gcal:
            settings.write(mt_gcal_sync.codeword+"\n")
        settings.write(repr(client.last_mod_time)+"\n")


    #Main loop
    last_timedep_check=0
    startup_status=2
    try:
        while True:
            while server_synchronize():
                if len(nsync.server_update_queue) > 50 and (startup_status==0 or startup_status==2) or len(nsync.server_update_queue) < 40 and startup_status==1:
                    startup_status+=1
                
                if os.path.isfile(client.cachedir+"/FORCE_EXIT") or startup_status==3:
                    dump_data()
                    if startup_status==3:
                        print "FATAL: We appear to have lost our cmessage connection."
                    sys.exit(0)
            time.sleep(5)
            if time.time()-last_timedep_check > 600:
                print "Performing timed pickle backup."
                sys.stdout.flush()
                do_timedep_check()
                last_timedep_check=time.time()
                if os.path.isfile(client.cachedir+"/client.pickle"):
                    shutil.copyfile(client.cachedir+"/client.pickle",client.cachedir+"/client.pickle.bak")
                if os.path.isfile(client.cachedir+"/msg_dict.pickle"):
                    shutil.copyfile(client.cachedir+"/msg_dict.pickle",client.cachedir+"/msg_dict.pickle.bak")
                if os.path.isfile(client.cachedir+"/l_timedep_tasks.pickle"):
                    shutil.copyfile(client.cachedir+"/l_timedep_tasks.pickle",client.cachedir+"/l_timedep_tasks.pickle.bak")
                dump_data()
    except Exception as e:
        dump_data()
        print "Failed with exception: "+repr(e)
        sys.stdout.flush()
        

if __name__=="__main__":
    main()
