#! /usr/bin/env python

import email.message
import sys

import mt_utils

newtask=email.message.Message()
nt_body = email.message.Message()
nt_body['Content-Type'] = "text/plain"
payload = sys.argv[2].replace('\\n','\n')
nt_body.set_payload(payload)
mt_utils.attach_payload(newtask,nt_body)
newtask['Content-Type']="multipart/x.MailTask"
newtask['Date']=email.utils.formatdate(localtime=True)
newtask['Subject'] = sys.argv[1]
newtask['X-MailTask-Type'] = "Checklist"
newtask['X-MailTask-Completion-Status'] = "Time-Dependent"
newtask['X-MailTask-Date-Info'] = email.utils.formatdate(timeval=int(sys.argv[3]),localtime=True) + " / " + email.utils.formatdate(timeval=int(sys.argv[4]),localtime=True)
newtask['X-MailTask-Virgin'] = "Yes"

print newtask.as_string()
