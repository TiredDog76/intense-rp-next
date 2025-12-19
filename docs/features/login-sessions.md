---
icon: material/key
---

# :material-key: Login & Sessions

Managing how you log in to DeepSeek and keeping your session alive between restarts. These two features work together to make your life easier.

---

## :material-login: Auto Login

If you tired of typing your password every time, Auto Login saves your DeepSeek credentials and enters them automatically when the browser opens.

![Login settings](../pics/features/login_settings.png)

### Setting It Up

1. Go to **Settings** → **Providers & Credentials**
2. Toggle on **Auto Login**
3. Enter your **DeepSeek Email** and **Password**
4. Click **Save**

Next time you start IntenseRP, it'll fill in your credentials and click the login button for you.

### How It Works

When IntenseRP detects you've been redirected to the DeepSeek sign-in page:

1. It waits for the login form to appear
2. Fills in your email and password
3. Clicks the login button
4. Waits for the redirect back to the chat page

If anything goes wrong (wrong password, captcha, etc.), you'll see an error in the console and can log in manually.

!!! note "Manual Login"
    If Auto Login is disabled, IntenseRP just waits patiently :service_dog: for you to log in yourself. Take your time - it won't time out.

---

## :material-cookie: Persistent Sessions

This one's even better. Instead of logging in every time (even automatically), Persistent Sessions saves your browser profile so you stay logged in between restarts.

### How It Works

When enabled, IntenseRP uses a "persistent browser context" - basically saving cookies, local storage, and session data to a folder on your computer. Next time you start the app, it loads that profile and you're already logged in.

:material-arrow-right: **Settings** → **System Settings** → **Persistent Sessions**

### Where's the Data Stored?

The browser profile is saved in your config directory:

```
[config_dir]/playwright_profiles/deepseek/
```

This folder contains your DeepSeek session cookies and any browser data. It's automatically created when you first enable Persistent Sessions.

!!! tip "Best of Both Worlds"
    You can use both features together! Enable Persistent Sessions so you're usually already logged in, and keep Auto Login as a backup for when the session expires.

---

## :material-delete: Clearing Your Profile

If you want to start fresh or log out completely, you can wipe the saved browser profile:

:material-arrow-right: **Settings** → **System Settings** → **Clear Profile**

This deletes the saved profile folder, which:

- Removes all cookies and session data
- Logs you out of DeepSeek
- Forces a fresh login next time

!!! warning "This Can't Be Undone"
    Once cleared, you'll need to log in again. If you have Auto Login enabled, this happens automatically. Otherwise, you'll log in manually.

---

## :material-frequently-asked-questions: Quick FAQ

??? question "Do I need both Auto Login and Persistent Sessions?"
    Nope! You can use either one:
    
    - **Just Auto Login**: Logs in fresh every time (slower, but always works)
    - **Just Persistent Sessions**: Stays logged in until the session expires
    - **Both**: Best reliability - persistent session when it works, auto login as fallback

??? question "My session keeps expiring?"
    DeepSeek sessions do expire eventually. If Persistent Sessions isn't keeping you logged in long enough, make sure you also have Auto Login configured as a backup.

??? question "Is my password stored securely?"
    Your credentials are saved in the config file on your local machine. IntenseRP doesn't send them anywhere except to DeepSeek's login form. If you're concerned, you can skip Auto Login and log in manually each time.

??? question "Can I use this with multiple DeepSeek accounts?"
    Not directly - the app only supports one set of credentials at a time. You'd need to clear the profile and change credentials to switch accounts.

---

## :material-arrow-left: Back to Features

[:material-arrow-left: Features Overview](../features.md)
