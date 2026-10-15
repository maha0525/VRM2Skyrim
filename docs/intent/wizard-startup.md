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

The served page's version must come from the same `settings.VERSION` as the
API and startup banner, injected into an HTML placeholder by the server.
A release must not require a second manual version bump in static HTML:
0.11.2 initially retained 0.11.1 there and falsely blocked a current server.
Test real HTTP page/API responses at both `/` and `/index.html`, including
a simulated future version. Preserve the source-fingerprint restart guard
for a process left running while files change.


## 2026-10-16 native dependency ABI agreement

The active wizard used Python 3.13 while bsa.py unconditionally prepended an
old developer-only dependencies/python tree containing CPython 3.11 lz4 native
extensions. find_spec('lz4') returned true even though import lz4.frame failed.
Headgear extraction reached the failure only when reading a compressed BSA.

Use installed dependencies belonging to the active project environment; do not
prepend a stale vendor tree globally. Launch.cmd must require the configured
.venv, rather than silently choosing an arbitrary system Python. Retain the
supported 3.11/3.12 contract. Setup verifies imports and LZ4 decompression after
installing requirements, and doctor tests imports/decompression instead of
package-name discovery. Log the interpreter and diagnostic failure details.
Verify compressed BSA v105 extraction, the failed headgear input and rendered
preview, and rejection of a present-but-unloadable native dependency.


The same-input end-to-end check also found two subsequent preview failures:
partitioned skin components legitimately omit source `shapes` metadata, while
the renderer unconditionally indexed that field; cached run.json was read
using the Windows locale despite being written as UTF-8. Use the imported NIF
materials for partial-source components, retain required metadata for other
components, and read JSON explicitly as UTF-8 in preview and result paths.
The original Erys VRM plus Dawnguard.esm:0023EB now completes conversion,
validation, ZIP creation and the actual close-up preview render. The generated
720x900 PNG was visually inspected. Launch.cmd was also run on an isolated
port, its .venv Python 3.11.13 log and live HTTP response checked, and that
verification server stopped.
