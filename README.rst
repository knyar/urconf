.. image:: https://readthedocs.org/projects/urconf/badge/?version=latest
  :target: http://urconf.readthedocs.org/en/latest/?badge=latest

.. image:: https://travis-ci.org/knyar/urconf.svg?branch=master
  :target: https://travis-ci.org/knyar/urconf

.. image:: https://coveralls.io/repos/knyar/urconf/badge.svg?branch=master&service=github
  :target: https://coveralls.io/github/knyar/urconf?branch=master

Declarative configuration library for Uptime Robot
--------------------------------------------------

``urconf`` is a Python library for Uptime Robot <https://uptimerobot.com/>
API. It expects definition of all your contacts and monitors, and then issues
API calls required to configure your Uptime Robot accordingly.

Usage
-----

Install urconf using pip: ``pip install urconf``

Write your monitoring configuration as a Python script:

.. code:: python

  import logging
  import urconf

  # urconf logs all operations that change configuration at the INFO level.
  # Use DEBUG to see API call contents.
  logging.basicConfig(level=logging.INFO)

  config = urconf.UptimeRobot("api-key")  # dry_run=True enables dry mode

  # Define contacts
  email = config.email_contact("me@example.com")
  boxcar = config.boxcar_contact("boxcar-api-key", "my boxcar")

  # Define monitors
  ssh = config.port_monitor("ssh on server1", "server1.example.com", 22)
  web = config.keyword_monitor(
      "my site", "https://example.com/", "welcome to example.com!")
  # More complex example with HTTP auth and non-standard monitoring interval
  backend = config.keyword_monitor(
      "my backend", "https://admin.example.com", "Cannot connect to database",
      should_exist=False, http_username="admin", http_password="password",
      interval=20)

  # Associate contacts with monitors
  for monitor in (ssh, web, backend):
      monitor.add_contacts(email, boxcar)

  # Sync configuration to Uptime Robot
  config.sync()

Run the script to sync configuration.

Functionality
-------------

Currently implemented:

- email and boxcar contacts;
- keyword and port monitors.

Pull requests extending supported types of contacts or monitors are very
welcome.

Caveats
-------

Since uptimerobot API does not support modifying contacts, when contact
modification is detected, ``urconf`` has to remove the old contact and re-add
it. This means that e-mail contacts have to be re-verified manually again.

Development notes
-----------------

- refer to API documentation <https://uptimerobot.com/api> while implementing
  additional functionality;
- run ``tox`` to run the tests in Python 2.7 and 3.4 environments;
- run ``make html`` in ``docs/`` to build documentation in HTML. It can be
  viewed in ``docs/_build/html/`` afterwards.

License
-------

``urconf`` is licensed under the MIT license.
