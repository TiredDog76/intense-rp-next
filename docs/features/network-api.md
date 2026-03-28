---
icon: material/lan
---

# :material-lan: Network & API

Configure how IntenseRP listens for incoming requests from SillyTavern and other clients. These settings control the port, network accessibility, and authentication.

---

## :material-numeric: Server Port

The port number where IntenseRP's API server listens for requests. Default is `7777`.

:material-arrow-right: **Settings** → **API Server** → **Access** → **Server Port**

![Network settings](../pics/features/api_server.png)

### Changing the Port

If port 7777 is already in use by another application, just pick a different one. Common alternatives are `8080`, `3000`, or any number between `1024` and `65535`.

!!! warning "Update SillyTavern Too"
    If you change the port here, don't forget to update your SillyTavern endpoint to match:
    
    ```
    http://127.0.0.1:YOUR_PORT/v1
    ```

---

## :material-lan-connect: Allow Local Network Access

By default, IntenseRP only accepts connections from your own computer (`localhost` / `127.0.0.1`). Enable LAN availability to let other devices on your network connect.

:material-arrow-right: **Settings** → **API Server** → **Access** → **Allow Local Network Access**

### When to Use This

- Running SillyTavern on a different machine (like a phone or tablet)
- Sharing your IntenseRP instance with others on your home network
- Using a remote desktop or VM setup

### How It Works

| Setting | Server Binds To | Who Can Connect |
|---------|-----------------|-----------------|
| **Off** (default) | `127.0.0.1` | Only this computer |
| **On** | `0.0.0.0` | Any device on your network |

### Finding Your IP

To connect from another device, you'll need your computer's local IP address. On most networks this looks like `192.168.x.x` or `10.x.x.x`.

!!! tip "Show the Server Address in Logs"
    If **Show the Server Address in Logs** is enabled (see below), IntenseRP automatically logs all server addresses to the console when it starts - including your LAN IP. No need to run `ipconfig` or `ip addr`.

=== ":material-microsoft-windows: Windows"

    Open Command Prompt and run:
    ```
    ipconfig
    ```
    Look for "IPv4 Address" under your active network adapter.

=== ":material-linux: Linux"

    Open a terminal and run:
    ```bash
    ip addr
    ```
    Or:
    ```bash
    hostname -I
    ```

Then use that IP in your client's endpoint:
```
http://192.168.1.100:7777/v1
```

!!! tip "Security Note"
    Enabling LAN access means anyone on your local network could potentially use your IntenseRP instance. Consider enabling API keys (below) if you're on a shared network.

---

## :material-monitor-eye: Show the Server Address in Logs

When enabled, IntenseRP prints the server address(es) to the console each time the API server starts. This is on by default.

:material-arrow-right: **Settings** → **API Server** → **Access** → **Show the Server Address in Logs**

With **Allow Local Network Access** off, you'll see:

```
Server running at http://127.0.0.1:7777
```

With **Allow Local Network Access** on, all detected local IPv4 addresses are printed as well:

```
Server running at http://127.0.0.1:7777
Server running at http://192.168.1.100:7777
```

Disable this if you'd rather not have the address logged on every start.

---

## :material-key-variant: Require API Keys

Add an extra layer of security by requiring an API key for all incoming requests. When enabled, clients must include a valid key in the `Authorization` header.

:material-arrow-right: **Settings** → **API Server** → **Security** → **Require API Keys**

### Setting Up API Keys

1. Toggle on **Require API Keys**
2. Add one or more key pairs:

    - **Name**: A label to identify this key (e.g., "SillyTavern", "Phone", "Laptop")
    - **Key**: The actual secret value (make it long and random!)

3. Save your settings

### Using Keys in SillyTavern

In SillyTavern's API connection settings, enter your key in the **API Key** field. SillyTavern will automatically send it as a Bearer token:

```
Authorization: Bearer your-secret-key-here
```

### How Authentication Works

When a request comes in:

1. IntenseRP checks if API keys are enabled
2. If yes, it looks for an `Authorization: Bearer xxx` header
3. It compares the token against your saved keys
4. If there's a match, the request proceeds (and the key name is logged)
5. If not, the request is rejected with a 401 error

!!! note "Multiple Keys"
    You can create multiple keys - one for each device or person. This makes it easy to revoke access for a specific client without affecting others.

---

## :material-api: API Endpoints

IntenseRP exposes an OpenAI-compatible API. Here are the available endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List available models |
| `/v1/chat/completions` | POST | Generate a chat completion |
| `/v1/completions` | POST | Generate a text completion from a raw prompt |

`/v1/completions` is the legacy prompt-based route. Unlike chat completions, it sends your prompt as-is after macro stripping, so chat templates, injections, and name scanning are skipped on purpose.

### Available Models

When you query `/v1/models`, you'll get different model IDs depending on the active provider (**Settings -> Provider and Login -> Current Provider**).

These IDs are behavior presets (modes), not true model selection.

=== ":material-brain: DeepSeek"

    | Model ID | Behavior |
    |----------|----------|
    | `deepseek-auto` | Uses your IntenseRP settings |
    | `deepseek-chat` | Forces DeepThink off |
    | `deepseek-reasoner` | Forces DeepThink on |

=== ":material-chat-processing: GLM Chat"

    | Model ID | Behavior |
    |----------|----------|
    | `glm-auto` | Uses your IntenseRP settings |
    | `glm-chat` | Forces Deep Think off |
    | `glm-reasoner` | Forces Deep Think on |

=== ":material-meteor: Moonshot"

    | Model ID | Behavior |
    |----------|----------|
    | `moonshot-auto` | Uses your IntenseRP settings |
    | `moonshot-chat` | Forces Thinking off |
    | `moonshot-reasoner` | Forces Thinking on |

=== ":material-chat: QwenLM"

    | Model ID | Behavior |
    |----------|----------|
    | `qwen-auto` | Uses your IntenseRP settings |
    | `qwen-chat` | Forces Thinking off |
    | `qwen-reasoner` | Forces Thinking on |

=== ":material-image-auto-adjust: Google AI Studio"

    | Model ID | Behavior |
    |----------|----------|
    | `aistudio-auto` | Uses your IntenseRP settings |
    | `aistudio-chat` | Suppresses `<think>` output and lowers Thinking Level on supported Gemini 3 / 3.1 models |
    | `aistudio-reasoner` | Uses your configured Thinking Level and Send Thinking setting |

---

## :material-frequently-asked-questions: Quick FAQ

??? question "What port should I use?"
    Any port between 1024-65535 that isn't already in use. The default `7777` works for most people. Avoid well-known ports like 80, 443, 8080 unless you know what you're doing.

??? question "Can I access IntenseRP from the internet?"
    Not recommended! IntenseRP is designed for local/LAN use. Exposing it to the internet would require port forwarding and proper security measures. If you really need remote access, consider a VPN instead.

??? question "My client can't connect on LAN?"
    Check that:
    
    1. **Allow Local Network Access** is enabled
    2. Your firewall allows connections on the port
    3. You're using the correct local IP (not `localhost`)
    4. Both devices are on the same network

??? question "How do I generate a good API key?"
    Use any password generator or run this in a terminal:
    
    ```bash
    openssl rand -hex 32
    ```
    
    Or just mash your keyboard - as long as it's long and random!

---

!!! tip "Need deeper API details?"
    See [:material-api: API Behavior](../advanced/api-behavior.md) for request flow, streaming, cancellation, and queueing.

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features Overview](../features.md)
