---
icon: material/newspaper-variant-outline
---

<!-- NOTE FOR SELF: Increment .github/state/latestnews.txt after you're done writing here or else nobody will get the bell indicator -->

# :material-newspaper-variant-outline: News

This page is the changelog for the latest news and updates about IntenseRP Next.

## June 12, 2026 - Update 2.8.8

IntenseRP Next v2.8.8 is a smaller release with two very practical wins: **Google AI Studio is back**, and **Providers in Parallel is no longer tucked Experimental**.

AI Studio is selectable again thanks to the new default **Humanize Mouse Movements** reliability mode. It is slower on purpose, because AI Studio really did not enjoy the instant-move / instant-click treatment, but it makes browser sends much more reliable.

Providers in Parallel now lives under **Browser & Runtime**, and it can do more than keep extra provider lanes warm. Depending on the mode you choose, different provider lanes can answer queued API requests at the same time, and startup can launch active lanes concurrently. If that startup burst is too heavy, batching is there too (still speeds things up, but with more breathing room).

[Full Release Notes](https://github.com/LyubomirT/intense-rp-next/releases/tag/v2.8.8-patch){ .md-button .md-button--primary }
[Join our Discord](https://discord.gg/4Gvjk2RdsK){ .md-button }
[Google AI Studio Behavior](providers/aistudio-behavior.md){ .md-button }
[Providers in Parallel](runtime/providers-in-parallel.md){ .md-button }
[Support the Project](hands/support.md){ .md-button }

---

## June 1, 2026 - Update 2.8.6

IntenseRP Next v2.8.6 is mostly a follow-up to the 2.8.5 provider work, but the headline is simple: **HuggingChat support is finally here**.

If DeepSeek has been giving you trouble lately, HuggingChat gives you another account-backed provider lane and broader access to some models exposed through `huggingface.co/chat`. It includes real model selection, inference provider hints, Thinking Effort, Exa search, prompt uploads, chat reuse, and account rotation.

That said, it's still not a magic solution. HuggingChat is still an early integration that depends on the web UI, and its monthly credits are a little tiny. The [HuggingChat Behavior docs](providers/huggingchat-behavior.md) cover the main things, credit limits, and account rotation setup.

[Full Release Notes](https://github.com/LyubomirT/intense-rp-next/releases/tag/v2.8.6-patch){ .md-button .md-button--primary }
[Join our Discord](https://discord.gg/4Gvjk2RdsK){ .md-button }
[HuggingChat Feedback](https://forms.gle/J7MVdcnorEPE249v8){ .md-button }
[Support the Project](hands/support.md){ .md-button }

---

## April 29, 2026 - Update 2.8.0

IntenseRP Next v2.8.0 is here, and the headline is **Perplexity support**. It works with both free and paid accounts, can stream answer text through the normal OpenAI-compatible API, and includes Perplexity-specific settings for model selection, Thinking, Search, and text-file prompt uploads where the account allows them.

This integration exists thanks to [Yurushia](https://github.com/twgok123), who sponsored Perplexity development and provided access to a paid account for testing. Huge thank you to them for making this one possible!!!

This release also includes some recent power-user and maintenance work: Full Parallelization for provider lanes, selective provider restarts when switching loadouts, AI Studio CAARS options, backup/import polish, and a more maintainable Remote Control frontend.

[Full Release Notes](https://github.com/LyubomirT/intense-rp-next/releases/tag/v2.8.0-update){ .md-button .md-button--primary }
[Join our Discord](https://discord.gg/4Gvjk2RdsK){ .md-button }
[Suggest New Features](./vote-for-new-stuff.md){ .md-button }
[Perplexity Behavior](providers/perplexity-behavior.md){ .md-button }
[Support the Project](hands/support.md){ .md-button }

---

## March 28, 2026 - Update 2.6.3

IntenseRP Next v2.6.3 is mostly a quality-of-life update, and the biggest visible change is the **Settings redesign**. The whole thing is meant to feel cleaner, easier to read, and a lot more intuitive to move around in.

This update also brings **Providers in Parallel**, which can keep multiple provider browsers alive at once so different providers can work side by side, plus **Loadouts**, a validated `loadouts.json` system for people who would rather manage formatting and provider behavior through a file and quickly jump between presets instead of clicking through the UI every time.

GLM also gets **GLM-5-Turbo** as a selectable real model option under **Provider Behavior -> GLM Chat -> Model**, alongside the existing GLM model choices.

[Full Release Notes](https://github.com/LyubomirT/intense-rp-next/releases/tag/v2.6.3-patch){ .md-button .md-button--primary }
[Join our Discord](https://discord.gg/4Gvjk2RdsK){ .md-button }
[Suggest New Features](./vote-for-new-stuff.md){ .md-button }
[Support the Project](hands/support.md){ .md-button }

---

## March 20, 2026 - About Sustainability

IntenseRP Next is a free and open-source project, and I want to keep it that way. But maintaining and developing a project like this takes a lot of time and effort, especially considering that it's a one-person project. I've been thinking about a more sustainable way to support it in the long run, so I've created a [survey](https://forms.gle/Dx9BA2kogYcjbdm37) to see what the community is and isn't comfortable with. If you have a moment, please fill it out and share your thoughts! I'd really appreciate the feedback, it will help me pick the best path for the project.

If you were already looking for a way to support the project, you can also check out the [Support page](hands/support.md) for some options.



## March 19, 2026 - Update 2.6.1

IntenseRP Next v2.6.1 is here with two small but useful upgrades.

Moonshot now supports an experimental **Auto Login** flow for its Google popup, so IntenseRP can try to fill the sign-in steps for you before falling back to manual completion if Google decides to be Google.

Multi-Slot Cache is also now available on every current driver except **Google AI Studio**, which means **DeepSeek**, **GLM Chat**, **Moonshot**, and **QwenLM** can now look through older cached chats instead of only remembering the latest one. This is especially useful if you swipe a lot. More about that in the [Multi-Slot Cache docs page](features/multi-slot-cache.md).

[Full Release Notes](https://github.com/LyubomirT/intense-rp-next/releases/tag/v2.6.1-patch){ .md-button .md-button--primary }
[Join our Discord](https://discord.gg/4Gvjk2RdsK){ .md-button }
[Suggest New Features](https://forms.gle/cRGEoTNKxUrjKRJ2A){ .md-button }

---

## 🎉 March 14, 2026 - Update 2.6.0

IntenseRP Next v2.6.0 is out, and the big headline is **Google AI Studio support**. It already includes streaming, Google login handling, model switching, and sampling controls, but it is still a bit beta-ish for now, so please poke it gently and let me know if something feels off.

This update also brings some nice extra polish: Moonshot now gets RP-friendly auto-adjustments just like Qwen, the Settings window loads much faster, mini help buttons were added around settings, the console got its own search, and there is a new v1-style multiline XML-like formatting preset too.

[Full Release Notes](https://github.com/LyubomirT/intense-rp-next/releases/tag/v2.6.0-update){ .md-button .md-button--primary }
[Join our Discord](https://discord.gg/4Gvjk2RdsK){ .md-button }
[Suggest New Features](https://forms.gle/JCe8FQ27mPgdEGes7){ .md-button }

---

## March 11, 2026 - Official Discord Server

The official Discord server is finally here! :tada: 

Based on the latest survey results, a majority vote favored creating a community space, so I've gone ahead and set it up. It's a little quiet for now since it's just starting out, but I'm hoping to expand it and see the community grow soon. If you want a place to chat, get support, or follow the latest updates more closely, come hang out!

[Join the Discord Server](https://discord.gg/4Gvjk2RdsK){ .md-button .md-button--primary }

---

## March 10, 2026 - News / Changelog is open

Welcome to the new News and Changelog page! :material-newspaper:

I've set up this place to keep everyone updated on the latest developments, features, and improvements in IntenseRP Next. Whenever there's a new update or important news, you'll find it here first. Make sure to check back regularly to stay in the loop with all the changes coming your way!
