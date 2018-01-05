# Check if we are running on Google App Engine
def _is_gae():
   import httplib
   return 'appengine' in str(httplib.HTTP)

# Check if we are running on appengine
if (_is_gae()):
    # appengine_config.py
    from google.appengine.ext import vendor

    # Add any libraries install in the "lib" folder.
    vendor.add('lib')

import contextlib
import json
import os
import urllib2
import webapp2
from twilio.rest import TwilioRestClient
from ics import Calendar
from datetime import datetime

# Calls you when your sites go down.
# License is GPLv3.
# Author: Eric Jiang <eric@doublemap.com>

TWILIO_SID = os.environ['TWILIO_SID']
TWILIO_TOKEN = os.environ['TWILIO_TOKEN']
TWILIO_FROM = os.environ['TWILIO_FROM']
CALLEES = os.environ['CALLEES'].split(',')

ICAL_PARSE_FROM_URL = os.environ['ICAL_PARSE_FROM_URL'].lower() in ['true', '1', 't', 'y', 'yes']
ICAL_URL = os.environ['ICAL_URL']

UPTIME_ROBOT_KEY = os.environ['UPTIME_ROBOT_KEY']
UPTIME_ROBOT = "http://api.uptimerobot.com/getMonitors?apiKey=" + UPTIME_ROBOT_KEY + "&format=json&noJsonCallback=1"

# what's our app name?
APP_HOSTNAME = "YOUR_APP_HERE.appspot.com"
if 'APP_HOSTNAME' in os.environ:  # try environment
    APP_HOSTNAME = os.environ['APP_HOSTNAME']
else:  # try getting it from app engine
    try:
        from google.appengine.api.app_identity import get_application_id
        APP_HOSTNAME = get_application_id() + ".appspot.com"
    except ImportError:
        pass


class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Hi, this thing will call you if uptime robot reports down sites.')


def get_uptime_status():
    with contextlib.closing(urllib2.urlopen(UPTIME_ROBOT)) as ustream:
        resp = json.load(ustream)

    downsites = []

    for m in resp['monitors']['monitor']:
        if m['status'] == "9":  # 9 == "Down", 8 == "Seems down"
            downsites.append(m['friendlyname'])
    return {"total": len(resp['monitors']['monitor']), "down": len(downsites), "downsites": downsites}


def trigger_call(recipients):
    client = TwilioRestClient(TWILIO_SID, TWILIO_TOKEN)
    for recp in recipients:
        call = client.calls.create(url=("http://%s/downmessage" % APP_HOSTNAME),
            to=recp, from_=TWILIO_FROM)

def get_phone_numbers_on_shift():
    if not ICAL_PARSE_FROM_URL:
        return []
    phoneNumbers = []
    calendar = Calendar(urllib2.urlopen(ICAL_URL).read().decode('iso-8859-1'))
    for event in calendar.events:
        present = datetime.now(event.begin.tzinfo)
        if event.begin < present and event.end > present:
            phoneNumbers.extend(get_phone_numbers_from_ical_description(event.description))

    return phoneNumbers
def get_phone_numbers_from_ical_description(description):
    lines = description.split("\n");
    buffer = [];
    for line in lines:
        phonePlusSign = line.find('+');
        if phonePlusSign == 0 or (phonePlusSign > 0 and 'phone' in line.lower()):
            if(phonePlusSign > 0):
                line = line[phonePlusSign:]

            phoneNumber = line.replace(' ', '').replace('-', '')

            # Making sure the phone number have minimum length
            if len(phoneNumber) > 7:
                buffer.append(phoneNumber);
    return buffer;

class CheckUptimes(webapp2.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        res = get_uptime_status()
        self.response.write("%d sites being monitored\n" % res['total'])
        if res['down'] != 0:
            self.response.write("Everybody panic!\n")
            for site in res['downsites']:
                self.response.write("%s is down.\n" % site)

            CALLEES.extend(get_people_on_shift())
            trigger_call(CALLEES)
        else:
            self.response.write("Everything seems fine\n")


class DowntimeMessage(webapp2.RequestHandler):
    def post(self):
        self.response.headers['Content-Type'] = "text/xml"
        res = get_uptime_status()
        if res['down'] != 0:
            self.response.write("""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="alice">Everyone panic! %s</Say>
            </Response>""" % " ".join(map(lambda s: ("%s is down." % s.replace("doublemap", "double map")), res['downsites'])))
        else:
            self.response.write("""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="alice">False alarm. %d of %d sites are down.</Say>
            </Response>""" % (res['down'], res['total']))


application = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/checksites', CheckUptimes),
    ('/downmessage', DowntimeMessage),
], debug=True)
