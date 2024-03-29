#
# Created on Feb, 2018
#
# @author: alexandre2r
#
# Based on @naxvm code:
# https://github.com/JdeRobot/dl-objectdetector
#

import time
import threading
from datetime import datetime

t_cycle = 150  # ms


class ThreadTracker(threading.Thread):

    def __init__(self, tracker):
        ''' Threading class for Tracker. '''
        self.tracker = tracker
        threading.Thread.__init__(self)

    def run(self):
        ''' Updates the thread. '''
        while True:
            start_time = datetime.now()
            if self.tracker.activated:
                self.tracker.track()
            end_time = datetime.now()

            dt = end_time - start_time
            dtms = ((dt.days * 24 * 60 * 60 + dt.seconds) * 1000 +
                    dt.microseconds / 1000.0)

            if dtms < t_cycle:
                time.sleep((t_cycle - dtms) / 1000.0)