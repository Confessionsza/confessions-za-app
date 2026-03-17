# confessions.za — Post Generator

A mobile web app to review, design, and save Instagram confession posts from Gmail.

---

## Features

- Pulls unread confessions from `info@confessionsza.com` (50 at a time, newest first)
- Accept (Public or Subscriber) or Reject each confession
- Auto-generates a styled post with rotating colours
- Holiday detection with emoji indicators
- Editable confession #, text, location, and colour before saving
- Separate numbering for public vs subscriber posts
- Saves image to your device (tap Save → Share → Save to Camera Roll on iOS)
- Deployed on Railway

---

## Setup

### 1. Google Cloud Console

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (e.g. `confessions-za`)
3. Enable the **Gmail API**
4. Go to **OAuth consent screen** → External → fill in app name & your email
5. Add scope: `https://www.googleapis.com/auth/gmail.modify`
6. Go to **Credentials** → Create OAuth 2.0 Client ID → Web Application
7. Add Authorized redirect URI: `https://YOUR-RAILWAY-APP.up.railway.app/oauth2callback`
8. Copy your **Client ID** and **Client Secret**

---

### 2. GitHub Repo

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/confessions-app.git
git push -u origin main
```

---

### 3. Railway Deployment

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select your repo
3. Add these **environment variables** in Railway:

| Key | Value |
|-----|-------|
| `GOOGLE_CLIENT_ID` | Your OAuth Client ID |
| `GOOGLE_CLIENT_SECRET` | Your OAuth Client Secret |
| `REDIRECT_URI` | `https://YOUR-APP.up.railway.app/oauth2callback` |
| `SECRET_KEY` | Any long random string |

4. Railway will auto-detect the Procfile and deploy

---

### 4. First Login

1. Open your Railway app URL on your phone
2. Tap **Connect Gmail**
3. Sign in with `info@confessionsza.com`
4. You'll be redirected back to the app

> ⚠️ **Important**: After deploying, go back to Google Cloud Console and add your actual Railway URL to the Authorized Redirect URIs.

---

## Usage

### Reviewing Confessions
- Confessions load newest first (toggle to Oldest in top bar)
- Holiday-related confessions show an emoji badge (🎄❤️🎆 etc.)
- The date each confession came through shows on the card

### Accepting a Confession
- Tap **✓ Public** → opens preview with public numbering
- Tap **⭐ Sub** → opens preview with subscriber numbering + "Subscribers Only" badge

### In the Preview
- Tap any colour swatch to change the background
- Edit the confession #, location, or text
- Tap **Save to Camera Roll** → the image downloads
- On iPhone: the file downloads, go to Files app and save to Photos, or the browser may prompt to save directly

### Rejecting
- Tap **✕ Reject** → archives the email (removes from inbox)

### Numbers Auto-Advance
- After saving, the next confession will automatically be #next
- Public and Subscriber numbers are tracked separately
- Colour rotation advances automatically too

---

## Colour Palette

| # | Colour |
|---|--------|
| 1 | Lavender `#C5A8D4` |
| 2 | Green `#6CC76C` |
| 3 | Salmon `#E89090` |
| 4 | Dark Navy `#2C3E4A` |
| 5 | Cornflower Blue `#7AA8F0` |
| 6 | Deep Purple `#6B2D8B` |
| 7 | Burgundy `#6B2535` |
| 8 | Golden Yellow `#E5BE4A` |

---

## Notes

- **State persistence**: The `confession_state.json` file stores your current numbers and colour index. On Railway, this resets on redeploy. To persist it, consider adding a Railway Volume or storing state in a small DB.
- **Session**: Gmail auth is stored in the Flask session. If you clear cookies, you'll need to re-authenticate.
- **OAUTHLIB_INSECURE_TRANSPORT**: Set to `'0'` in production (already handled — Railway uses HTTPS).
