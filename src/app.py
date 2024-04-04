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

import hashlib
import hmac
import json
import os

from dotenv import load_dotenv
from flask import Flask, request

import servicenow
import util

# Absolute Paths
script_dir = os.path.dirname(os.path.abspath(__file__))
logs_path = os.path.join(script_dir, 'logs')
alert_configs = os.path.join(script_dir, 'alert_configurations')

# Global Flask flask_app
app = Flask(__name__)

# Load in Environment Variables
load_dotenv()
WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET')

# Set up file and console logging
logger = util.set_up_logging()

# Define Global Class Object (contains all API methods for SNOW)
snow = servicenow.ServiceNow(logger)


def alert_ticket_data(alert_type: str, alert_data: dict, ticket_data: dict) -> dict:
    """
    Generate Final ServiceNow ticket payload. Includes a combination of Raw Webhook Data and Custom Config
    :param alert_type: Device/Meeting type (changes raw alert data processing)
    :param alert_data: Raw Webhook Data
    :param ticket_data: Custom Config (modified and returned to be used as SNOW ticket data)
    :return: ServiceNow ticket data
    """
    # Set Short Description to that of Device Name
    ticket_data['short_description'] = alert_data['notificationAttributes']['deviceName']

    # Set Caller ID (caller ID set to account which authenticated if name not provided)
    ticket_data['caller_id'] = snow.get_caller_id(ticket_data['caller_id'])

    # If Alert Type is for a Meeting, valuable insight included in webhook summary, separate any custom description
    # from webhook summary
    if alert_type == "meeting":
        ticket_data[
            'description'] = f"Custom Description:\n{ticket_data['description']}\nRaw Description:\n{alert_data['summary']}"

    # Always Add Control Hub Meta-Data
    ticket_data['description'] += '\n\nControlHub Alert MetaData:' + '\n' + json.dumps(
        alert_data['notificationAttributes'], indent=4)

    return ticket_data


def handle_device_alerts(alert_data: dict):
    """
    Process "Device" type alerts from Control Hub. Perform different parsing based on sub-type of event, and specific issue type (if relevant)
    :param alert_data: Raw Webhook Alert Data
    """
    # Static Configurations Base Folder Path
    alert_config_devices = os.path.join(alert_configs, 'devices')

    # Handle Device Alert SubType (mark the issues in different ways)
    alert_type = alert_data.get('subType', '')
    alert_issue_type = []

    if alert_type == "Offline and online events":
        alert_config_subtype = os.path.join(alert_config_devices, 'offline_online')

        # Obtain Alert Issue Type (issue code not present, look for 'online' or 'offline' in summary)
        summary = alert_data.get('summary', "")
        if 'online' in summary.lower():
            alert_issue_type = ['online']
        elif 'offline' in summary.lower():
            alert_issue_type = ['offline']
        else:
            logger.error(f"Unknown alert issue type. Neither 'online' or 'offline' is in {summary.lower()}")
            return

    elif alert_type == "Issue detected or resolved events":
        alert_config_subtype = os.path.join(alert_config_devices, 'issues')

        # Obtain Alert Issue Type (issue code - based on alert documentation in readme)
        issues = alert_data.get('issues', {})
        if 'detected' in issues:
            alert_issue_type = issues['detected']
        else:
            logger.error(
                f"Unable to determine specific device issues... `issues` and/or `detected` field not present.'")
            return
    else:
        logger.error(f"Unsupported Device Alert Type: {alert_type}, skipping ticket creation...")
        return

    # Retrieve Alert Configuration File
    config_file = os.path.join(alert_config_subtype, 'config.json')
    with open(config_file, 'r') as fp:
        toplevel_configs = json.load(fp)

    # Iterate through issues in payload, create SNOW tickets if possible/necessary
    for issue_type in alert_issue_type:
        # Check if issue type supported and defined
        if issue_type in toplevel_configs:
            # We found it!
            logger.info(
                f"Received and have configuration for: [blue]`Device`[/], [blue]`{alert_type}`[/] (Alert Type), [blue]`{issue_type}`[/] (Sub-Issue)")
            ticket_config = toplevel_configs[issue_type]

            # Generate Ticket Data
            ticket_data = alert_ticket_data("device", alert_data, ticket_config)

            # Send SNOW Ticket with Ticket Data
            snow.create_service_now_ticket(ticket_data, alert_data['notificationId'])
        else:
            logger.error(
                f"Unsupported Device Alert Sub-Type: '{alert_issue_type}', skipping ticket creation for this issue...")
            continue


