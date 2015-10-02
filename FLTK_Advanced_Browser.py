#! /usr/bin/env python

#Direct translation from C++ version of this template class to Python

from fltk import *

def FLTK_Advanced_Browser(T):
    class FLTK_Advanced_Browser_T(T):
        
        @staticmethod
        def advanced_browser_callback(adv_browser):
            i=1
            while i<=adv_browser.size():
                if adv_browser.selected(i) and adv_browser.is_disabled(i):
                    adv_browser.deselect(i)
                i+=1

            if hasattr(adv_browser,"real_callback"):
                adv_browser.real_callback(adv_browser,*adv_browser.varargs)

        def callback(self,real_callback,*args):
            self.real_callback = real_callback
            self.varargs = args
    
        def __init__(self,x,y,w,h,label=""):
            T.__init__(self,x,y,w,h,label)
            self.initial_width = w
            self.red_lines = set()
            self.disabled_lines = set()
            self.bold_lines = set()
            T.callback(self,self.advanced_browser_callback)

        def column_widths(self,tup):
            self.initial_column_widths=tup
            T.column_widths(self,tup)
            
        def resize(self,x,y,w,h):
            T.resize(self,x,y,w,h)

            if hasattr(self,"initial_column_widths"):
                ratio = float(w)/self.initial_width
                current_column_widths = []
                for i in range(len(self.initial_column_widths)):
                    current_column_widths.append(int(self.initial_column_widths[i]*ratio))

                T.column_widths(self,tuple(current_column_widths))
                T.redraw(self)

        def is_red(self,line):
            return line in self.red_lines

        def set_red(self,line):
            if line in self.red_lines:
                return

            self.red_lines.add(line)
            self.set_color(line,"88")

        def unset_red(self,line):
            if line not in self.red_lines:
                return

            self.red_lines.remove(line)
            self.unset_color(line,"88")

        def is_disabled(self,line):
            return line in self.disabled_lines

        def set_disabled(self,line):
            if line in self.disabled_lines:
                return

            self.disabled_lines.add(line)
            self.set_color(line,"39")

        def unset_disabled(self,line):
            if line not in self.disabled_lines:
                return

            self.disabled_lines.remove(line)
            self.unset_color(line,"39")

        def is_bold(self,line):
            return line in self.bold_lines

        def set_bold(self,line):
            if line in self.bold_lines:
                return

            self.bold_lines.add(line)

            new_text = self.text(line)
            new_text = new_text.replace(self.column_char(),self.column_char()+"@b")
            new_text = "@b"+new_text
            self.text(line,new_text)

        def unset_bold(self,line):
            if line not in self.bold_lines:
                return

            self.bold_lines.remove(line)

            new_text = self.text(line)
            new_text = new_text.replace("@b","")
            self.text(line,new_text)

        def set_color(self,line,color):
            new_text = self.text(line)
            new_text = new_text.replace(self.column_char(),self.column_char()+"@C"+color)
            new_text = "@C"+color+new_text
            self.text(line,new_text)

        def unset_color(self,line,color):
            new_text = self.text(line)
            new_text = new_text.replace("@C"+color,"")
            self.text(line,new_text)

    return FLTK_Advanced_Browser_T
