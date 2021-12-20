import drivers
from time import *

display=drivers.LCD()

display.lcd_display_string("hello world",1)
display.lcd_display_string("Raspberry pi b",2)

sleep(100)
