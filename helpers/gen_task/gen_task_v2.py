#! /usr/bin/env python

import email.message
import sys

import mt_utils

newtask=email.message.Message()
nt_body = email.message.Message()
nt_body['Content-Type'] = "text/plain"
payload = sys.stdin.read()
nt_body.set_payload(payload)
mt_utils.attach_payload(newtask,nt_body)
newtask['Content-Type']="multipart/x.MailTask"
newtask['Date']=email.utils.formatdate(localtime=True)
newtask['Subject'] = sys.argv[1]
newtask['X-MailTask-Type'] = "Checklist"
newtask['X-MailTask-Completion-Status'] = "Incomplete"
newtask['X-MailTask-Virgin'] = "Yes"
if len(sys.argv) > 2 and sys.argv[2]!="":
    newtask['X-MailTask-Priority'] = sys.argv[2]
if len(sys.argv) > 3:
    newtask['X-MailTask-Slay'] = sys.argv[3]

print newtask.as_string()
