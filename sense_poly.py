#!/usr/bin/env python3

"""
This is a NodeServer for Sense Monitoring written by automationgeek (Jean-Francois Tremblay)  
based on the NodeServer template for Polyglot v2 written in Python2/3 by Einstein.42 (James Milne) milne.james@gmail.com.
Using this Exploratory Work done from extracting Sense Monitoring Data using Python Library by scottbonline https://github.com/scottbonline/sense
"""

import udi_interface
import time
import json
import sys
from copy import deepcopy
from threading import Thread
from sense_energy import Senseable

LOGGER = udi_interface.LOGGER
VERSION = '3.0.2'

def get_profile_info(logger):
    pvf = 'profile/version.txt'
    try:
        with open(pvf) as f:
            pv = f.read().replace('\n', '')
    except Exception as err:
        logger.error('get_profile_info: failed to read  file {0}: {1}'.format(pvf,err), exc_info=True)
        pv = 0
    f.close()
    return { 'version': pv }
    
class Controller(udi_interface.Node):

    def __init__(self, polyglot, primary, address, name):
        super(Controller, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.name = 'Sense'
        self.email = None
        self.password = None
        self.sense = None
        self.discovery_thread = None
        self.hb = 0
        self.queryON = False

        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)

        polyglot.ready()
        polyglot.addNode(self)
        
    def parameterHandler(self, params):
        self.poly.Notices.clear()
        try:
            if 'email' in params and self.email is None:
                self.email = params['email']
            else:
                self.poly.Notices['email'] = 'Please provide email address in custom parameters'
                LOGGER.error('Please provide email address in custom parameters')
                return False
            
            if 'password' in params and self.password is None:
                self.password = params['password']
            else:
                self.poly.Notices['pass'] = 'Please provide password in custom parameters'
                LOGGER.error('Please provide password in custom parameters')
                return False
            
            if self.password != "" and self.email != "":
                self.heartbeat()
                self.connectSense()
                self.discover()
            else:
                self.poly.Notices['cfg'] = 'Please provide email address and password'
            
        except Exception as ex:
            LOGGER.error('Error starting Sense NodeServer: %s', str(ex))
            return False
        

    def start(self):
        LOGGER.info('Started Sense NodeServer version %s', str(VERSION))

    def poll(self, polltype):
        if 'shortPoll' in polltype:
            try :
                if self.discovery_thread is not None:
                    if self.discovery_thread.is_alive():
                        LOGGER.debug('Skipping shortPoll() while discovery in progress...')
                        return
                    else:
                        self.discovery_thread = None
                self.update()
            except Exception as ex:
                LOGGER.error('Error shortPoll: %s', str(ex))
        else:
            try :
                if self.discovery_thread is not None:
                    if self.discovery_thread.is_alive():
                        LOGGER.debug('Skipping longPoll() while discovery in progress...')
                        return
                    else:
                        self.discovery_thread = None
                self.connectSense()
                self.heartbeat()
            except Exception as ex:
                LOGGER.error('Error longPoll: %s', str(ex))
        
    def query(self):
        for node in self.poly.nodes():
            node.reportDrivers()
            
    def update(self) :       
        try:
            self.sense.update_realtime()
            self.sense.update_trend_data()
            
            self.setDriver('ST', 1)
            self.setDriver('CPW', int(self.sense.active_power) if self.sense.active_power != None else 0 )
            self.setDriver('GV6', int(self.sense.active_solar_power) if self.sense.active_solar_power != None else 0 ) 
            self.setDriver('GV7', int(self.sense.daily_usage) if self.sense.daily_usage != None else 0 )  
            self.setDriver('GV8', int(self.sense.daily_production) if self.sense.daily_production != None else 0 )
            self.setDriver('GV9', int(self.sense.weekly_usage) if self.sense.weekly_usage != None else 0 )
            self.setDriver('GV10', int(self.sense.weekly_production) if self.sense.weekly_production != None else 0 )
            self.setDriver('GV11', int(self.sense.monthly_usage) if self.sense.monthly_usage != None else 0 )
            self.setDriver('GV12', int(self.sense.monthly_production) if self.sense.monthly_production != None else 0 )
            self.setDriver('GV13', int(self.sense.yearly_usage) if self.sense.yearly_usage != None else 0 )  
        except Exception as ex:
            LOGGER.error('query, unable to retrieve Sense Monitor usage: %s', str(ex))
        
        for node in self.poly.nodes():
            if  node.queryON == True :
                node.update()

    def heartbeat(self):
        self.l_info('heartbeat','hb={}'.format(self.hb))
        if self.hb == 0:
            self.reportCmd("DON",2)
            self.hb = 1
        else:
            self.reportCmd("DOF",2)
            self.hb = 0
    
    def l_info(self, name, string):
        LOGGER.info("%s:%s: %s" %  (self.id,name,string))
    
    def connectSense(self):
        try:
            self.sense = Senseable()
            self.sense.authenticate(self.email,self.password)   
        except Exception as ex:
            LOGGER.error('Unable to connect to Sense API: %s', str(ex))
    
    def discover(self, *args, **kwargs):    
        if self.discovery_thread is not None:
            if self.discovery_thread.is_alive():
                LOGGER.info('Discovery is still in progress')
                return
        self.discovery_thread = Thread(target=self._discovery_process)
        self.discovery_thread.start()
    
    def _discovery_process(self):
        for device in self.sense.get_discovered_device_data():
            if device is not None: 
                try :
                    if device["tags"]["DeviceListAllowed"] == "true" and device['name'] != "Always On" and device['name'] != "Unknown" :
                        self.poly.addNode(SenseDetectedDevice(self.poly, self.address, device['id'], device['name']))                    
                except Exception as ex: 
                    LOGGER.error('discover device name: %s', str(device['name']))
    
    def runDiscover(self,command):
        self.discover()
    
    def delete(self):
        LOGGER.info('Deleting Sense Node Server')
        
    id = 'controller'
    commands = {
                    'QUERY': query,
                    'DISCOVERY' : runDiscover
                }
    drivers = [{'driver': 'ST', 'value': 1, 'uom': 2},
               {'driver': 'CPW', 'value': 0, 'uom': 73},
               {'driver': 'GV6', 'value': 0, 'uom': 73},
               {'driver': 'GV7', 'value': 0, 'uom': 30},
               {'driver': 'GV8', 'value': 0, 'uom': 30},
               {'driver': 'GV9', 'value': 0, 'uom': 30},
               {'driver': 'GV10', 'value': 0, 'uom': 30},
               {'driver': 'GV11', 'value': 0, 'uom': 30},
               {'driver': 'GV12', 'value': 0, 'uom': 30},
               {'driver': 'GV13', 'value': 0, 'uom': 30},
               {'driver': 'GV14', 'value': 0, 'uom': 30}]
    
