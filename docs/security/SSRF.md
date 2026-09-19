# SSRF Security Model (P0 + P0-2 IP pinning)

**Module:** `aeo_mvp.security.ssrf`  
**Decision:** D020  
**Date:** 2026-09-18 (IST); IP pinning 2026-09-19

## Goal

Prevent the crawler from fetching non-public or dangerous destinations (SSRF), including via redirects and DNS rebinding (TOCTOU between validate-time and connect-time DNS).

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
5. **IP pinning (P0-2):** for each outbound hop, resolve **once**, validate every address, then connect **only** to those validated IPs. The logical hostname is preserved for the HTTP `Host` header and TLS `sni_hostname` (certificate verification remains enabled). Never validate against one IP and connect to an independently re-resolved IP.
6. **Redirects:** `follow_redirects=False`; manually follow at most **5** hops; each `Location` (absolute or joined) is freshly resolved and validated; the same `ValidatedFetchTarget` is reused for that hop’s connect (no second DNS between validate and connect).
7. **Demo mode:** does not perform live fetches (fixtures only); SSRF applies to live crawl paths.

## API surface

| Function | Behavior |
| --- | --- |
| `validate_url_for_fetch(url) -> ValidatedFetchTarget` | Normalize + single DNS resolve + public-IP check; returns logical URL + `validated_ips` |
| `assert_safe_public_url(url) -> str` | Same validation; returns normalized URL only |
| `pinned_connect_url(target, ip) -> str` | Rewrite authority to a validated IP for TCP connect |
| `request_extensions_for_pin(target)` | httpcore `sni_hostname` for TLS when scheme is https |
| `is_obviously_unsafe_url(url) -> bool` | Cheap pre-check (scheme/host/literal IP, no DNS) for job create |
| `SSRFError` | Subclass of `ValueError` |

## Integration

- `crawler/fetch.fetch_url` — `validate_url_for_fetch` + pinned `client.get` (IP URL, `Host`, `sni_hostname`) before every hop.
- `crawler/discover.crawl_live` — validates base URL up front; unsafe base fails the job; page fetches go through `fetch_url`.
- Job create API — rejects obviously unsafe URLs early (localhost, private literals, bad schemes) when not in demo mode.

## Out of scope

- Allowlists of private ranges for lab use are not supported.
- Global DNS caching is **not** used as the rebinding fix (would not pin the connect IP).

## Tests

See `tests/unit/test_ssrf.py` (deterministic mocked DNS; local TLS fixture for pin + SNI/Host/verify).
