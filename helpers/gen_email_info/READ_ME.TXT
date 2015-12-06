To use this, you need to pass in a list of email addresses or nicks, separated by newlines, on standard in.  You also have to pass a description to give these emails/nicks on file descriptor 3.  You do this with 3< instead of just <.  So, like,

./the_extractor.py < ../email_extractor/emails.html | ./gen_email_info.py 3< ~/tongue.txt

It works.  It's cool.  I don't know why more people don't do it.
