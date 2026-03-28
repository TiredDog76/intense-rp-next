---
icon: material/shield-lock-outline
---

# :material-shield-lock-outline: IP Whitelist

Let's say you share a network with other people, or you expose IntenseRP through a tunnel to use it publicly. That's perfectly fine! But also insecure. Anyone on the same network or with access to the tunnel could potentially access your IntenseRP API and control it.

To avoid that, IP Whitelist lets you limit API access to specific IP addresses.

By default, it is off, and IntenseRP allows API access from any IP if that's the case.

:material-arrow-right: **Settings** -> **API Server** -> **Security** -> **Restrict Access by IP Address**

---

## When It Helps

- You enabled **Allow Local Network Access**
- You are running IntenseRP on a shared or open network
- You are exposing IntenseRP through a tunnel and want a tighter allowlist

---

## How To Use It

1. Turn on **Use IP Whitelist**
2. Add the IP addresses you want to allow
3. Save your settings

Once enabled, only those IPs can access the API. Everything else is blocked. **Make sure to add your own IP if you want to keep using the API!**

IntenseRP will also log all blocked access attempts, so you can check the console if you suspect something is trying to access your API without permission.

Example entries:

- `127.0.0.1`
- `192.168.1.50`

!!! note "Local Use"
    If you connect locally, add your local address, or else you'll lock yourself out. Some setups may also use `::1` instead of `127.0.0.1`.

!!! tip "Tunnels And Proxies"
    Some tunnels or reverse proxies may make IntenseRP see the tunnel or proxy IP instead of the original device IP. If something gets blocked unexpectedly, whitelist the IP that IntenseRP actually sees. I'm still working on improving this, though, since there's a reason you use a tunnel in the first place.

---

## :material-arrow-left: Back to Advanced

[:material-arrow-left: Advanced](../advanced.md)
