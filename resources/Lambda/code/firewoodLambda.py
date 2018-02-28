'''
Created on Feb 18, 2018

@author: joey whelan
'''

import dateutil.parser
import datetime
import time
import os
import json
from smartystreets_python_sdk import StaticCredentials, exceptions, ClientBuilder
from smartystreets_python_sdk.us_street import Lookup

FIREWOOD_TYPES = ['split', 'logs']
PRICE_PER_CORD = {'split' : 200, 'logs' : 150}
DELIVERY_ZIP = '80863'
AUTH_ID = 'yourId'
AUTH_TOKEN = 'yourToken'


class LexHandler(object):
    '''
    Class containing functionality to validate and fulfill AWS Lex interactions.
    '''       
    def __init__(self, event):
        '''Sets instance variables.
        
        Args:
            self: Instance reference 
            event: Lamba event object from Lex
        
        Returns:
            None
        
        Raises:
            None
        '''
        self.event= event
        self.name = event['currentIntent']['name']
        self.userId = event['userId']
        self.slots = event['currentIntent']['slots']
        self.source = event['invocationSource']
        self.sessionAttributes = event['sessionAttributes']
    
    def __isValidDeliveryStreet(self, deliveryStreet, deliveryZip):  
        '''Performs a validity check of a given street address and zip code pair.  Leverages the SmartyStreets 
        address verification service.
        
        Args:
            self: Instance reference 
            deliveryStreet: String containing the street address
            deliveryZip: String containing the zip code
        
        Returns:
            Boolean indicating whether the street address is valid
        
        Raises:
            None
        '''
        if deliveryStreet and deliveryZip:
            credentials = StaticCredentials(AUTH_ID, AUTH_TOKEN)
            client = ClientBuilder(credentials).build_us_street_api_client()
            lookup = Lookup()
            lookup.street = deliveryStreet
            lookup.zipcode = deliveryZip
            try:
                client.send_lookup(lookup)
            except exceptions.SmartyException:
                return False
            
            if lookup.result:
                return True
            else:
                return False
        else:
            return False
    
    def __isValidDeliveryDate(self, deliveryDate):
        '''Verifies a Lex-inputed delivery date.  Allows for dates from 1-30 days after current date.
        
        Args:
            self: Instance reference 
            deliveryDate: String date object
        
        Returns:
            Boolean indicating whether the date is valid
        
        Raises:
            None
        '''
        try:
            if deliveryDate:
                date = dateutil.parser.parse(deliveryDate).date()
                today = datetime.date.today()
                tomorrow = today + datetime.timedelta(days = 1)
                monthFromNow = today + datetime.timedelta(days = 30) 
                if date >= tomorrow and date <= monthFromNow:
                    return True
                else:
                    return False
            else:
                return False
        except ValueError:
            return False

    def __isValidDeliveryTime(self, deliveryTime):
        '''Verifies a Lex-inputed delivery time.  Allows for times from 9 am to 5 pm.
        
        Args:
            self: Instance reference 
            deliveryDate: String time object
        
        Returns:
            Boolean indicating whether the time is valid
        
        Raises:
            None
        '''
        try:   
            if deliveryTime and len(deliveryTime) == 5:
                hour, minute = deliveryTime.split(':')
                hour = int(hour)
                minute = int(minute)
                if hour >= 9 and hour <= 17 and minute >= 0 and minute <= 59:
                    return True
                else:
                    return False
            else:
                return False
        except ValueError:
            return False            
    
    def __isValidDeliveryZip(self, deliveryZip):
        '''Verifies a Lex-inputed zip code.  Allows for only 1 valid zip.
        
        Args:
            self: Instance reference 
            deliveryZip: String zip code object
        
        Returns:
            Boolean indicating whether the zip is valid
        
        Raises:
            None
        '''
        if deliveryZip == DELIVERY_ZIP:
            return True
        else:
            return False
                    
    def __isValidFirewoodType(self, firewoodType):
        '''Verifies a Lex-inputed firewood request type.  Allows for split or log types.
        
        Args:
            self: Instance reference 
            firewoodType: String indicating requested firewood type
        
        Returns:
            Boolean indicating whether the type is valid
        
        Raises:
            None
        '''
        if firewoodType and firewoodType.lower() in FIREWOOD_TYPES:
            return True
        else:
            return False
    
    def __isValidNumberCords(self, numberCords):
        '''Verifies a Lex-inputed number of cords.  Allows for 1 to 3 cords.
        
        Args:
            self: Instance reference 
            numberCords: String indicating requested number of cords
        
        Returns:
            Boolean indicating whether the cord value is valid
        
        Raises:
            None
        '''
        try:
            if numberCords:
                cords = int(numberCords)
                if cords >=1 and cords <= 3:
                    return True
                else:
                    return False
            else:
                return False
        except ValueError:
            return False
       
    def __processOrderFirewood(self):
        '''Main Lex processing routine.  Processes both dialog verification and fulfillment events from Lex.
        
        Args:
            self: Instance reference 
        
        Returns:
            Formatted Lambda response object (dict) for consumption by AWS Lex
        
        Raises:
            None
        '''
        firewoodType = self.slots['FirewoodType']
        numberCords = self.slots['NumberCords']
        deliveryDate = self.slots['DeliveryDate']
        deliveryTime = self.slots['DeliveryTime']
        deliveryStreet = self.slots['DeliveryStreet']
        deliveryZip = self.slots['DeliveryZip']
        resp = None
    
        if self.source == 'DialogCodeHook':
            allValid, firstInvalidSlot, message = self.__validateOrderFirewood(firewoodType, numberCords, deliveryDate, \
                                                                               deliveryTime, deliveryStreet, deliveryZip)
            if allValid:
                price = '$' + str(PRICE_PER_CORD[firewoodType] * int(numberCords))
                if self.sessionAttributes:
                    self.sessionAttributes['Price'] = price
                else:
                    self.sessionAttributes = {'Price' : price}
                resp = {
                                'sessionAttributes': self.sessionAttributes,
                                'dialogAction': {
                                    'type': 'Delegate',
                                    'slots': self.slots
                                }
                        }
            else:
                self.slots[firstInvalidSlot] = None
                resp = {
                            'sessionAttributes': self.sessionAttributes,
                            'dialogAction': {
                                                'type': 'ElicitSlot',
                                                'intentName': self.name,
                                                'slots': self.slots,
                                                'slotToElicit': firstInvalidSlot,
                                                'message': { 'contentType': 'PlainText',
                                                            'content' : message
                                                        }
                                            }
                        }
        else:   
            msg = 'Thanks, your order for {} cords of {} firewood ' + \
                'has been placed and will be delivered to {} on {} at {}.  ' + \
                'We will need to collect a payment of {} upon arrival.'
            resp = {
                    'sessionAttributes': self.sessionAttributes,
                    'dialogAction': {
                                        'type': 'Close',
                                        'fulfillmentState': 'Fulfilled',
                                        'message': {'contentType': 'PlainText',
                                                    'content': msg.format(numberCords, firewoodType, deliveryStreet, \
                                                            deliveryDate, deliveryTime, self.sessionAttributes['Price'])
                                                    }
                                    }
                    }
        return resp
    
    def __agentTransfer(self):
        if self.source == 'FulfillmentCodeHook':
            if self.sessionAttributes:
                self.sessionAttributes['Agent'] = 'True';
            else:
                self.sessionAttributes = {'Agent' : 'True'}
            msg = 'Transferring you to an agent now.'
           
            resp = {
                    'sessionAttributes': self.sessionAttributes,
                    'dialogAction': {
                                        'type': 'Close',
                                        'fulfillmentState': 'Fulfilled',
                                        'message': {
                                            'contentType': 'PlainText',
                                            'content': msg
                                        }
                                    }
                    }
            return resp
     
    def __validateOrderFirewood(self, firewoodType, numberCords, deliveryDate, deliveryTime, deliveryStreet, deliveryZip):
        '''Main Lex input data validation routine.  Processes both dialog verification and fulfillment events from Lex.
        
        Args:
            self: Instance reference 
        
        Returns:
            Boolean: indicates whether errors were found
            SlotName:  Name of slot where error was found
            Message:  Input prompt and/or error message
        
        Raises:
            None
        '''
        if not self.__isValidFirewoodType(firewoodType):
            message = 'Our firewood options are split or logs.  Which type would you prefer?'
            return False, 'FirewoodType', message
            
        if not self.__isValidNumberCords(numberCords):
            message = 'Delivery quantity options are 1, 2, or 3 cords.  How many cords do you need?'
            return False, 'NumberCords', message
        
        if not self.__isValidDeliveryDate(deliveryDate):
            message = 'Available delivery dates are from tomorrow to a month from today.  What date would you prefer?'
            return False, 'DeliveryDate', message
        
        if not self.__isValidDeliveryTime(deliveryTime):
            message = 'Available delivery times are from 9 am to 5 pm.  What time would you prefer?'
            return False, 'DeliveryTime', message

        if not self.__isValidDeliveryZip(deliveryZip):
            message = 'Delivery is available only within the {} zip code.  What is your delivery zip code?'.format(DELIVERY_ZIP)
            return False, 'DeliveryZip', message
        
        if not self.__isValidDeliveryStreet(deliveryStreet, deliveryZip):
            message = ''
            if deliveryStreet:
                message = 'The street address you provided {} does not appear to be valid.  '.format(deliveryStreet)
            message = message + 'Please provide a street address for delivery.'
            return False, 'DeliveryStreet', message
        
        return True, None, None
      
    def respond(self):
        '''Public method that calls private methods for data verification and fulfillment
        
        Args:
            self: Instance reference 
        
        Returns:
            Formatted Lambda response object (dict) for consumption by AWS Lex
        
        Raises:
            None
        '''
        if self.name == 'OrderFirewood':
            return self.__processOrderFirewood();
        elif self.name == 'RequestAgent':
            return self.__agentTransfer();
        else:
            raise Exception('Intent with name ' + self.name + ' not supported')

def lambda_handler(event, context):
    '''Main handler method called externally by AWS Lex
        
        Args:
            event: Lex event object.
            context - lambda context.  unused
        
        Returns:
            Formatted Lambda response object (dict) for consumption by AWS Lex
        
        Raises:
            None
    '''
    handler = LexHandler(event)
    os.environ['TZ'] = 'America/Denver'
    time.tzset()
    return handler.respond()

if __name__ == '__main__':
    with open(os.path.join('../TestEvents','orderFirewoodDialogTest.json'), 'r') as file:
        testEvent = json.load(file)
        resp = lambda_handler(testEvent, None)
        print(json.dumps(resp, indent=4, sort_keys=True))
    
