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

import codecs
import fltk
from html2text import html2text
import os
import tempfile

#Note: EVERY method here must correctly handle unicode by decoding it with utf-8/replace,
#then ENCODING it with utf-8

#Note: FLTK 1.1 seems to use ISO-8859-1 as its native encoding.
#      FLTK 1.3 changes this to UTF-8.
#FLTK_ENCODING="ISO-8859-1"
FLTK_ENCODING="UTF-8"

def text_plain(submsg,mime_encoding):
    return submsg.get_payload(decode=True).decode(encoding=mime_encoding,errors="replace").encode(encoding=FLTK_ENCODING,errors="replace")

def text_html(submsg,mime_encoding):
    return html2text(submsg.get_payload(decode=True).decode(encoding=mime_encoding,errors="replace")).encode(encoding=FLTK_ENCODING,errors="replace")

def application_pdf(submsg,mime_encoding):
    temptuple=tempfile.mkstemp()
    os.fdopen(temptuple[0],'w').write(submsg.get_payload(decode=True))
    os.system("xpdf "+temptuple[1]+" & ( sleep 10; rm "+temptuple[1]+" ) &")
    return "PDF file opened"

def image_jpeg(submsg,mime_encoding):
    temptuple=tempfile.mkstemp()
    os.fdopen(temptuple[0],'w').write(submsg.get_payload(decode=True))
    os.system("display "+temptuple[1]+" & ( sleep 10; rm "+temptuple[1]+" ) &")
    return "JPEG file opened"

def application_octetstream(submsg,mime_encoding):
    fc = fltk.Fl_File_Chooser(".","*",fltk.Fl_File_Chooser.CREATE,"Select Save Location")
    fc.show()

    while fc.shown():
        fltk.Fl_wait()

    if fc.value()==None:
        return submsg.get_payload(decode=True).decode(encoding=mime_encoding,errors="replace").encode(encoding=FLTK_ENCODING,errors="replace")

    open(fc.value(),'w').write(submsg.get_payload(decode=True))
    return "Undisplayable file; saved to "+fc.value()

def display_submessage(submsg):
    if submsg['Content-Transfer-Encoding']==None:
        del submsg['Content-Transfer-Encoding']
    
    if submsg.get_payload(decode=True)==None:
        return ""
    
    ATTACHE = { "text/plain" : text_plain, "text/html" : text_html,
                "application/pdf" : application_pdf,
                "image/jpeg" : image_jpeg }

    
    mime_encoding = submsg.get_content_charset()
    if mime_encoding==None:
        mime_encoding="utf-8"
    else:
        try:
            codecs.lookup(mime_encoding)
            valid_encoding = True
        except LookupError:
            valid_encoding = False
        if not valid_encoding:
            mime_encoding="utf-8"

    mimetype = submsg.get_content_type()
    print mimetype
    if mimetype in ATTACHE:
        return ATTACHE[mimetype](submsg,mime_encoding)
    elif mimetype.find("text/")==0:
        return text_plain(submsg,mime_encoding)
    return application_octetstream(submsg,mime_encoding)
