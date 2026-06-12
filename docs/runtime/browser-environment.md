---
icon: material/earth
---

# :material-earth: Browser Environment

Browser Environment controls the launch-time hints IntenseRP passes to provider pages.

:material-arrow-right: **Settings** -> **Browser & Runtime** -> **Browser Environment**

There are two settings here:

- **Preferred Browser Locale** defaults to **English (en-US)**. It affects browser language signals such as `navigator.language`, request language headers, and locale-sensitive formatting.
- **Browser Timezone** defaults to **System Default**. The built-in override is **New York (`America/New_York`)**.

This is best-effort, not a magic cloak. Saved provider preferences, account settings, cookies, local storage, and IP geolocation can still matter.

!!! tip "Recommended default"
    Keep the locale on **English (en-US)** unless you have a specific reason not to. IntenseRP's provider drivers expect English UI text, so this tends to be the most predictable choice.

Timezone is more situational. Leave it on **System Default** unless you specifically need a browser page to report New York time.

---

## :material-arrow-left: Back to Browser & Runtime

[:material-arrow-left: Browser & Runtime Overview](../runtime.md)
