# OFENSIVARIA BOT VERSION PYTHON 3 #

To run the poller (doesn't use the http server, so it's easier to test locally):

* `fab poll`

To run the web app:

* `fab web`

We don't have tests yet :(

To deploy:

* `fab -H <yourserver> --set telegram_token='<your_telegram_token>',docker_username=<your_docker_username>,host_string=<your_server> deploy`

Deploying is really hacky and not pretty at all. But works.

## TODO ##

* Tests
* Easier infrastructure to write commands
