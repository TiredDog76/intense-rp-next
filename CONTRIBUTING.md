# Contributing

Thanks for helping out!
This project moves fast (and provider web UIs change often), so small, focused contributions work best.

Before you start: please follow our `CODE_OF_CONDUCT.md`.

## Quick guidelines

- If you're not sure where to start, open an issue first.
- Keep PRs small and scoped to one thing.
- Avoid drive-by refactors (they get painful to review and go stale quickly).

## Bug reports

GitHub issues are best: https://github.com/LyubomirT/intense-rp-next/issues

Please include:

- your version (see `version.json`)
- OS (Windows/Linux) and anything unusual about your setup
- exact steps to reproduce (what you clicked / what you sent)
- what you expected vs what happened
- logs (please redact passwords, API keys, and personal info)

## Feature requests

Open an issue and describe the use case. Screenshots and concrete examples help a lot.

## Dev setup (from source)

Requirements: Python 3.12+ (3.13 recommended)

```bash
git clone https://github.com/LyubomirT/intense-rp-next.git
cd intense-rp-next

python -m venv venv

source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt

# Optional, since IntenseRP can auto-download browsers
playwright install chromium

python main.py
```

## Pull requests

- Open an issue first for anything big or behavior-changing.
- Match the existing style and structure (especially in the UI and provider drivers).
- If you change user-facing behavior, update docs in `docs/` when it makes sense.
- Please do not commit generated/local stuff like `venv/`, `dist/`, `build/`, `config_data/`, `cache/`, or `logs/` (they are in `.gitignore`).

## Need to reach the maintainer?

For general discussion, use GitHub issues/PRs or Discussions.
For private/sensitive topics, email `ternavski103@gmail.com` (or DM `@lyubomirt` on Discord / `@LyubomirT` on Telegram).
