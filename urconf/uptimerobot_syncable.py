class Syncable(object):
    """Syncable is the parent class for objects that urconf keeps in sync.

       All values are stored in the `self._values` dictionary.
    """
    def __init__(self, **kwargs):
        """Construct the object.

        This is designed to be called either with kwargs specified manually or
        with a dict of parameters as returned by getAlertContacts or
        getMonitors.

        Parameter names (self._values keys) correspond to the "Parameters"
        list at https://uptimerobot.com/api
        """
        self._values = {}
        for f in self._REQUIRED_FIELDS:
            if f not in kwargs:
                raise RuntimeError("Contact requires {}; got {}".format(
                    f, kwargs))

        # `id` is not part of FIELDS, because it"s auto-generated on the server
        # rather than passed by the user. However, it's useful to have it,
        # so it's added into the self._values if it exists in kwargs.
        for f in self._FIELDS + ["id"]:
            if f in kwargs and kwargs[f]:
                self[f] = kwargs[f]

    def __eq__(self, other):
        for f in self._FIELDS:
            if self[f] != other[f]:
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __setitem__(self, key, value):
        self._values[key] = self._TYPES[key](value)

    def __getitem__(self, key):
        if key in self._values:
            return self._values[key]
        if self._TYPES[key] == str:
            return ""
        if self._TYPES[key] == int:
            return 0

    def __repr__(self):
        return self._values.__repr__()

    @property
    def name(self):
        """Defines primary identificator for this object used by urconf."""
        return self[self._FIELDS[0]]


class Monitor(Syncable):
    _FIELDS = [
        "friendlyname", "url", "type", "subtype", "keywordtype",
        "keywordvalue", "httpusername", "httppassword", "port", "interval",
    ]
    _TYPES = {
        # leading zeroes matter, so `id` should be treated is a string.
        "id": str,
        "friendlyname": str,
        "url": str,
        "type": int,
        "subtype": int,
        "keywordtype": int,
        "keywordvalue": str,
        "httpusername": str,
        "httppassword": str,
        "port": int,
        "interval": int,
    }
    _REQUIRED_FIELDS = ["friendlyname", "url", "type"]

    # Possible monitor types, copied from https://uptimerobot.com/api
    TYPE_KEYWORD = 2
    TYPE_PORT = 4

    def __init__(self, **kwargs):
        super(Monitor, self).__init__(**kwargs)
        self._added_contacts = []
        self._contacts_str = None
        if "alertcontact" in kwargs:
            # This means that this Monitor object has been created based on
            # the data returned by getMonitors API call, which includes contact
            # IDs and options, which can be placed in the right format into
            # self._contacts_str.
            contacts = [
                self._contact_str(c["id"], c["threshold"], c["recurrence"])
                for c in kwargs["alertcontact"]]
            self._contacts_str = "-".join(sorted(contacts))

    def _contact_str(self, *args):
        return "_".join([str(a) for a in args])

    @property
    def _contacts(self):
        """Returns contact information for this monitor.

        Information is returned in the format expected by editMonitor or
        newMonitor API calls. For monitors that come from the server (i.e.
        initialized based on getMonitors data) we can read the
        self._contacts_str directly. Otherwise we look at all contacts
        added using self.add_contacts.
        """
        if self._contacts_str:
            return self._contacts_str
        contacts = [self._contact_str(c[0]["id"], c[1], c[2])
                    for c in self._added_contacts]
        return "-".join(sorted(contacts))

    def __repr__(self):
        return "<{} {}>".format(self._values, self._contacts)

    def __eq__(self, other):
        if not super(Monitor, self).__eq__(other):
            return False
        return self._contacts == other._contacts

    @property
    def _params_delete(self):
        """Generates URL parameters for the deleteMonitor API call."""
        return {"monitorID": self["id"]}

    @property
    def _params_create(self):
        """Generates URL parameters for the newMonitor API call."""
        create_params = {
            "friendlyname": "monitorFriendlyName",
            "url": "monitorURL",
            "type": "monitorType",
            "subtype": "monitorSubType",
            "port": "monitorPort",
            "keywordtype": "monitorKeywordType",
            "keywordvalue": "monitorKeywordValue",
            "httpusername": "monitorHTTPUsername",
            "httppassword": "monitorHTTPPassword",
            "interval": "monitorInterval",
        }
        params = {create_params[f]: self[f] for f in self._FIELDS}
        params["monitorAlertContacts"] = self._contacts
        return params

    @property
    def _params_update(self):
        """Generates URL parameters for the editMonitor API call."""
        return self._params_create

    def add_contacts(self, *args, **kwargs):
        """Defines contacts for a monitor.

        Args:
            args: one or more Contact objects (returned by functions like
                `email_contact` or `boxcar_contact`).
            threshold: alert threshold (the x value that is set to define "if
                down for x minutes, alert every y minutes).
            recurrence: alert recurrence (the y value that is set to define "if
                down for x minutes, alert every y minutes).
        """
        for key in kwargs:
            assert key in ("threshold", "recurrence"), \
                "invalid keyword argument to add_contacts: {}".format(key)
        threshold = kwargs.get("threshold", 0)
        recurrence = kwargs.get("recurrence", 0)
        for c in args:
            assert type(c) == Contact, "{} is not a Contact".format(c)
            self._added_contacts.append((c, threshold, recurrence))


class Contact(Syncable):
    _FIELDS = ["value", "type", "friendlyname"]
    _TYPES = {
        # leading zeroes matter, so `id` should be treated is a string.
        "id": str,
        "friendlyname": str,
        "type": int,
        "value": str,
    }
    _REQUIRED_FIELDS = ["value", "type"]

    # Possible contact types, copied from https://uptimerobot.com/api
    TYPE_EMAIL = 2
    TYPE_BOXCAR = 4

    @property
    def _params_delete(self):
        """Generates URL parameters for the deleteAlertContact API call."""
        return {"alertContactID": self["id"]}

    @property
    def _params_create(self):
        """Generates URL parameters for the newAlertContact API call."""
        return {
            "alertContactType": self["type"],
            "alertContactValue": self["value"],
            "alertContactFriendlyName": self["friendlyname"],
        }