def handle_meetings_alerts(alert_data: dict):
    """
    Process "Live Meeting" type alerts from Control Hub. Perform different parsing based on sub-type of event
    :param alert_data: Raw Webhook Alert Data
    """
    # Static Configurations Base Folder Path
    alert_config_meetings = os.path.join(alert_configs, 'meetings')

    # Handle Meeting Alert SubType (mark the issues in different ways)
    alert_type = alert_data.get('subType', '')

    if alert_type == "Device live meeting alert":
        alert_config_subtype = os.path.join(alert_config_meetings, 'device_live_meeting')
    else:
        logger.error(f"Unsupported Device Alert Type: {alert_type}, skipping ticket creation...")
        return

    # Retrieve Alert Configuration File
    config_file = os.path.join(alert_config_subtype, 'config.json')
    with open(config_file, 'r') as fp:
        toplevel_configs = json.load(fp)

    # Should only be one issue type defined (keeping with standard structure of other alerts)
    if "live_meeting_alert" in toplevel_configs:
        logger.info(
            f"Received and have configuration for: [blue]`Meetings`[/], [blue]`{alert_type}`[/] (Alert Type), [blue]`Live Meeting Alert`[/] (Sub-Issue)")

        ticket_config = toplevel_configs["live_meeting_alert"]

        # Generate Ticket Data
        ticket_data = alert_ticket_data("meeting", alert_data, ticket_config)

        # Send SNOW Ticket with Ticket Data
        snow.create_service_now_ticket(ticket_data, alert_data['notificationId'])
    else:
        logger.error(f"No configuration found for `live_meeting_alert`, skipping ticket creation...")
        return


@app.route("/", methods=["GET", "POST"])
def control_hub_alerts():
    """
    The webhooks will send information to this web server, and this function
    provides the logic to parse the Control Hub alert (and generate a SNOW Incident)
    """
    # If the method is POST, then an alert has sent a webhook to the web server
    if request.method == "POST":
        logger.info("Webhook Alert Detected:")

        # Webhook Secret Check
        hashed = hmac.new(WEBHOOK_SECRET.encode(), request.data, hashlib.sha1)
        validatedSignature = hashed.hexdigest()

        if validatedSignature != request.headers.get('X-Spark-Signature'):
            logger.error("Webhook Secret invalid! Skipping...")
            return "Webhook Secret invalid! Skipping..."

        # Retrieve the json data from the request - contains alert info
        webhook_data = request.json
        logger.info(webhook_data)

        # Extract ControlHub "Service" for proper routing
        alert_data = webhook_data.get('data', {})
        alert_service = alert_data.get('type', 'Unknown')

        # Handle "Device" Alerts (Online/Offline, Issues)
        if alert_service == "Devices":
            handle_device_alerts(alert_data)
        # Handle "Meetings" Alerts (Live Meeting Monitoring)
        elif alert_service == "Meetings":
            handle_meetings_alerts(alert_data)
        else:
            # Unsupported Alert Service Type
            logger.error(
                f'[red]Error: Unsupported Alert Service Type: {alert_service}[/]. Please see README for a list of supported alerts.')

    return 'Webhook receiver is running - check the terminal for alert information'


if __name__ == '__main__':
    app.run(debug=False, port=5000, host='0.0.0.0')
