'''
Created on Feb 27, 2018

@author: joey whelan
'''
import boto3
import configparser
import os
import json
import logging
from datetime import date, datetime
import time

logger = logging.getLogger('awsbot')
hdlr = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(module)-8s %(funcName)-8s %(message)s')
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(logging.DEBUG)


class AWSBot(object):
    '''
    Class containing all the functionality to build, test, and destroy a chatbot on AWS Lex programmatically 
    via the AWS SDK for Python.
    '''   
    def __init__(self, config):
        '''Fetches user options and sets instance variables.
        
        Args:
            self: Instance reference 
            filename: Name of configuration file
        
        Returns:
            None
        
        Raises:
            NoSectionError: Raised if section is missing in config file
            NoOptionError: Raised if option is missing in config file
        '''
        logger.debug('Entering')
        self.bot, self.slots, self.intents, self._lambda, self.permissions = self.__loadResources(config)
        self.buildClient = boto3.client('lex-models')
        self.testClient = boto3.client('lex-runtime')
        self.lambdaClient = boto3.client('lambda')
        logger.debug('Exiting')  
        
    def __dateSerializer(self, obj):
        '''Custom string serializer for date/datetime objects
        
        Args:
            self: Instance reference 
            obj: Object from JSON parse
        
        Returns:
            ISO-formatted date string
        
        Raises:
            TypeError: Raised if the object is not of type datetime or date
        '''
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError ("Type %s not serializable" % type(obj))

    def __loadResources(self, config):
        '''Loads AWS object configurations from JSON files
        
        Args:
            self: Instance reference 
            config: Name of directory containing the JSON files
        
        Returns:
            Dict config objects the bot, intents, slots, lambda codehook, and lambda permission
        
        Raises:
            None
        '''
        logger.debug('Entering')
        cfgParser = configparser.ConfigParser()
        cfgParser.optionxform = str
        cfgParser.read(config)
        
        filename = cfgParser.get('AWSBot', 'botJsonFile')
        with open(filename, 'r') as file:
            bot = json.load(file)
        
        slotsDir = cfgParser.get('AWSBot', 'slotsDir')
        slots = []
        for root,_,filenames in os.walk(slotsDir):
            for filename in filenames:
                with open(os.path.join(root,filename), 'r') as file:
                    jobj = json.load(file)
                    slots.append(jobj)
                    logger.debug(json.dumps(jobj, indent=4, sort_keys=True))
                     
        intentsDir = cfgParser.get('AWSBot', 'intentsDir')
        intents = []
        for root,_,filenames in os.walk(intentsDir):
            for filename in filenames:
                with open(os.path.join(root,filename), 'r') as file:
                    jobj = json.load(file)
                    intents.append(jobj)
                    logger.debug(json.dumps(jobj, indent=4, sort_keys=True))
        
        filename = cfgParser.get('AWSBot', 'lambdaJsonFile')
        dirname = os.path.dirname(filename)
        with open(filename, 'r') as file:
            _lambda = json.load(file)
        with open(os.path.join(dirname,_lambda['Code']['ZipFile']), 'rb') as zipFile:
            zipBytes = zipFile.read()
        _lambda['Code']['ZipFile'] = zipBytes    
        
        permissionsDir = cfgParser.get('AWSBot', 'permissionsDir')
        permissions = []
        for root,_,filenames in os.walk(permissionsDir):
            for filename in filenames:
                with open(os.path.join(root,filename), 'r') as file:
                    jobj = json.load(file)
                    permissions.append(jobj)
                    logger.debug(json.dumps(jobj, indent=4, sort_keys=True))      
        return bot, slots, intents, _lambda, permissions
        
    def __buildLambda(self):
        '''Builds the AWS Lambda object via a zipped python code package.  Adds a permission to be called from the Lex intent
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        resp = self.lambdaClient.create_function(**self._lambda)
        logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        
        for permission in self.permissions:
            resp = self.lambdaClient.add_permission(**permission)
            logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        '''
        resp = self.lambdaClient.add_permission(**self.permission)
        logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        '''
        logger.debug('Exiting')
    
    def __buildSlotTypes(self):
        '''Builds the AWS Lex slot objects via a JSON config file
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        for slot in self.slots:
            resp = self.buildClient.put_slot_type(**slot)
            logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        logger.debug('Exiting')
        
    def __buildIntents(self):
        '''Builds the AWS Lex intent objects via a JSON config file
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        for intent in self.intents:
            resp = self.buildClient.put_intent(**intent)
            logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        logger.debug('Exiting')
        
    def __buildBot(self):
        '''Builds the AWS Lex bot object via a JSON config file.  Loops/delays while waiting for the bot object build 
        to be completed on AWS.
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        self.buildClient.put_bot(**self.bot)
        complete = False
        for _ in range(20):
            time.sleep(20)
            resp = self.buildClient.get_bot(name=self.bot['name'], versionOrAlias='$LATEST')
            logger.debug(resp['status'])
            if resp['status'] == 'FAILED':
                logger.debug('***Bot Build Failed***')
                logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
                complete = True
                break
            elif resp['status']  == 'READY':
                logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
                complete = True
                break
                   
        if not complete:
            logger.debug('***Bot Build Timed Out***')
            logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer)) 
        logger.debug('Exiting')
    
    def __destroySlotTypes(self):
        '''Deletes the AWS Lex slot types objects.  
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')  
        for slot in self.slots:
            try:
                resp = self.buildClient.delete_slot_type(name=slot['name'])
                logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
            except Exception as err:
                logger.debug(err)
        logger.debug('Exiting')
            
    def __destroyIntents(self):
        '''Deletes the AWS Lex intent objects.  
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        for intent in self.intents:
            try:
                resp = self.buildClient.delete_intent(name=intent['name'])
                logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
            except Exception as err:
                logger.debug(err)
            time.sleep(5)  #artificial delay to allow the operation to be completed on AWS
        logger.debug('Exiting')
    
    def __destroyLambda(self):
        '''Deletes the AWS Lambda object.  
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        try:
            resp = self.lambdaClient.delete_function(FunctionName=self._lambda['FunctionName'])
            logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        except Exception as err:
            logger.debug(err)
        logger.debug('Exiting')
    
    def __destroyBot(self):
        '''Deletes the AWS Lex bot object.  
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        try:
            resp = self.buildClient.delete_bot(name=self.bot['name'])
            logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer))
        except Exception as err:
            logger.debug(err)
        time.sleep(5) #artificial delay to allow the operation to be completed on AWS
        logger.debug('Exiting')
    
    def build(self):
        '''Public function that calls private functions to build the various AWS Lex/Lambda objects.  
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')  
        self.__buildLambda()
        self.__buildSlotTypes()
        self.__buildIntents()
        self.__buildBot()
    
        logger.debug('Exiting')
    
    def test(self, msg):
        '''Public function that provides the ability to send a test text into the Lex bot
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        params = {
                    'botAlias': '$LATEST',
                    'botName': self.bot['name'],
                    'inputText': msg,
                    'userId': 'fred',
                }
        resp = self.testClient.post_text(**params)
        logger.debug(json.dumps(resp, indent=4, sort_keys=True, default=self.__dateSerializer)) 
        logger.debug('Exiting')
        
    def destroy(self):
        '''Public function that calls private functions to delete the various AWS Lex/Lambda objects.  
        
        Args:
            self: Instance reference 

        Returns:
            None
        
        Raises:
            Various AWS boto3 exceptions
        '''    
        logger.debug('Entering')
        self.__destroyBot()
        self.__destroyIntents()
        self.__destroySlotTypes()
        self.__destroyLambda()
        logger.debug('Exiting')
        

if __name__ == '__main__':
    bot = AWSBot('awsbot.cfg')
    bot.build()
    #bot.test('I want to order 2 cords of split firewood to be delivered at 1 pm on tomorrow to 900 Tamarac Pkwy 80863')
    #bot.destroy()
    
