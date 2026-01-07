## PinRecon v1.5.1  
**Pinterest Board Pin Extractor & Downloader (Correctness-First, CLI)**

PinRecon downloads pins from a Pinterest board **without copying cookies, without asking for passwords, and without losing pins**.

It is designed for people who care more about **completeness and safety** than speed.

---

## What PinRecon does

- Extracts **all pins** from a Pinterest board  
- Works with **public and private boards** you have access to  
- Avoids duplicate downloads  
- Remembers what was already downloaded  
- Can be safely stopped and resumed  

---

## What PinRecon does NOT do

- ❌ Does NOT ask for your email or password  
- ❌ Does NOT ask you to paste cookies or session data  
- ❌ Does NOT upload any data anywhere  
- ❌ Does NOT run in the background  
- ❌ Does NOT modify your system  

Everything stays on your computer.

---

## How login works

**You log in directly on Pinterest, not in PinRecon.**

Here is exactly what happens:

1. PinRecon opens a **real browser window** (Firefox)  
2. The browser goes to **Pinterest’s official login page**  
3. **You type your password into Pinterest**, like normal  
4. Pinterest logs you in and you closes the browser  
5. PinRecon remembers that browser session for future runs  

👉 **PinRecon never sees your password.**  
👉 **PinRecon cannot read your password.**  
👉 **PinRecon never asks for credentials.**

This is the same as opening Pinterest yourself — PinRecon only automates scrolling.

---

## Why PinRecon exists

Many Pinterest downloaders ask users to:
- copy cookies  
- paste session tokens  
- paste request headers  

That moves sensitive login data **out of the browser**, which is unsafe.

PinRecon avoids this entirely by letting the browser handle login.

---

## When you should use PinRecon

- You want to download **your own private or secret boards**  
- You want **all pins**, not “most pins”  
- You want a tool that can be stopped and resumed safely  
- You do NOT want to paste cookies or credentials anywhere  

---

## When you should NOT use PinRecon

- You only want a few images from a small public board  
- You want the fastest possible downloader  
- You are uncomfortable running any automation tools  

PinRecon prioritizes correctness and security not speed. But, still it is fast.

---

## How to run

### Windows (recommended)

1. Download the ZIP from **GitHub Releases**  
2. Extract the folder  
3. Run `PinRecon.exe`  
4. Follow on-screen instructions  

No installation.  
Delete the folder to remove PinRecon.

---


## 🔧 Developer Setup

This section is for developers who want to run **PinRecon from source code**.

### Requirements

- Python **3.9 or newer**
- Git
- Internet connection (for Playwright browser installation)

---

### Setup

Clone the repository:

```bash
git clone https://github.com/MehraYash524/pinrecon.git
cd pinrecon
```

Install dependencies:
```bash
pip install -r requirements.txt
```
Install Playwright browsers:
```bash
playwright install firefox
```
Run from source
```bash
python PinRecon.py
```
## Files and folders created

PinRecon creates files **only inside its own folder**:

- `user_data/` → browser login profile (managed by Firefox)  
- `history/` → remembers which pins were already processed  
- `downloads/` → saved images  
- `.runtime_guard` → crash-recovery state  
- `.session_lock` → prevents accidental double runs  
- `.login_trust` → checks your login

Nothing is written outside the PinRecon folder.

---

## Antivirus warnings

Some antivirus programs may show warnings for automation tools or large executables.

This is common for:
- browser automation tools  
- bundled browsers  
- portable executables  

PinRecon does not hide behavior, does not auto-update, and does not communicate with third-party servers.  
The full source code is available on GitHub for inspection.

---

## Disclaimer

- PinRecon is **not affiliated with Pinterest**  
- Use it only with boards you own or have permission to access  
- You are responsible for how you use the tool  

---

## License

MIT License — free to use, modify, and inspect.  
Provided **as-is**, without warranty.

---

## Summary

- You log in on Pinterest, not in PinRecon  
- No passwords, no cookies, no uploads  
- Built for correctness and safety  
- Portable, transparent, removable  

If that matches what you want, PinRecon is the right tool.
