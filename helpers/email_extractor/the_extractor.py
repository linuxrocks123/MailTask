#! /usr/bin/env python

import sys
for line in sys.stdin.readlines():
    start_index = line.find("mailto:?Bcc=")
    if start_index!=-1:
        emails = line[start_index+len("mailto:?Bcc="):line.find(">")-1]
        for addr in emails.split(";"):
            print addr
        break
