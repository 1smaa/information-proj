# -*- coding: utf-8 -*-
"""
Created on Thu Oct 13 17:53:22 2016

@author: Marco Avesani
"""

#import visa
import pyvisa as visa
import numpy as np
from time import time_ns, sleep
from struct import unpack
from datetime import datetime
import traceback

class Oscilloscope():
    """
    Class to deal with any Tek oscilloscope
    In particular with the TDS6000 series
    """

    def __init__(self, usb_address=None, active_channels: list[int] = [1], memory=1000000, connect_at_start=False):
        """
        Args:
            self (int): Pointer to the class
            usb_address (str): USB address of the Oscilloscope
        """
        self._resource_man = visa.ResourceManager('@py')
        self._nchan = len(active_channels)
        self._memory = memory

        self._is_connected = False

        self.ymult: float = None
        self.yzero: float = None
        self.yoff: float = None
        self.xincr: float = None
        self.xscale: float = None
        self.xoffset: float = None
        self.xlength: float = None

        if connect_at_start:
            self.connect(usb_address, active_channels, memory)

    # other IP: 'TCPIP::192.168.40.205::INSTR'
    def connect(self, usb_address: str = 'TCPIP::192.168.50.205::INSTR', active_channels: list[int] = [1], memory: int = 1000000):
        '''
            Opens the visa resource manager. If provided uses the address, otherwise
            uses the first result from the visa list.
            Set the source channel to 1
            Set the 8 bit accuracy
            Set binary transfer protocol with big endian
            Gets and stores X and Y scale info
            Set the memory to 1M points
        '''
        # "Create the visa resource and connect to the device"
        if usb_address is None:
            dev_list = self._resource_man.list_resources()
            for dev in dev_list:
                print(dev)
                try:
                    self._scope = self._resource_man.open_resource(dev)
                    self._scope.query('WFMPRE:YMULT?')  # try to send a random known message to see if it connected to the right device
                    self._is_connected = True
                    break
                except:
                    pass
            if not self._is_connected:
                print('Not connected! Resource is not present in the system.')
                return
        else:
            print(usb_address)
            try:
                self._scope = self._resource_man.open_resource(usb_address)
            except Exception as e:
                traceback.print_exc()
                print('Not connected! Resource is not present in the system.')
                return

        self._nchan = len(active_channels)
        self._memory = memory
        #self._scope.timeout = 10000

        # "Initial configuration settings will start from here"
        self._scope.write('DATA:SOU ' + ','.join([f'CH{chan_}' for chan_ in active_channels]))

        # "Set 1byte=8bit accuracy"
        self._scope.write('DATA:WIDTH 1')
        # "Set the binary encoding method: here fastest is big endian"
        self._scope.write('DATA:ENC FAS')

        # "This is the voltage scale"
        self.ymult = float(self._scope.query('WFMPRE:YMULT?'))
        # "This is the voltage zero"
        self.yzero = float(self._scope.query('WFMPRE:YZERO?'))
        # "This is the voltage offset"
        self.yoff = float(self._scope.query('WFMPRE:YOFF?'))
        # "This is the time increment"
        self.xincr = float(self._scope.query('WFMPRE:XINCR?'))
        # "This is the time scale"
        self.xscale = float(self._scope.query('HORIZONTAL:MAIN:SCALE?'))
        # "This is the time offset"
        self.xoffset = float(self._scope.query('HORIZONTAL:MAIN:POSITION?'))
        # "This is the length of horizontal record"
        self.xlength = float(self._scope.query('HORIZONTAL:RECORDLENGTH?'))

        # "Can be used to force the length of the acqusition.. Default=Full Memory"
        self._scope.write('DATA:START 1')
        self._scope.write(f'DATA:STOP {self._memory}')

        self.change_channels(active_channels)
        self._is_connected = True
        print('Connected!')

    def readVolt_int(self, skip_y_values_check: bool = False) -> list[list[int]]:
        """
        Read the waveform on the scope
        Waveforms are returned concatenated

        Get the y infos
        Get the data in binary
        Use y info to transform it into Volts

        Returns:
            np array with nchan*memory points
        """
        datas = self.readVolt_bin(skip_y_values_check)

        for i in range(len(datas)):
            datas[i] = np.array(unpack('>{0}b'.format(int(len(datas[i]))), datas[i]))

        return datas

    def readVolt(self, skip_y_values_check: bool = False) -> list[list[float]]:
        """
        Read the waveform on the scope
        If multiple channels are selected the two waveforms are returned
        concatenated

        Get the y infos
        Get the data in binary
        Use y info to transform it into Volts

        Returns:
            np array with nchan*memory points
        """
        datas = self.readVolt_int(skip_y_values_check)

        for i in range(len(datas)):
            datas[i] = (datas[i] - self.yoff) * self.ymult + self.yzero  # converts from ints to volts

        return datas

    def readVolt_bin(self, skip_y_values_check: bool = False) -> list[list[int]]:
        """
        Read the waveform on the scope in binary form
        If multiple channels are selected the two waveforms are returned
        concatenated

        Returns:
            np array with nchan*memory points
        """
        if not skip_y_values_check:
            # "This is the voltage scale"
            self.ymult = float(self._scope.query('WFMPRE:YMULT?'))
            # "This is the voltage zero"
            self.yzero = float(self._scope.query('WFMPRE:YZERO?'))
            # "This is the voltage offset"
            self.yoff = float(self._scope.query('WFMPRE:YOFF?'))

        # "Query the scope for the reading"
        self._scope.write('CURVE?')
        # "Get the data in binary"
        successful_read = False
        initial_time = time_ns()
        while not successful_read:
            try:
                data = self._scope.read_raw()
                successful_read = True
            except:
                if time_ns() - initial_time > 3e9:  # if you wait more than 3s:
                    raise Exception('ERROR: Communication failed.')

        endTxLen = 1
        sourceHeaderLen = int((len(data) - self._nchan * self._memory - endTxLen) / (self._nchan))

        datas = [0] * self._nchan
        for i in range(0, self._nchan):
            datas[i] = data[(i + 1) * sourceHeaderLen + i * self._memory:(i + 1) * sourceHeaderLen + (i + 1) * self._memory]

        return datas

    def readTime(self):
        """
        Updates the x info stored in the class
        """

        # "This is the time scale"
        self.xscale = float(self._scope.query('HORIZONTAL:MAIN:SCALE?'))  # s
        # "This is the time offset"
        self.xoffset = float(self._scope.query('HORIZONTAL:MAIN:POSITION?'))  # 5.0000E+01, indicates the horizontal position of the waveform on the screen is set to 50%.
        # "This is the length of horizontal record"
        self.xlength = float(self._scope.query('HORIZONTAL:RECORDLENGTH?'))
        time = np.arange(0, self.xscale * 10, self.xscale * 10 / self._memory)  # *10 beacuse there are always 10 divisions on the oscilloscope
        time_unit: str = self._scope.query('HORIZONTAL:MAIN:UNITS?')
        return time, time_unit  # the time array, str containing the units (e.g.: 's', 'ms',...)

    def change_channels(self, chan_to_activate: list[int]):
        '''
            chan_to_activate: list of the channels you want to activate in range(1, number of channels of the oscilloscope)
        '''
        for chan in chan_to_activate:
            if chan <= 0:
                raise Exception(f'Invalid value {chan} set as channel.')

        self._nchan = len(chan_to_activate)

        self._scope.write('DATA:SOU ' + ','.join([f'CH{chan_}' for chan_ in chan_to_activate]))

        # "This is the voltage scale"
        self.ymult = float(self._scope.query('WFMPRE:YMULT?'))
        # "This is the voltage zero"
        self.yzero = float(self._scope.query('WFMPRE:YZERO?'))
        # "This is the voltage offset"
        self.yoff = float(self._scope.query('WFMPRE:YOFF?'))
        # "This is the time increment"
        self.xincr = float(self._scope.query('WFMPRE:XINCR?'))
        # "This is the time scale"
        self.xscale = float(self._scope.query('HORIZONTAL:MAIN:SCALE?'))
        # "This is the time offset"
        self.xoffset = float(self._scope.query('HORIZONTAL:MAIN:POSITION?'))
        # "This is the length of horizontal record"
        self.xlength = float(self._scope.query('HORIZONTAL:RECORDLENGTH?'))

    def get_time_info(self):
        self.xincr = float(self._scope.query('WFMPRE:XINCR?'))
        # "This is the time scale"
        self.xscale = float(self._scope.query('HORIZONTAL:MAIN:SCALE?'))
        # "This is the time offset"
        self.xoffset = float(self._scope.query('HORIZONTAL:MAIN:POSITION?'))
        # "This is the length of horizontal record"
        self.xlength = float(self._scope.query('HORIZONTAL:RECORDLENGTH?'))

        return [self.xincr, self.xscale, self.xoffset, self.xlength]

    def get_volt_info(self):
        # "This is the voltage scale"
        self.ymult = float(self._scope.query('WFMPRE:YMULT?'))
        # "This is the voltage zero"
        self.yzero = float(self._scope.query('WFMPRE:YZERO?'))
        # "This is the voltage offset"
        self.yoff = float(self._scope.query('WFMPRE:YOFF?'))

        return [self.ymult, self.yzero, self.yoff, self.xlength]

    def modify_vertical_scale(self, ch_scale):
        for c_s in ch_scale:
            self._scope.write(f'CH{c_s[0]}:SCAle {c_s[1]}')
        sleep(0.1)
    
    def change_acq_mode(self, avg=False, num_avg=1):
        if avg:
            self._scope.write('ACQuire:MODe AVErage')
            self._scope.write(f'ACQuire:NUMAVg {num_avg}')
        else:
            self._scope.write('ACQuire:MODe SAMple')
        sleep(0.1)
        return self._scope.query('ACQuire:MODe:ACTUal?')
    
    def return_measurement(self, meas_num=0):
        value = float(self._scope.query(f'MEASUrement:MEAS{meas_num}:VALue?'))
        unit = self._scope.query(f'MEASUrement:MEAS{meas_num}:UNIts?')
        type_ = self._scope.query(f'MEASUrement:MEAS{meas_num}:TYPe?')
        return value, unit[1:-2], type_[:-1]

    def wfm_acq(self, num_events, path):
        path = 'C:\\Users\\Tek_Local_Admin\\Tektronix\\TekScope\\SaveOnTrigger\\' + path

        self._scope.write('ACQuire:MODe SAMple')
        self._scope.write('ACQuire:SAMplingmode RT')
        self._scope.write('ACQuire:STOPAfter RUNSTop')

        self._scope.write('SAVe:WAVEform:FILEFormat INTERNal')
        #self._scope.write('SAVe:WAVEform:FILEFormat SPREADSHEETTxt')
        self._scope.write('SAVe:WAVEform:DATaSTARt 0')
        self._scope.write(f'SAVe:WAVEform:DATaSTARt {self._memory}')

        for i in range(num_events):
            num_acq = int(self._scope.query('ACQuire:NUMACq?'))
            self._scope.write('ACQuire:STATE RUN')
            while True:
                if int(self._scope.query('ACQuire:NUMACq?')) > num_acq:
                    break
            self._scope.write('ACQuire:STATE OFF')
            self._scope.write(f'SAVe:WAVEform ALL,"{path}\\{datetime.now().strftime("%Y%m%d_%H%M%S%f")}"')
        self._scope.write('ACQuire:STATE RUN')


    def disconnect(self):
        if self._is_connected:
            self._scope.close()
            self._is_connected = False

    def __del__(self):
        """
        Closes the connection before deleting the objects
        """
        self.disconnect()
        del self._scope
        del self._resource_man


if __name__ == '__main__':
    import matplotlib.pyplot as plt

    #osc = Oscilloscope(usb_address='TCPIP::192.168.50.205::INSTR', active_channels=[1,2], connect_at_start=True, memory=int(1e6))
    osc = Oscilloscope(usb_address='TCPIP::192.168.50.205::INSTR', active_channels=[1,2], connect_at_start=True, memory=int(1e6))
    v_scale = 12e-3
    osc.modify_vertical_scale([(1,v_scale),(2,v_scale)])

    '''voltages = osc.readVolt()
    time, unit = osc.readTime()
    if unit == 's':
        time = time * 1e3  # s to ms

    osc.disconnect()
    plt.figure()
    for voltage in voltages:
        plt.plot(time * 1e3, voltage)
    plt.xlabel('time [ms]')
    plt.ylabel('voltage [V]')
    plt.show()
'''