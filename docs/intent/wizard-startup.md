# Reliable local wizard startup

An older wizard may remain alive after the user opens a new launcher.
Windows allows two HTTPServer sockets with SO_REUSEADDR to bind the same
address and port; the second prints a successful startup banner, but HTTP
requests can continue reaching the first process. An isolated reproduction
returned the old version on all ten requests after both servers started.

Bind the loopback listener exclusively, and probe for an existing loopback
listener first: Windows can still allow a specific-address exclusive bind
beside an older reusable wildcard listener. If the requested port is occupied
or unavailable, bind an OS-selected free port, log the reason, and display
and open that actual URL. Never kill the owner of an occupied port or attach
the new screen to an older process. Restart guidance must tell the user to
use the URL opened by the new launcher. Preserve uploaded data and running
conversion processes in existing instances.

Verify real HTTP responses with an older reusable listener on both loopback
and wildcard addresses, a current exclusive listener, and repeated startup.
Check that the browser receives the actual bound URL and unrelated startup
errors are not swallowed. Use isolated temporary workspaces and ports.
