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

import base64
import email
import email.parser
import email.utils
import sys
import time

#Dead-Simple CaseInsensitiveList class
class CaseInsensitiveList(list):
    def index(self,key):
        lowered_key = key.lower()
        for i in range(len(self)):
            if self[i].lower()==lowered_key:
                return i
        raise ValueError
    
    def __contains__(self, key):
        try:
            self.index(key)
        except ValueError:
            return False
        return True

##Stupidly simple method to turn a sequence type's .index() method into .find()
def find(seqobj, needle):
    try:
        return seqobj.index(needle)
    except ValueError:
        return -1

##Returns a date/time string appropriate for use in email main browser
def browser_time(tstr,formatstr="%m/%d/%Y %H:%M"):
    tztmt = email.utils.parsedate_tz(tstr)
    if tztmt!=None:
        return time.strftime(formatstr,time.localtime(email.utils.mktime_tz(tztmt)))
    else:
        return time.strftime(formatstr,time.localtime(0))

##Given an email header, find all instances of commas in nicknames and turn them into
# ASCII character Device Control 1 (0x11)
def decomma(tstr):
    to_return=""
    in_quotes=False
    prev_char_backslash=False
    for char in tstr:
        if prev_char_backslash and not in_quotes:
            if char==',':
                to_return+='\x11'
            else:
                to_return+=char
            prev_char_backslash=False
        elif char=='\\':
            prev_char_backslash=True
        elif char=='"':
            in_quotes = not in_quotes
        elif in_quotes and char==',':
            to_return+='\x11'
        else:
            to_return+=char
    return to_return

def recomma(tstr):
    return tstr.replace('\x11',',')

##Return the MIME Message-ID, or generate and return NONMIME ID from timestamp.
def get_message_id(msg,folder):
    if "Message-ID" in msg:
        return msg['Message-ID'].replace(' ','').replace('\t','').replace('\r','').replace('\n','')
    else: #generate nonmime-id
        sanitized_folder=folder.replace('/','-')
        return "<NONMIME-TimestampID-"+repr(int(email.utils.mktime_tz(email.utils.parsedate(msg["Date"]))))+"@"+sanitized_folder+".mailtask"

##Generate a unique Message-ID for given message
def gen_message_id(msg,params):
    messageID = ("<"+base64.b32encode(repr(hash(msg.as_string())))+"@"+base64.b32encode(repr(hash(msg["From"])))+repr(int(params[0]))+".mailtask"+">").replace("=","")
    del msg["Message-ID"]
    msg["Message-ID"]=messageID

##Get list of MIME IDs of related messages
def get_related_ids(msg):
    return msg["References"].replace('\t',' ').replace('\r',' ').replace('\n',' ').replace(',',' ').split() if 'References' in msg else []

##Set "References" header to specified list of MIME IDs
def set_related_ids(msg,related_list):
    del msg["References"]
    msg["References"]=",".join(set(related_list))

##Encapsulates a message object into an RFC822 attachment
def rfc822_encapsulate(msg,filename=""):
    lines = msg.as_string().splitlines()

    for header in ("Content-Type","Content-Transfer-Encoding"):
        splitpoint=-1
        for i in range(len(lines)):
            if lines[i]=="":
                splitpoint=i
                break
        for i in range(splitpoint):
            if lines[i].find(header+": ")==0:
                lines.insert(splitpoint,lines[i])
                del lines[i]
                #Handle multi-line Content-Type/Content-Transfer-Encoding headers
                while len(lines[i]) and lines[i][0] in (' ','\t'):
                    lines.insert(splitpoint,lines[i])
                    del lines[i]
                break
    
    for i in range(len(lines)):
        if lines[i].find("Content-Type: ")==0:
            lines.insert(i,"")
            break
    return email.parser.Parser().parsestr('Content-Type: message/rfc822'+('; name="'+filename+'"' if filename!="" else "")+'\n'+"\n".join(lines))

##Attaches a message object to the payload of another message object
# If the parent message object is not of multipart type, restructure
# the message such that its current payload is the first subpayload of
# the parent message, and change the parent payload's content type to
# multipart/mixed.
def attach_payload(parent,child):
    #message/rfc822 encapsulation requires the payload's sole list element to be
    #the target of the attachment instead of the encapsulated message
    if parent.get_content_type()=="message/rfc822":
        attach_payload(parent.get_payload()[0],child)
        return
    
    if 'X-MailTask-Virgin' in parent:
        del parent['X-MailTask-Virgin']
    if 'Content-Type' not in child:
        child.set_type("text/plain")
    if 'To' in child or 'Cc' in child or 'Bcc' in child or 'Message-ID' in child:
        child = rfc822_encapsulate(child)
    if isinstance(parent.get_payload(),str):
        first_payload = email.message.Message()
        first_payload['Content-Type']=parent['Content-Type']
        first_payload['Content-Transfer-Encoding']=parent['Content-Transfer-Encoding']
        if 'Content-Disposition' in parent:
            first_payload['Content-Disposition']=parent['Content-Disposition']
        first_payload.set_payload(parent.get_payload())
        parent.set_type("multipart/mixed")
        parent.set_payload([first_payload])
    parent.attach(child)

