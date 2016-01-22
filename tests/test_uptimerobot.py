import os
try:
    from urllib.parse import urlparse, parse_qs
except ImportError:
    from urlparse import urlparse, parse_qs

import pytest
import requests
import responses
import urconf


def read_data(filename):
    """Reads data from file and returns it as a string.

    File will be read from the directory named after this file (test_foo/ if
    the file is test_foo.py).
    """
    basename, _ = os.path.splitext(__file__)
    with open(os.path.join(basename, filename)) as f:
        return f.read()


def assert_query_params(request, **kwargs):
    """Asserts that given query parameters have expected values.

    Args:
        request: a PreparedRequest object.
        kwargs: key/value pairs that should be present in the query of
            request URL.

    Raises:
        AssertionError if a parameter has unexpected value.
        KeyError if a parameter does not exist.
    """
    params = parse_qs(urlparse(request.url).query, keep_blank_values=True)
    for key in kwargs:
        assert params[key][0] == str(kwargs[key]), "Invalid {}".format(key)


class TestUptimeRobot(object):
    @responses.activate
    def test_get_raises_on_invalid_json(self):
        responses.add(
            responses.GET, "https://fake/none", body="omg this is not json")

        config = urconf.UptimeRobot("", url="https://fake")
        with pytest.raises(urconf.uptimerobot.UptimeRobotAPIError):
            config._api_get("none", {})

    @responses.activate
    def test_get_raises_on_404(self):
        responses.add(
            responses.GET, "https://fake/none", body="404", status=404)

        config = urconf.UptimeRobot("", url="https://fake")
        with pytest.raises(urconf.uptimerobot.UptimeRobotAPIError):
            config._api_get("none", {})

    @responses.activate
    def test_get_raises_on_api_errors(self):
        responses.add(responses.GET, "https://fake/none",
                      body='{"stat": "error", "message": "error", "id": 99}')

        config = urconf.UptimeRobot("", url="https://fake/")
        with pytest.raises(urconf.uptimerobot.UptimeRobotAPIError):
            config._api_get("none", {})

    @responses.activate
    def test_api_get_paginated(self):
        def callback(request):
            params = parse_qs(urlparse(request.url).query)
            limit = params["limit"][0] if "limit" in params else 1
            offset = params["offset"][0] if "offset" in params else 0
            resp = """{{"stat": "ok", "offset": "{offset}", "limit": "{limit}",
                        "total": "10","fake":["fakedata{offset}"]}}""".format(
                offset=offset, limit=limit)
            return (200, {}, resp)
        responses.add_callback(responses.GET, "https://fake/getFake",
                               callback=callback)

        config = urconf.UptimeRobot("", url="https://fake/")
        result = config._api_get_paginated("getFake", {}, lambda x: x["fake"])

        assert len(responses.calls) == 10
        for i in (range(10)):
            assert "fakedata{}".format(i) in result

    @responses.activate
    def test_add_email_contact(self):
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(
            responses.GET, "https://fake/newAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"0725","status":"0"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.email_contact("e@mail", name="email1")
        config.email_contact("XYZ")
        config._sync_contacts()

        assert config._contacts["XYZ"]["id"] == "0725"
        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, alertContactType=2,
            alertContactFriendlyName="", alertContactValue="XYZ")

    @responses.activate
    def test_add_boxcar_contact(self):
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(
            responses.GET, "https://fake/newAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"12344","status":"0"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.email_contact("e@mail", name="email1")
        config.boxcar_contact("XYZ", name="boxcar1")
        config._sync_contacts()

        assert config._contacts["XYZ"]["id"] == "12344"
        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, alertContactType=4,
            alertContactFriendlyName="boxcar1", alertContactValue="XYZ")

    @responses.activate
    def test_delete_email_contact(self):
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_two"))
        responses.add(
            responses.GET, "https://fake/deleteAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"9876352"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.email_contact("e@mail", name="email1")
        config._sync_contacts()

        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, alertContactID="9876352")

    @responses.activate
    def test_add_port_monitor(self):
        responses.add(responses.GET, "https://fake/getMonitors",
                      body=read_data("monitors_none"))
        responses.add(
            responses.GET, "https://fake/newMonitor",
            body='{"stat": "ok","monitor":{"id":"515","status":"1"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.port_monitor("my mail", "servername", 25),
        config._sync_monitors()

        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, monitorFriendlyName="my mail",
            monitorURL="servername", monitorType=4, monitorSubType=4,
            monitorPort=25, monitorAlertContacts="",
            monitorInterval=urconf.uptimerobot.DEFAULT_INTERVAL)

    @responses.activate
    def test_add_keyword_monitor_and_change_contact_threshold(self):
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.GET, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.GET, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')
        responses.add(
            responses.GET, "https://fake/newMonitor",
            body='{"stat": "ok","monitor":{"id":"6969","status":"1"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1")
        config.keyword_monitor(
            "kw1", "http://fake", "test1", http_username="user1",
            http_password="pass1").add_contacts(email)
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor(
            "smtp2", "host2", 25).add_contacts(email, threshold=5)
        config.keyword_monitor(
            "kw2", "http://fake2", "test2").add_contacts(email)
        config.sync()

        assert len(responses.calls) == 4
        assert_query_params(
            responses.calls[2].request, monitorFriendlyName="smtp2",
            monitorURL="host2", monitorType=4, monitorSubType=4,
            monitorKeywordType=0, monitorKeywordValue="",
            monitorAlertContacts="012345_5_0",
            monitorInterval=urconf.uptimerobot.DEFAULT_INTERVAL)
        assert_query_params(
            responses.calls[3].request, monitorFriendlyName="kw2",
            monitorURL="http://fake2", monitorType=2, monitorSubType=0,
            monitorKeywordType=2, monitorKeywordValue="test2",
            monitorHTTPUsername="", monitorHTTPPassword="",
            monitorAlertContacts="012345_0_0",
            monitorInterval=urconf.uptimerobot.DEFAULT_INTERVAL)

    @responses.activate
    def test_remove_monitor(self):
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.GET, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.GET, "https://fake/deleteMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1")
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 3
        assert_query_params(responses.calls[2].request, monitorID=123401)

    @responses.activate
    def test_edit_monitor_type(self):
        """API does not allow editing monitor type, so urconf should
           remove the old monitor and create the new one.
        """
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.GET, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.GET, "https://fake/deleteMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')
        responses.add(
            responses.GET, "https://fake/newMonitor",
            body='{"stat": "ok","monitor":{"id":"120011","status":"1"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1")
        # change keyword monitor to a port monitor
        config.port_monitor("kw1", "fake", 80).add_contacts(email)
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 4
        assert_query_params(responses.calls[2].request, monitorID=123401)
        assert_query_params(
            responses.calls[3].request, monitorFriendlyName="kw1",
            monitorURL="fake", monitorType=4, monitorSubType=1,
            monitorAlertContacts="012345_0_0",
            monitorInterval=urconf.uptimerobot.DEFAULT_INTERVAL)

    @responses.activate
    def test_remove_http_auth(self):
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.GET, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.GET, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123401"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1")
        config.keyword_monitor(
            "kw1", "http://fake", "test1").add_contacts(email)
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 3
        assert_query_params(
            responses.calls[2].request, monitorFriendlyName="kw1",
            monitorURL="http://fake", monitorType=2, monitorSubType=0,
            monitorKeywordType=2, monitorKeywordValue="test1",
            monitorHTTPUsername="", monitorHTTPPassword="",
            monitorAlertContacts="012345_0_0",
            monitorInterval=urconf.uptimerobot.DEFAULT_INTERVAL)

    @responses.activate
    def test_change_email_address(self):
        """Tests contact updates.

        Since API does not allow editing a contact, this verifies that the
        contact gets removed and then re-added. New contact ID will be
        allocated, so all monitors using the old contact will need to be
        updated as well.
        """
        responses.add(responses.GET, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(
            responses.GET, "https://fake/deleteAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"012345"}}')
        responses.add(
            responses.GET, "https://fake/newAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"144444","status":"0"}}')
        responses.add(responses.GET, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.GET, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123401"}}')
        responses.add(
            responses.GET, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123402"}}')
        responses.add(
            responses.GET, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1-renamed")
        config.keyword_monitor(
            "kw1", "http://fake", "test1", http_username="user1",
            http_password="pass1").add_contacts(email)
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 7
        assert_query_params(
            responses.calls[1].request, alertContactID="012345")
        assert_query_params(
            responses.calls[2].request,
            alertContactFriendlyName="email1-renamed",
            alertContactType=2, alertContactValue="e@mail")
        assert_query_params(
            responses.calls[4].request, monitorFriendlyName="kw1",
            monitorURL="http://fake", monitorType=2, monitorSubType=0,
            monitorKeywordType=2, monitorKeywordValue="test1",
            monitorHTTPUsername="user1", monitorHTTPPassword="pass1",
            monitorAlertContacts="144444_0_0",
            monitorInterval=urconf.uptimerobot.DEFAULT_INTERVAL)

    @responses.activate
    def test_change_email_address_dry_run(self):
        """Tests dry run mode, confirming that no objects get changed."""
        with responses.RequestsMock(assert_all_requests_are_fired=False) \
                as resp:
            resp.add(responses.GET, "https://fake/getAlertContacts",
                     body=read_data("contacts_two"))
            resp.add(responses.GET, "https://fake/getMonitors",
                     body=read_data("monitors_three"))
            exception = requests.exceptions.HTTPError(
                "dry_run should not mutate state")
            for method in ("deleteAlertContact", "newAlertContact",
                           "editMonitor", "deleteMonitor", "newMonitor"):
                resp.add(responses.GET, "https://fake/{}".format(method),
                         body=exception)

            config = urconf.UptimeRobot("", url="https://fake/", dry_run=True)
            email = config.email_contact("new@mail", name="email2")
            config.keyword_monitor(
                "kw1", "http://fake", "test1").add_contacts(email)
            config.port_monitor("ssh1", "host1", 22).add_contacts(email)
            config.port_monitor("smtp3", "host3", 25).add_contacts(email)
            config.sync()

            assert len(resp.calls) == 2
