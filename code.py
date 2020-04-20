import time
from pyglanceportal import PyGlancePortal

pyportal = PyGlancePortal(debug=True)

while True:
    pyportal.build_display()
    time.sleep(300)