"""Run the public UI behind a TLS-terminating host with one explicit HTTPS origin."""
import os
import re
from urllib.parse import urlsplit


def hosting_settings(environ=None):
    """Validate public configuration before importing or starting the workbench."""
    environ = os.environ if environ is None else environ
    origin = environ.get("MIRAGE_PUBLIC_ORIGIN", environ.get("RENDER_EXTERNAL_URL", ""))
    if not origin:
        raise ValueError("Set MIRAGE_PUBLIC_ORIGIN or RENDER_EXTERNAL_URL to the exact HTTPS origin")
    try:
        parsed = urlsplit(origin)
        origin_port = parsed.port
        hostname = parsed.hostname or ""
    except ValueError:
        raise ValueError("Invalid public HTTPS origin") from None
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    valid_hostname = len(hostname) <= 253 and re.fullmatch(rf"{label}(?:\.{label})*", hostname)
    canonical = "https://" + hostname
    if origin_port is not None and origin_port != 443:
        canonical += f":{origin_port}"
    if (parsed.scheme != "https" or not valid_hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment
            or origin_port == 0 or origin != canonical):
        raise ValueError("Public origin must be canonical HTTPS, without path, credentials, wildcard, or default port")
    port_text = environ.get("PORT", "10000")
    if not re.fullmatch(r"[0-9]{1,5}", port_text) or not 1 <= int(port_text) <= 65535:
        raise ValueError("PORT must be an integer from 1 to 65535")
    return {"bind": "0.0.0.0", "port": int(port_text), "public_origin": origin}


def main():
    try:
        settings = hosting_settings()
    except ValueError as error:
        raise SystemExit(f"MIRAGE hosting configuration error: {error}") from None
    from mirage.server import serve
    serve(**settings)


if __name__ == "__main__":
    main()
