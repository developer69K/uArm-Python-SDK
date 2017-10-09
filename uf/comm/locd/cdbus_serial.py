#!/usr/bin/env python3
# Software License Agreement (BSD License)
#
# Copyright (c) 2017, UFactory, Inc.
# All rights reserved.
#
# Author: Duke Fong <duke@ufactory.cc>

# pip3.6 install pycrc --user
from PyCRC.CRC16 import CRC16

import _thread, threading
import serial
from serial.tools import list_ports
from ...utils.select_serial_port import select_port
from ...utils.log import *


def modbus_crc(data):
    return CRC16(modbus_flag = True).calculate(data)

def to_hexstr(data):
    return ' '.join('%02x' % b for b in data)


class CdbusSerial(threading.Thread):
    def __init__(self, ufc, node, iomap, dev_port = None, baud = 115200, filters = None):
        
        self.ports = {
            'in': {'dir': 'in', 'type': 'topic', 'callback': self.in_cb, 'data_type': bytes},
            'out': {'dir': 'out', 'type': 'topic'},
            'service': {'dir': 'in', 'type': 'service', 'callback': self.service_cb}
        }
        
        self.local_filter = [b'\xaa']
        self.remote_filter = [b'\x55']
        
        self.rx_bytes = b''
        
        self.node = node
        self.logger = logging.getLogger(node)
        ufc.node_init(node, self.ports, iomap)
        
        dev_port = select_port(logger = self.logger, dev_port = dev_port, filters = filters)
        if not dev_port:
            quit(1)
        
        # TODO: maintain serial connection by service callback
        self.com = serial.Serial(port = dev_port, baudrate = baud, timeout = 0.5)
        if not self.com.isOpen():
            raise Exception('serial open failed')
        threading.Thread.__init__(self)
        self.daemon = True
        self.alive = True
        self.start()
    
    def run(self):
        while self.alive:
            bchar = self.com.read()
            if len(bchar) == 0:
                if len(self.rx_bytes) != 0:
                    self.logger.warning('drop: ' + to_hexstr(self.rx_bytes))
                    self.rx_bytes = b''
                continue
            
            self.rx_bytes += bchar
            #self.logger.log(logging.VERBOSE, '>>> ' + to_hexstr(bchar))
            
            if len(self.rx_bytes) == 1:
                if bchar not in self.local_filter:
                    self.logger.debug('byte0 filtered: ' + to_hexstr(bchar))
                    self.rx_bytes = b''
            elif len(self.rx_bytes) == 2:
                if bchar not in self.remote_filter:
                    self.logger.debug('byte1 filtered: ' + to_hexstr(bchar))
                    self.rx_bytes = b''
            elif len(self.rx_bytes) == self.rx_bytes[2] + 5:
                if modbus_crc(self.rx_bytes) != 0:
                    self.logger.debug('crc error: ' + to_hexstr(self.rx_bytes))
                elif self.ports['out']['handle']:
                    self.logger.log(logging.VERBOSE, '-> ' + to_hexstr(self.rx_bytes[:-2]))
                    self.ports['out']['handle'].publish(self.rx_bytes[:-2])
                self.rx_bytes = b''
        
        self.com.close()
    
    
    def stop(self):
        self.alive = False
        self.join()
    
    def in_cb(self, data):
        self.logger.log(logging.VERBOSE, '<- ' + to_hexstr(data))
        data += modbus_crc(data).to_bytes(2, byteorder='little')
        self.com.write(data)
    
    def service_cb(self, message):
        # set filter, bond rates ...
        words = msg.split(' ', 1)
        action = words[0]
        
        words = words[1].split(' ', 1)
        param = words[0]
        
        if param == 'local_filter':
            if action == 'get':
                ret = 'ok, ' + ' '.join('%02x' % b[0] for b in self.local_filter)
                self.logger.debug('get local_filter ret: %s' % ret)
                return ret
            if action == 'set':
                self.logger.debug('set local_filter: %s' % words[1])
                self.local_filter = [int(n, 16).to_bytes(1, 'little') for n in words[1].split(' ')]
                return 'ok'
        if param == 'remote_filter':
            if action == 'get':
                ret = 'ok, ' + ' '.join('%02x' % b[0] for b in self.remote_filter)
                self.logger.debug('get remote_filter ret: %s' % ret)
                return ret
            if action == 'set':
                self.logger.debug('set remote_filter: %s' % words[1])
                self.remote_filter = [int(n, 16).to_bytes(1, 'little') for n in words[1].split(' ')]
                return 'ok'

