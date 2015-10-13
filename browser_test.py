from fltk import *
from FLTK_Advanced_Browser import *
w = Fl_Window(0,0,200,200)
FBrowser = FLTK_Advanced_Browser(Fl_Select_Browser)
b = FBrowser(0,0,200,200)
b.type(2) #This is afaict totally undocumented.
b.column_widths((100,25,25,50))
b.add("Test\tString\tIs\tGood")
w.resizable(w)
w.show()
