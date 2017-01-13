# OFENSIVARIA BOT VERSION PYTHON 3 #

To run the poller (doesn't use the http server, so it's easier to test locally):

* `fab poll`

To run the web app:

* `fab web`

We don't have tests yet :(

To deploy:

* `fab deploy` (but you need access to the server itself)

Deploying is really hacky and not pretty at all. But works.

## TODO ##

* Tests
* Improve deploy with fabric-docker -- https://docker-fabric.readthedocs.io/en/stable/index.html
* Easier infrastructure to write commands
