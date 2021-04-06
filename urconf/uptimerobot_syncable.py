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

    @property
    def _params_delete(self):
        """Generates URL parameters for the delete* API call."""
        return {"id": self["id"]}

class Monitor(Syncable):
    _FIELDS = [
        "friendly_name", "url", "type", "sub_type", "keyword_type",
        "keyword_value", "http_username", "http_password", "port", "interval",
        "http_auth_type", "http_method", "post_type", "post_value",
        "post_content_type",
    ]
    _TYPES = {
        # leading zeroes matter, so `id` should be treated is a string.
        "id": str,
        "friendly_name": str,
        "url": str,
        "type": int,
        "sub_type": int,
        "keyword_type": int,
        "keyword_value": str,
        "http_username": str,
        "http_password": str,
        "port": int,
        "interval": int,
        "http_auth_type": int,
        "http_method": int,
        "post_type": int,
        "post_value": str,
        "post_content_type": int,
    }
    _REQUIRED_FIELDS = ["friendly_name", "url", "type"]

    # Possible monitor types, copied from https://uptimerobot.com/api
    TYPE_KEYWORD = 2
    TYPE_PORT = 4

    def __init__(self, **kwargs):
        super(Monitor, self).__init__(**kwargs)
        self._added_contacts = []
        self._contacts_str = None
        if "alert_contacts" in kwargs:
            # This means that this Monitor object has been created based on
            # the data returned by getMonitors API call, which includes contact
            # IDs and options, which can be placed in the right format into
            # self._contacts_str.
            contacts = [
                self._contact_str(c["id"], c["threshold"], c["recurrence"])
                for c in kwargs["alert_contacts"]]
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
    def _params_create(self):
        """Generates URL parameters for the newMonitor API call."""
        params = self._values.copy()
        params["alert_contacts"] = self._contacts
        return params

    @property
    def _params_update(self):
        """Generates URL parameters for the editMonitor API call."""
        params = self._params_create
        del params["type"]
        return params

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
    _FIELDS = ["value", "type", "friendly_name"]
    _TYPES = {
        # leading zeroes matter, so `id` should be treated is a string.
        "id": str,
        "friendly_name": str,
        "type": int,
        "value": str,
    }
    _REQUIRED_FIELDS = ["value", "type"]

    # Possible contact types, copied from https://uptimerobot.com/api
    TYPE_SMS = 1
    TYPE_EMAIL = 2
    TYPE_TWITTER_DM = 3
    TYPE_BOXCAR = 4
    TYPE_WEBHOOK = 5
    TYPE_PUSHBULLET = 6
    TYPE_PUSHOVER = 9

    @property
    def _params_create(self):
        """Generates URL parameters for the newAlertContact API call."""
        return {f: self[f] for f in self._FIELDS}

    @property
    def _params_update(self):
        """Generates URL parameters for the editAlertContact API call."""
        params = self._params_create
        del params["type"]
        return params
