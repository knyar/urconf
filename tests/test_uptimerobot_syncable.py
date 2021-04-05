import pytest

from urconf.uptimerobot_syncable import Contact, Monitor


class TestUptimeRobotSyncable(object):
    def test_required_fields(self):
        with pytest.raises(RuntimeError):
            Contact(friendly_name="name")

    def test_id_does_not_affect_equality(self):
        contact1 = Contact(friendly_name="c1", type=2, value="v1", id="0213")
        contact2 = Contact(friendly_name="c1", type=2, value="v1", id="1444")
        assert contact1 == contact2
        # __repr__ includes `id`, so string representations are not equal.
        assert str(contact1) != str(contact2)

    def test_monitor_contacts_affect_equality(self):
        contact = Contact(friendly_name="c1", type=2, value="v1", id="0213")
        mon1 = Monitor(friendly_name="m1", url="u1", type="1")
        mon1.add_contacts(contact)
        mon2 = Monitor(friendly_name="m1", url="u1", type="1",
                       alert_contacts=[
                           {"id": "0213", "type": 2, "value": "v1",
                           "threshold": 0, "recurrence": 0}])
        mon3 = Monitor(friendly_name="m1", url="u1", type=1)  # no contacts
        assert mon1 != mon3
        assert mon2 != mon3
        assert mon1 == mon2
        assert str(mon1) == str(mon1)
