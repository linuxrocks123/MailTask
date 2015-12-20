# MailTask Alpha: The Email Manager

---

## License Info (Copyright (C) 2015  Patrick Simmons)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see
[http://www.gnu.org/licenses/](http://www.gnu.org/licenses/).

---

Note: The GPLv3 is in the LICENSE file.

## Description

Hello.  This set of programs is MailTask.  This is a brief document
intending to familiarize users with how to use this program.

MailTask is a suite of three related programs.  They are `server.py`,
`client.py`, and `mt_scrtry_rn.py`.  These will be referred to as the
server, the client, and the utility client, respectively.

To use the server, you create an empty directory and put a file called
`ACCOUNT_INFO` with the servers, usernames, and passwords of the
accounts you intend to use with MailTask in that directory.  You then
create the Tasks folder as well as `*/INBOX` and `*/Sent`, where `*` is
every number from 0 up to but not including the number of accounts you
put in `ACCOUNT_INFO`.  You should also create an empty file called
`ADDRESSBOOK` and a `Tasks/BLACKHOLE` file containing roughly the
following:
```
Content-Type: multipart/x.MailTask;
 boundary="===============4405596723705947737=="
Date: Thursday, 1 Jan 1970 00:00:00 -0000
Subject: BLACKHOLE
X-MailTask-Type: Checklist
X-MailTask-Completion-Status: Incomplete

--===============4405596723705947737==
Content-Type: text/plain


--===============4405596723705947737==--
```

You then start the server in that directory, passing it two parameters
indicating the ports you want to use to communicate with the client.

Each client, and the utility client, should be set up a similar way.
See the source for the utility client for additional ways to configure
the utility client; each user will probably have a slightly different
use case for how to use the utility client and may even want to modify
the utility client to behave differently.  The utility client is a
client, but it automatically creates tasks based on incoming emails,
marks tasks done when they are finished, and can be configured to
ignore certain accounts or folders.

Be aware that the server will mark all emails in an account as read
when it first runs.  Be also aware that it will take a VERY long time
to download all emails the first time a client is run.  For large
accounts, it may be necessary to manually copy over the server's
downloaded emails in these cases (contained in the `*/{INBOX,Sent}`
folders).

## Requirements
1)  Python 2  
2)  FLTK / pyfltk  
3)  cPickle (falls back to pickle if not found)  
4)  ???  

Anecdotal note about pyfltk: the easiest way to get this on
Debian-based distros is to use the `python-fltk` package.  Using pip
with a requirements.txt file with pyFltk has been reported not to work.

I may add more documentation here later, but that's it for now.  Enjoy!