##Take a message embedded in another message (such as a message of type
# multipart/x.MailTask) and delete the message/rfc822 header.  Replace
# it with the message internal header.  This is complicated by the fact
# that the message's internal header must be moved up to before the
# Message-ID header in order to be accepted.
# Precondition: message must already have Message-ID header
def unrfc822(message):
    msgstr = message.as_string()
    msg_parts = msgstr.split("\n")
    del msg_parts[0]
    insert_idx = -1
    fields_to_move = set(["Content-Type","MIME-Version"])
    for i in range(len(msg_parts)):
        if msg_parts[i].find("Message-ID")==0 and insert_idx==-1:
            insert_idx=i
        move_this_line = False
        for field in fields_to_move:
            if msg_parts[i].find(field)==0:
                move_this_line = True
                fields_to_move.remove(field)
                break
        if move_this_line:
            if insert_idx!=-1:
                magic_str = msg_parts[i]
                del msg_parts[i]
                msg_parts.insert(insert_idx,magic_str)
            else:
                print "BUG: Content-Type before Message-ID in unrfc822"
    
    return email.parser.Parser().parsestr("\n".join(msg_parts))

##Flatten a message according to RFC2822 by stupidly inserting newlines everywhere.
# Do the minimum necessary because this is asinine but Microsoft SMTP seems to require it.
# I DON'T CARE if it's the standard IT'S 2015 AND ARBITRARY LINE LENGTH LIMITS MAKE NO SENSE!
def rfc2822_flatten(mstring):
    to_return=""
    for line in mstring.split("\n"):
        if len(line)<998:
            to_return+=line+"\n"
        else:
            to_dispose = line
            while len(to_dispose):
                if len(to_dispose)<998:
                    to_return+=to_dispose+"\n"
                    to_dispose=""
                else:
                    if to_dispose[:998].rfind("\n")!=-1:
                        split_idx = to_dispose[:998].rfind("\n")
                    else:
                        split_idx = 998
                    to_return+=to_dispose[:split_idx]+"\n"
                    to_dispose = to_dispose[split_idx:]
    return to_return

##Deletes the passed object from the payload of message object.
# Handles changing message content type from multipart to single-part if necessary
def delete_payload_component(parent,child):
    if parent.get_content_type()=="message/rfc822":
        delete_payload_component(parent.get_payload()[0],child)
        return
    payload = parent.get_payload()
    del payload[payload.index(child)]
    if len(payload)==1:
        sole_component = payload[0]
        parent.set_payload(sole_component.get_payload())
        if 'Content-Type' in sole_component:
            parent.replace_header('Content-Type',sole_component['Content-Type'])
        else:
            parent.set_type("text/plain")

        if 'Content-Transfer-Encoding' in sole_component:
            del parent['Content-Transfer-Encoding']
            parent['Content-Transfer-Encoding']=sole_component['Content-Transfer-Encoding']

#Get best submessage from an email to use as a body.  Return it
def get_body(msg):
    #Internal method to rank content types of bodies
    def rank_body(ctype):
        TYPE_RANKING = ["text/plain","text/html","text/"]
        for i in range(len(TYPE_RANKING)):
            if ctype.get_content_type().find(TYPE_RANKING[i])==0:
                return i
        return len(TYPE_RANKING)
    
    full_payload = msg.get_payload()
    if isinstance(full_payload,str):
        return msg

    #Best body found so far
    best_body = None
    best_body_ranking = sys.maxint

    #Check all direct payload subcomponents
    for candidate in full_payload:
        if 'Content-Type' in candidate and not ('Content-Disposition' in candidate and candidate['Content-Disposition'].lower().find("attachment")!=-1):
            if rank_body(candidate) < best_body_ranking:
                best_body = candidate
                best_body_ranking = rank_body(candidate)

    #Check if we have multipart/alternative subpart.  Examine it if so.
    for node in full_payload:
        if 'Content-Type' in node and node.get_content_type().find("multipart/")==0:
            subpayload = node.get_payload()
            for candidate in subpayload:
                if 'Content-Type' in candidate and not ('Content-Disposition' in candidate and candidate['Content-Disposition'].find("attachment")!=-1):
                    if rank_body(candidate) < best_body_ranking:
                        best_body = candidate
                        best_body_ranking = rank_body(candidate)

    return best_body


##Returns string representing which type of task we are
def get_task_type(task):
    if 'X-MailTask-Date-Info' not in task:
        return "Checklist"
    elif task['X-MailTask-Date-Info'].find("/")==-1:
        return "Deadline"
    else:
        return "Meeting"


#Search message cache for specific MIDs
def search_cache(mid,cache):
    for record in cache:
        rdict = record[1]
        if 'Message-ID' in rdict and get_message_id(rdict,None)==mid:
            return record
    return None

##Walk the body of a message and process each submessage
def walk_attachments(submsg,process_single_submsg,force_decomp=False):
    if not isinstance(submsg.get_payload(),str) and (force_decomp or submsg.get_content_type().find("multipart/")==0):
        for component in submsg.get_payload():
            if component.get_content_type().find("multipart/")==0:
                for subsubmsg in component.get_payload():
                    walk_attachments(subsubmsg,process_single_submsg,force_decomp)
            else:
                process_single_submsg(component)
    else:
        process_single_submsg(submsg)

##Gets MIME type of file
# Uses magic if available, otherwise mimetypes
try:
    import magic
    has_magic=True
except ImportError:
    has_magic=False
    import mimetypes
    mimetypes.init()
def get_mime_type(fname):
    if has_magic:
        return magic.from_file(fname,mime=True)
    else:
        if fname.find(".")!=-1:
            simple_suffix=fname.rsplit(".")[1]
            simple_name=fname.split(".")[0]+"."+simple_suffix
        else:
            simple_name=fname
        to_return = mimetypes.guess_type(simple_name,strict=False)[0]
        if to_return==None:
            to_return = "application/octet-stream"
        return to_return
