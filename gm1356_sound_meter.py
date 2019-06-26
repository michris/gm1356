#!/usr/bin/env python
# -*- coding: utf-8 -*-

from msvcrt import kbhit
import pywinusb.hid as hid
import logging
from logging.handlers import RotatingFileHandler
import time
import os
import datetime
import sys

# What this code does : 
# - This code reads out data from Benetech GM1356 digital sound level meter and stores it in a csv file
# - USB initialisation, get data command & data interpretation obtained via reverse engineering
# - Before using -> set parameters on device (dB A, Fast, Max lock off) then start this script

# Tested : 
# - Tested on windows 10, Python 3.6.6, pywinusb 0.4.2

__author__      = "Christophe Michiels"
__copyright__   = "Copyright 2019"
__license__ = "MIT"
__version__ = "1.0"
__maintainer__ = "Christophe Michiels"
__email__ = ""
__status__ = "Production"

# Inspiration & thanks to :
# - https://www.wenbiancheng.com/question/python/16357756-How%20to%20send%20hid%20data%20to%20device%20using%20python%20/%20pywinusb?
# - http://www.swblabs.com/article/pi-soundmeter (WS1361 digital sound level meter)
# - https://freeusbanalyzer.com/

# requirements.txt : 
# pywinusb

# Manual install pywinusb :
# Python -m pip install pywinusb

# TODO :
# - 

# USB ids for device GM1356
VENDOR_ID = 0x64BD
PRODUCT_ID = 0x74E3

# Raw logger variables
raw_logger = None
raw_log_file_name = "raw_log.txt"
raw_log_file_size = 1 * 1024 * 1024                         # 1MB file size

# CSV logger variables
csv_logger = None
csv_log_file_name = "data.csv"

# Stdio logger varaibles
stdio_logger = None

# General logger variable
logging_folder = "log/"

# USB variables 
device = None
delay_between_samples = 0.5                     # in sec (Do not go faster than 0.5 sec)

cmd_buffer = [0x00, 0xb3, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]             # This command string needs to be send to the device in order to receive data
#print(cmd_buffer)


def init_logging():
    """ Initialise different log files """
    global stdio_logger, raw_logger, csv_logger

    # Create log folder if it does not yet exist
    if not os.path.exists(logging_folder):
        os.makedirs(logging_folder)

    # Logger for time and sound levels in , separted csv file
    csv_logger = logging.getLogger('csv_logger')
    csv_logger.setLevel(logging.INFO)
    path = os.path.join(logging_folder, csv_log_file_name)
    handler = logging.handlers.TimedRotatingFileHandler(path, when="H", interval=1)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    csv_logger.addHandler(handler)

    # Log raw data, start & stop messages ...
    raw_logger = logging.getLogger('raw_logger')
    raw_logger.setLevel(logging.INFO)
    path = os.path.join(logging_folder, raw_log_file_name)
    handler = RotatingFileHandler(path, maxBytes=raw_log_file_size, backupCount=5)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    raw_logger.addHandler(handler)

    # Also log everything to the cmdline ; put in comments if not wanted
    stdio_logger = logging.getLogger()
    stdio = logging.StreamHandler()
    stdio.setLevel(logging.INFO)
    formatter = logging.Formatter("%(message)s")
    stdio.setFormatter(formatter)
    stdio_logger.addHandler(stdio)
    return

""" 
Explanation of bits in data[3] field :
  0000x000 : bit 16 : x = 1 -> dB C ; x = 0 -> dB A 
  00x00000 : bit 32 : x = 1 -> Max lock on ; x = 0 -> Max lock off
  0x000000 : bit 64 : x = 1 -> Fast ; x = 0 -> Slow
  00000xxx : xxx = 0 ; Range 30 - 130
  00000xxx : xxx = 1 ; Range 30 - 80
  00000xxx : xxx = 2 ; Range 50 - 100
  00000xxx : xxx = 3 ; Range 60 - 110
  00000xxx : xxx = 4 ; Range 80 - 130
"""
def get_units(value):
    """ Return dB units """

    if (value & 16) == 16:
        return 'dB C'
    else :
        return 'dB A'

def get_max_lock(value):
    """ Return if Max lock is on or off """

    if (value & 32) == 32:
        return 'Max lock on'
    else :
        return 'Max lock off'

def get_speed(value):
    """ Return if the capturing speed is fast (no filtering) or slow (filtered) """

    if (value & 64) == 64:
        return 'Fast'
    else :
        return 'Slow'

def get_range(value):
    """ Return the range for under or over limit message """

    if (value & 4) == 4:
        return '80 - 130'
    elif (value & 3) == 3:
        return '60 - 110'
    elif (value & 2) == 2:
        return '50 - 100'
    elif (value & 1) == 1:
        return '30 - 80'
    else :
        return '30 - 130'

def get_dB(value1, value2):
    """ Calculate the dB value out of two bytes information """
    dB = (value1*256 + value2)*0.1
    return dB

def sample_handler(data):
    """ Data handler callback function. Log data in a csv file and a raw log file """
    #t = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")[:16]                     # Show msec with only 2 numbers
    t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:22]                     # Show msec with only 2 numbers
    csv_logger.info(f"{t},{get_dB(data[1], data[2]):.1f},{get_units(data[3])}")
    raw_logger.info(f"{t},{get_dB(data[1], data[2]):.1f},{get_units(data[3])},{get_speed(data[3])},{get_max_lock(data[3])},{get_range(data[3])},{data}")
    #print(f"Raw data: {data} ; {get_dB(data[1], data[2]):.1f}")
    return

def close_usb():
    """ Close usb device """
    global device

    try:
        device.close()
    except:
        raw_logger.error("Could not close usb device")
    return

def init_usb():
    """ Initialise USB device, open device & set data call back function """
    global device

    filter = hid.HidDeviceFilter(vendor_id = VENDOR_ID, product_id = PRODUCT_ID)
    hid_device = filter.get_devices()
    device = hid_device[0]
    try:
        device.open()
        raw_logger.info(hid_device)
        device.set_raw_data_handler(sample_handler)
    except:
        close_usb()
        raw_logger.error("Could not open usb device")
        raw_logger.error("Exit")
        sys.exit(1)
    return

def capture_data():
    """ Capture data loop. Send a get data cmd & sleep before sending the next request. Data is handled by the callback function """
    global device

    print("Press any key to stop")
    print("Waiting for data...")
    while not kbhit() and device.is_plugged():
        try:
            device.send_output_report(cmd_buffer)
        except Exception as e:
            # FYI : this code has not been tested - Could not simulate
            if e == HIDError:
                raw_logger.error("USB write timed out")
            else:
                raw_logger.error("Unknown error : " + str(e))
            close_usb()
            raw_logger.error("Exit")
            sys.exit(1)
        time.sleep(delay_between_samples)
    
    if not device.is_plugged():
        raw_logger.error("Stopped capturing : Device unplugged")
    else:
        raw_logger.error("Stopped capturing : Keyboard pressed")

    return

if __name__ == '__main__':
    init_logging()
    raw_logger.info("Capturing data started ...")
    init_usb()
    capture_data()
    close_usb()
    raw_logger.info("Script ended")


