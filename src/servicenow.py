#!/usr/bin/env python3
"""
Copyright (c) 2024 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Trevor Maco <tmaco@cisco.com>"
__copyright__ = "Copyright (c) 2024 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

import logging
import os

import requests
from dotenv import load_dotenv

# Load in Environment Variables
load_dotenv()
SERVICENOW_INSTANCE = os.getenv('SERVICENOW_INSTANCE')
SERVICENOW_USERNAME = os.getenv('SERVICENOW_USERNAME')
SERVICENOW_PASSWORD = os.getenv('SERVICENOW_PASSWORD')


class ServiceNow:
    """
    ServiceNow API Class, includes various methods for interacting with ServiceNow REST API
    """

    def __init__(self, logger: logging.Logger):
        """
        Initialize the ServiceNow class
        """
        self.headers = {"Content-Type": "application/json", "Accept": "application/json"}
        self.auth = (SERVICENOW_USERNAME, SERVICENOW_PASSWORD)
        self.logger = logger

    def get_caller_id(self, caller_id_name: str) -> str:
        """
        Get SNOW Caller ID for Incident
        """
        # Get ServiceNow caller (use authenticator by default if not specified)
        if caller_id_name == '':
            caller_id_name = SERVICENOW_USERNAME

        servicenow_caller = requests.get(
            SERVICENOW_INSTANCE + "/api/now/table/sys_user?sysparm_query=user_name%3D" + caller_id_name,
            auth=self.auth, headers=self.headers).json()['result'][0]['name']

        return servicenow_caller

    def create_service_now_ticket(self, ticket_data: dict, notification_id: str):
        """
        Create ServiceNow Ticket using ticket_data (includes data from webhook and static files)
        """
        self.logger.info(f'Creating Service Now Ticket for ControlHub Webhook Alert: {notification_id}')

        # Create new ServiceNow Ticket using ticket_data
        response = requests.post(SERVICENOW_INSTANCE + "/api/now/table/incident", auth=self.auth, headers=self.headers,
                                 json=ticket_data)

        if response.ok:
            ticket_details = response.json()
            self.logger.info(
                f'A New ticket was created with Incident Number: {ticket_details["result"]["number"]}.\n Response: {response}')
        else:
            self.logger.error(f'Failed to create Service Now Ticket: {response.text}')
