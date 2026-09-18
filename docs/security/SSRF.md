# SSRF Security Model (P0)

**Module:** `aeo_mvp.security.ssrf`  
**Decision:** D020  
**Date:** 2026-09-18 (IST)

## Goal

Prevent the crawler from fetching non-public or dangerous destinations (SSRF), including via redirects and DNS rebinding.

## Allow policy

1. **Scheme:** `http` or `https` only (`file://`, `ftp://`, etc. rejected).
2. **Hostname:** reject `localhost`, `*.localhost`, `*.local`, and known metadata host labels.
3. **DNS:** resolve with `socket.getaddrinfo`; **every** A/AAAA address must be a **global unicast public** IP.
4. **Rejected address classes:**
   - Loopback (`127.0.0.0/8`, `::1`)
   - RFC1918 private (`10/8`, `172.16/12`, `192.168/16`)
   - Link-local (`169.254.0.0/16`, `fe80::/10`) including cloud metadata `169.254.169.254`
   - Multicast, unspecified, reserved
   - IPv6 ULA `fc00::/7`
   - IPv4-mapped IPv6 that embeds a private IPv4
   - CGNAT `100.64.0.0/10`
5. **Redirects:** `follow_redirects=False`; manually follow at most **5** hops; each `Location` (absolute or joined) is re-validated and DNS re-resolved before the next request.
6. **Demo mode:** does not perform live fetches (fixtures only); SSRF applies to live crawl paths.

## API surface

| Function | Behavior |
| --- | --- |
| `assert_safe_public_url(url) -> str` | Normalize + full DNS/public-IP check; raise `SSRFError` |
| `is_obviously_unsafe_url(url) -> bool` | Cheap pre-check (scheme/host/literal IP, no DNS) for job create |
| `SSRFError` | Subclass of `ValueError` |

## Integration

- `crawler/fetch.fetch_url` — validates before every hop.
- `crawler/discover.crawl_live` — validates base URL up front; unsafe base fails the job.
- Job create API — rejects obviously unsafe URLs early (localhost, private literals, bad schemes) when not in demo mode.

## Out of scope (MVP)

- Full IP-pinning / custom transport (Host header pin) is desirable for defense-in-depth but not required for this P0 stub beyond re-resolve-per-hop.
- Allowlists of private ranges for lab use are not supported.

## Tests

See `tests/unit/test_ssrf.py`.
