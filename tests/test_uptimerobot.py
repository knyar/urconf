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
    params = parse_qs(request.body, keep_blank_values=True)
    for key in kwargs:
        assert params[key][0] == str(kwargs[key]), "Invalid {}".format(key)


class TestUptimeRobot(object):
    @responses.activate
    def test_get_raises_on_invalid_json(self):
        responses.add(
            responses.POST, "https://fake/none", body="omg this is not json")

        config = urconf.UptimeRobot("", url="https://fake")
        with pytest.raises(urconf.uptimerobot.UptimeRobotAPIError):
            config._api_post("none", {})

    @responses.activate
    def test_get_raises_on_404(self):
        responses.add(
            responses.POST, "https://fake/none", body="404", status=404)

        config = urconf.UptimeRobot("", url="https://fake")
        with pytest.raises(urconf.uptimerobot.UptimeRobotAPIError):
            config._api_post("none", {})

    @responses.activate
    def test_get_raises_on_api_errors(self):
        responses.add(responses.POST, "https://fake/none",
                      body='{"stat":"fail","error":{"type":"invalid_parameter"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        with pytest.raises(urconf.uptimerobot.UptimeRobotAPIError):
            config._api_post("none", {})

    @responses.activate
    def test_api_post_paginated(self):
        def callback(request):
            params = parse_qs(request.body) if request.body else {}
            limit = params["limit"][0] if "limit" in params else 1
            offset = params["offset"][0] if "offset" in params else 0
            resp = """{{"stat": "ok", "offset": {offset}, "limit": {limit},
                        "total": 10,"fake":["fakedata{offset}"]}}""".format(
                offset=offset, limit=limit)
            return (200, {}, resp)
        responses.add_callback(responses.POST, "https://fake/getFake",
                               callback=callback)

        config = urconf.UptimeRobot("", url="https://fake/")
        result = config._api_post_paginated("getFake", {}, lambda x: x["fake"])

        assert len(responses.calls) == 10
        for i in (range(10)):
            assert "fakedata{}".format(i) in result

    @responses.activate
    def test_add_email_contact(self):
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(
            responses.POST, "https://fake/newAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"0725","status":0}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.email_contact("e@mail", name="email1")
        config.email_contact("XYZ")
        config._sync_contacts()

        assert config._contacts["XYZ"]["id"] == "0725"
        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, type=2,
            friendly_name="XYZ", value="XYZ")

    @responses.activate
    def test_add_boxcar_contact(self):
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(
            responses.POST, "https://fake/newAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"12344","status":"0"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.email_contact("e@mail", name="email1")
        config.boxcar_contact("XYZ", name="boxcar1")
        config._sync_contacts()

        assert config._contacts["XYZ"]["id"] == "12344"
        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, type=4,
            friendly_name="boxcar1", value="XYZ")

    @responses.activate
    def test_delete_email_contact(self):
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_two"))
        responses.add(
            responses.POST, "https://fake/deleteAlertContact",
            body='{"stat": "ok","alert_contact":{"id":"9876352"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.email_contact("e@mail", name="email1")
        config._sync_contacts()

        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, id="9876352")

    @responses.activate
    def test_add_port_monitor(self):
        responses.add(responses.POST, "https://fake/getMonitors",
                      body=read_data("monitors_none"))
        responses.add(
            responses.POST, "https://fake/newMonitor",
            body='{"stat": "ok","monitor":{"id":"515","status":1}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        config.port_monitor("my mail", "servername", 25),
        config._sync_monitors()

        assert len(responses.calls) == 2
        assert_query_params(
            responses.calls[1].request, friendly_name="my mail",
            url="servername", type=4, sub_type=4,
            port=25, alert_contacts="",
            interval=urconf.uptimerobot.DEFAULT_INTERVAL*60)

    @responses.activate
    def test_add_keyword_monitor_and_change_contact_threshold(self):
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.POST, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.POST, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')
        responses.add(
            responses.POST, "https://fake/newMonitor",
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
            responses.calls[2].request, friendly_name="smtp2",
            url="host2", sub_type=4,
            alert_contacts="012345_5_0",
            interval=urconf.uptimerobot.DEFAULT_INTERVAL*60)
        assert_query_params(
            responses.calls[3].request, friendly_name="kw2",
            url="http://fake2",
            keyword_type=2, keyword_value="test2",
            alert_contacts="012345_0_0",
            interval=urconf.uptimerobot.DEFAULT_INTERVAL*60)

    @responses.activate
    def test_remove_monitor(self):
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.POST, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.POST, "https://fake/deleteMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1")
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 3
        assert_query_params(responses.calls[2].request, id=123401)

    @responses.activate
    def test_edit_monitor_type(self):
        """API does not allow editing monitor type, so urconf should
           remove the old monitor and create the new one.
        """
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.POST, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.POST, "https://fake/deleteMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')
        responses.add(
            responses.POST, "https://fake/newMonitor",
            body='{"stat": "ok","monitor":{"id":"120011","status":"1"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.email_contact("e@mail", name="email1")
        # change keyword monitor to a port monitor
        config.port_monitor("kw1", "fake", 80).add_contacts(email)
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 4
        assert_query_params(responses.calls[2].request, id=123401)
        assert_query_params(
            responses.calls[3].request, friendly_name="kw1",
            url="fake", type=4, sub_type=1,
            alert_contacts="012345_0_0",
            interval=urconf.uptimerobot.DEFAULT_INTERVAL*60)

    @responses.activate
    def test_remove_http_auth(self):
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(responses.POST, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.POST, "https://fake/editMonitor",
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
            responses.calls[2].request, friendly_name="kw1",
            url="http://fake",
            keyword_type=2, keyword_value="test1",
            alert_contacts="012345_0_0",
            interval=urconf.uptimerobot.DEFAULT_INTERVAL*60)

    @responses.activate
    def test_change_email_address(self):
        """Tests contact updates.

        Since API does not allow editing contact type, this verifies that the
        contact gets removed and then re-added. New contact ID will be
        allocated, so all monitors using the old contact will need to be
        updated as well.
        """
        responses.add(responses.POST, "https://fake/getAlertContacts",
                      body=read_data("contacts_one"))
        responses.add(
            responses.POST, "https://fake/deleteAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"012345"}}')
        responses.add(
            responses.POST, "https://fake/newAlertContact",
            body='{"stat": "ok","alertcontact":{"id":"144444","status":"0"}}')
        responses.add(responses.POST, "https://fake/getMonitors",
                      body=read_data("monitors_three"))
        responses.add(
            responses.POST, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123401"}}')
        responses.add(
            responses.POST, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123402"}}')
        responses.add(
            responses.POST, "https://fake/editMonitor",
            body='{"stat": "ok","monitor":{"id":"123403"}}')

        config = urconf.UptimeRobot("", url="https://fake/")
        email = config.boxcar_contact("boxcar1", name="email1")
        config.keyword_monitor(
            "kw1", "http://fake", "test1", http_username="user1",
            http_password="pass1").add_contacts(email)
        config.port_monitor("ssh1", "host1", 22).add_contacts(email)
        config.port_monitor("smtp2", "host2", 25).add_contacts(email)
        config.sync()

        assert len(responses.calls) == 7
        assert_query_params(
            responses.calls[1].request, id="012345")
        assert_query_params(
            responses.calls[2].request,
            friendly_name="email1", type=4, value="boxcar1")
        assert_query_params(
            responses.calls[4].request, friendly_name="kw1",
            url="http://fake",
            keyword_type=2, keyword_value="test1",
            http_username="user1", http_password="pass1",
            alert_contacts="144444_0_0",
            interval=urconf.uptimerobot.DEFAULT_INTERVAL*60)

    @responses.activate
    def test_change_email_address_dry_run(self):
        """Tests dry run mode, confirming that no objects get changed."""
        with responses.RequestsMock(assert_all_requests_are_fired=False) \
                as resp:
            resp.add(responses.POST, "https://fake/getAlertContacts",
                     body=read_data("contacts_two"))
            resp.add(responses.POST, "https://fake/getMonitors",
                     body=read_data("monitors_three"))
            exception = requests.exceptions.HTTPError(
                "dry_run should not mutate state")
            for method in ("deleteAlertContact", "newAlertContact",
                           "editMonitor", "deleteMonitor", "newMonitor"):
                resp.add(responses.POST, "https://fake/{}".format(method),
                         body=exception)

            config = urconf.UptimeRobot("", url="https://fake/", dry_run=True)
            email = config.email_contact("new@mail", name="email2")
            config.keyword_monitor(
                "kw1", "http://fake", "test1").add_contacts(email)
            config.port_monitor("ssh1", "host1", 22).add_contacts(email)
            config.port_monitor("smtp3", "host3", 25).add_contacts(email)
            config.sync()

            assert len(resp.calls) == 2
