import json
import logging
import types

import requests
import typedecorator

from urconf.uptimerobot_syncable import Contact, Monitor

logger = logging.getLogger("urconf")
typedecorator.setup_typecheck()

DEFAULT_INTERVAL = 5  # minutes


class UptimeRobotAPIError(Exception):
    """An exception which is raised when Uptime Robot API returns an error."""
    pass


class UptimeRobot(object):
    """UptimeRobot is the main object used to sync configuration.

    It keeps alert contacts and monitors defined by the user in
    `self._contacts` and `self_monitors` lists.
    """
    @typedecorator.params(self=object, api_key=str, url=str, dry_run=bool)
    def __init__(self, api_key, url="https://api.uptimerobot.com/v2/",
                 dry_run=False):
        """Initializes the configuration.

        Args:
            api_key: (string) Uptime Robot API key. This should be the
                "Main API Key", not one of the monitor-specific API keys.
            url: (string) Base URL for Uptime Robot API.
            dry_run: (bool) Flag that can be set to True to prevent urconf
                from changing Uptime Robot configuration.
        """
        self._url = url.rstrip("/") + "/"
        self._dry_run = dry_run
        # These are HTTP query parameters that will be passed to the API with
        # all requests.
        self.params = {
            "api_key": api_key,
            "format": "json",
        }
        self._contacts = {}
        self._monitors = {}
        # `requests` logs at INFO by default, which is annoying.
        logging.getLogger("requests").setLevel(logging.WARNING)

    @typedecorator.params(self=object, method=str,
                          params={str: typedecorator.Union(str, int)})
    def _api_post(self, method, params):
        """Issues a POST request to the API and returns the result.

        Args:
            method: (string) API method to call.
            params: ({string: string}) A dictionary containing key/value
                pairs that will be used in POST data.

        Returns:
            Unmarshalled API response as a Python object.

        Raises:
            UptimeRobotAPIError: when API returns an unexpected error.
        """
        url = self._url + method
        resp = requests.post(url, data=params)
        if resp.status_code != 200:
            raise UptimeRobotAPIError("Got HTTP error {} fetching {}".format(
                resp.status_code, url))
        logger.debug("POST {} {}: {}".format(url, params, resp.text))
        try:
            data = json.loads(resp.text)
        except ValueError as e:
            raise UptimeRobotAPIError(
                "Error decoding JSON of {}: {}. Got: {}".format(
                    method, e, resp.text))
        if data["stat"] != "ok":
            raise UptimeRobotAPIError("{} returned error: {}".format(
                method, data["error"]))
        return data

    @typedecorator.params(
        self=object, method=str, params={str: typedecorator.Union(str, int)},
        element_func=types.FunctionType)
    def _api_post_paginated(self, method, params, element_func):
        """Fetches all elements from a given API method.

        This function gets all elements that a given API method returns,
        issuing multiple POST calls if results do not fit in a single page.

        Args:
            method: (string) API method to call.
            params: ({string: string}) A dictionary containing key/value
                pairs that will be used in the URL query string.
            element_func: function that extracts a list of results from the
                object returned by the API call in question. For example, if
                returned JSON is `{"result": [...]}`, the function can be
                `lambda x: x["result"]`.

        Returns:
            A list of Python objects corresponding to API response.
        """
        params = params.copy()
        result = []
        while True:
            response = self._api_post(method, params)
            result.extend(element_func(response))
            if "pagination" in response:
                response = response["pagination"]
            if response["total"] > response["offset"] + response["limit"]:
                params["offset"] = response["offset"] + response["limit"]
            else:
                break
        return result

    def _sync_monitors(self):
        """Synchronizes locally defined list of monitors with the server.

        This method compares locally defined monitors with the result of the
        `getMonitors` API method and synchronizes them by creating missing
        monitors, deleting obsolete ones, and updating the ones that changed.

        Note: creating and updating monitors requires server-side contact IDs,
        so `_sync_monitors` should only be executed after `_sync_contacts`.
        """
        existing = {}
        params = self.params.copy()
        params.update({"alert_contacts": 1})
        fetched = self._api_post_paginated(
            "getMonitors", params, lambda x: x["monitors"])
        for monitor_dict in fetched:
            m = Monitor(**monitor_dict)
            if m.name in self._monitors:
                existing[m.name] = True
                if not m == self._monitors[m.name]:
                    self._api_update_monitor(m, self._monitors[m.name])
            else:
                self._api_delete_monitor(m)
        for name in self._monitors:
            if name not in existing:
                self._api_create_monitor(self._monitors[name])

    @typedecorator.params(self=object, old="Monitor", new="Monitor")
    def _api_update_monitor(self, old, new):
        logger.info("Updating monitor {}".format(new.name))
        logger.debug("Old: %s", old)
        logger.debug("New: %s", new)
        if old["type"] != new["type"]:
            logger.info("Monitor type updates are not possible, "
                        "will remove and re-add {}".format(new.name))
            self._api_delete_monitor(old)
            self._api_create_monitor(new)
            return
        if self._dry_run:
            return
        params = self.params.copy()
        params.update(new._params_update)
        params["id"] = old["id"]
        self._api_post("editMonitor", params)

    @typedecorator.params(self=object, monitor="Monitor")
    def _api_delete_monitor(self, monitor):
        logger.info("Deleting monitor {}".format(monitor.name))
        if self._dry_run:
            return
        params = self.params.copy()
        params.update(monitor._params_delete)
        self._api_post("deleteMonitor", params)

    @typedecorator.params(self=object, monitor="Monitor")
    def _api_create_monitor(self, monitor):
        logger.info("Creating monitor {}".format(monitor.name))
        if self._dry_run:
            return
        params = self.params.copy()
        params.update(monitor._params_create)
        self._api_post("newMonitor", params)

    def _sync_contacts(self):
        """Synchronizes locally defined list of contacts with the server.

        This method compares locally defined contacts with the result of the
        `getAlertContacts` API method and synchronizes them by creating missing
        contacts and deleting obsolete ones.

        This also populates server-side contact IDs that are required to create
        and update monitors, so `_sync_contacts` should be executed before
        `_sync_monitors`.
        """
        existing = {}
        fetched = self._api_post_paginated(
            "getAlertContacts", self.params,
            lambda x: x["alert_contacts"])
        for contact_dict in fetched:
            c = Contact(**contact_dict)
            if c.name in self._contacts:
                existing[c.name] = True
                # Populate the `id` field based on the contact information
                # we got from the server. This id will be required for the
                # newMonitor / editMonitor calls we make later.
                self._contacts[c.name]["id"] = c["id"]
                if c != self._contacts[c.name]:
                    self._api_update_contact(c, self._contacts[c.name])
            else:
                self._api_delete_contact(c)
        for name in self._contacts:
            if name not in existing:
                contact_id = self._api_create_contact(self._contacts[name])
                self._contacts[name]["id"] = contact_id

    @typedecorator.params(self=object, old="Contact", new="Contact")
    def _api_update_contact(self, old, new):
        logger.info("Updating contact {}".format(new.name))
        logger.debug("Old: %s", old)
        logger.debug("New: %s", new)
        if old["type"] != new["type"]:
            logger.info("Contact type updates are not possible, "
                        "will remove and re-add {}".format(new.name))
            self._api_delete_contact(old)
            self._api_create_contact(new)
            return
        if self._dry_run:
            return
        params = self.params.copy()
        params.update(new._params_update)
        params["id"] = old["id"]
        self._api_post("editAlertContact", params)

    @typedecorator.params(self=object, contact="Contact")
    def _api_delete_contact(self, contact):
        logger.info("Deleting contact {}".format(contact.name))
        if self._dry_run:
            return
        params = self.params.copy()
        params.update(contact._params_delete)
        self._api_post("deleteAlertContact", params)

    @typedecorator.params(self=object, contact="Contact")
    def _api_create_contact(self, contact):
        logger.info("Creating contact {}".format(contact.name))
        if self._dry_run:
            return
        params = self.params.copy()
        params.update(contact._params_create)
        result = self._api_post("newAlertContact", params)
        return result["alertcontact"]["id"]

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, type=int, value=str, friendlyname=str)
    def contact(self, type, value, friendlyname=""):
        """Adds a contact of a given type.

        This is mainly a convenience function for other type-specific methods
        (like email_contact), however it can be used directly to define a
        contact of a type which is not supported by the newAlertContact
        endpoint of Uptime Robot API. The contact will need to be created in
        the Uptime Robot UI manually, but using this function to define it
        as part of configuration will allow usage of such contact for
        monitors.

        Args:
            type: (int) contact type.
            value: (string) contact value.
            friendlyname: (string) name used for this contact in the Uptime
                Robot.

        Returns:
            Contact object which can later be used in add_contacts method
                of a monitor.
        """
        c = Contact(friendly_name=friendlyname, type=type, value=value)
        assert c.name not in self._contacts, \
            "Duplicate contact: {}".format(c.name)
        self._contacts[c.name] = c
        logging.debug("Created contact: %s", c)
        return c

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, email=str, name=str)
    def email_contact(self, email, name=None):
        """Defines an email contact.

        Args:
            email: (string) e-mail address.
            name: (string) name used for this contact in the Uptime Robot web
                interface.

        Returns:
            Contact object which can later be used in add_contacts method
                of a monitor.
        """
        if not name:
            name = email
        return self.contact(Contact.TYPE_EMAIL, email, name)

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, key=str, name=str)
    def boxcar_contact(self, key, name=""):
        return self.contact(Contact.TYPE_BOXCAR, key, name)

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, number=str, name=str)
    def sms_contact(self, number, name=""):
        return self.contact(Contact.TYPE_SMS, number, name)

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, value=str, name=str)
    def twitter_dm_contact(self, value, name=""):
        return self.contact(Contact.TYPE_TWITTER_DM, value, name)

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, value=str, name=str)
    def webhook_contact(self, value, name=""):
        return self.contact(Contact.TYPE_WEBHOOK, value, name)

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, value=str, name=str)
    def pushbullet_contact(self, value, name=""):
        return self.contact(Contact.TYPE_PUSHBULLET, value, name)

    @typedecorator.returns("Contact")
    @typedecorator.params(self=object, value=str, name=str)
    def pushover_contact(self, value, name=""):
        return self.contact(Contact.TYPE_PUSHOVER, value, name)

    @typedecorator.returns("Monitor")
    @typedecorator.params(
        self=object, name=str, url=str, keyword=str, should_exist=bool,
        http_username=str, http_password=str, interval=int)
    def keyword_monitor(self, name, url, keyword, should_exist=True,
                        http_username="", http_password="",
                        interval=DEFAULT_INTERVAL):
        """Defines a keyword monitor.

        Args:
            name: (string) name used for this monitor in the Uptime Robot web
                interface.
            url: (string) URL to check.
            keyword: (string) Keyword to check.
            should_exist: (string) Whether the keyword should exist or not
                (defaults to True).
            http_username: (string) Username to use for HTTP authentification.
            http_password: (string) Password to use for HTTP authentification.
            interval: (int) Monitoring interval in minutes.

        Returns:
            Monitor object.
        """
        keywordtype = 2 if should_exist else 1
        m = Monitor(friendly_name=name, type=Monitor.TYPE_KEYWORD, url=url,
                    keyword_value=keyword, keyword_type=keywordtype,
                    http_username=http_username, http_password=http_password,
                    interval=interval*60)
        assert m.name not in self._monitors, \
            "Duplicate monitor: {}".format(m.name)
        self._monitors[m.name] = m
        return m

    @typedecorator.returns("Monitor")
    @typedecorator.params(self=object, name=str, hostname=str, port=int,
                          interval=int)
    def port_monitor(self, name, hostname, port, interval=DEFAULT_INTERVAL):
        """Defines a port monitor.

        Args:
            name: (string) name used for this monitor in the Uptime Robot web
                interface.
            hostname: (string) Host name to check.
            port: (int) TCP port.
            interval: (int) Monitoring interval in minutes.

        Returns:
            Monitor object.
        """
        # Port to subtype map from https://uptimerobot.com/api
        port_to_subtype = {80: 1, 443: 2, 21: 3, 25: 4, 110: 5, 143: 6}
        subtype = port_to_subtype.setdefault(port, 99)
        m = Monitor(friendly_name=name, type=Monitor.TYPE_PORT, url=hostname,
                    sub_type=subtype, port=port, interval=interval*60)
        assert m.name not in self._monitors, \
            "Duplicate monitor: {}".format(m.name)
        self._monitors[m.name] = m
        return m

    def sync(self):
        """Synchronizes configuration with the Uptime Robot API.

        This method should be called after all contacts and monitors have been
        defined and will sync defined configuration to the Uptime Robot."""
        self._sync_contacts()
        self._sync_monitors()