class SenseDetectedDevice(udi_interface.Node):

    def __init__(self, controller, primary, address, name):
        newaddr = address.lower().replace('dcm','').replace('-','')
        super(SenseDetectedDevice, self).__init__(controller, primary,newaddr, name)
        self.parent = controller.getNode(primary)
        self.queryON = True
        self.nameOrig = name
        self.addressOrig = address
        
        self.setDriver('GV1', 0)
        self.setDriver('GV2', 0)
        self.setDriver('GV3', 0)
        self.setDriver('GV4', 0)
        self.setDriver('GV5', 0)
          
  
    def query(self):
        self.reportDrivers()

    def update(self):
        try :
            # Device Power Status
            val = 0
            for x in self.parent.sense.active_devices:
                if x == self.nameOrig:
                    val = 100
                    break
            self.setDriver('ST',val)
                    
            # Device Info
            deviceInfo = self.parent.sense.get_device_info(self.addressOrig)
            if deviceInfo is not None:
                    if 'usage' in deviceInfo : 
                        self.setDriver('GV1', int(deviceInfo['usage']['avg_monthly_runs']))
                        self.setDriver('GV5', int(deviceInfo['usage']['avg_watts']))
                        self.setDriver('GV2', int(deviceInfo['usage']['avg_monthly_KWH']))
                        self.setDriver('GV3', int(deviceInfo['usage']['current_month_runs']))
                        self.setDriver('GV4', int(deviceInfo['usage']['current_month_KWH']))
        except Exception as ex:
            LOGGER.error('updateDevice: %s', str(ex))
            
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 78},
               {'driver': 'GV5', 'value': 0, 'uom': 73}, 
               {'driver': 'GV1', 'value': 0, 'uom': 56}, 
               {'driver': 'GV2', 'value': 0, 'uom': 30}, 
               {'driver': 'GV3', 'value': 0, 'uom': 56}, 
               {'driver': 'GV4', 'value': 0, 'uom': 30} ]

    id = 'SENSEDEVICE'
    commands = {
                    'QUERY': query          
                }
    
if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start(VERSION)
        polyglot.updateProfile()
        polyglot.setCustomParamsDoc()
        Controller(polyglot, 'controller', 'controller', 'SenseNodeServer')
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
