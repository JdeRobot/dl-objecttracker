#
# Created on Jan, 2019
#
# @author: alexandre2r
#
#  Based on @naxvm code:
# https://github.com/JdeRobot/dl-objectdetector
#


import time
import threading
from datetime import datetime


class ThreadNetwork(threading.Thread):

    def __init__(self, network):
        ''' Threading class for Camera. '''

        self.t_cycle = 150  # ms
        self.network = network
        self.framerate = 0

        threading.Thread.__init__(self)

    def run(self):
        ''' Updates the thread. '''
        while True:
            start_time = datetime.now()
            if self.network.activated:
                self.network.predict()
            end_time = datetime.now()

            dt = end_time - start_time
            dtms = ((dt.days * 24 * 60 * 60 + dt.seconds) * 1000 +
                    dt.microseconds / 1000.0)

            if self.network.activated:
                delta = max(self.t_cycle, dtms)
                self.framerate = int(1000.0 / delta)
            else:
                self.framerate = 0

            if(dtms < self.t_cycle):
                time.sleep((self.t_cycle - dtms) / 1000.0)

    def runOnce(self):
        if not self.network.activated:
            self.network.predict()
