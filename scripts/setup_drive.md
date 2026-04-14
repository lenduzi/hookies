# Google Drive API Setup

Follow these steps once to enable Drive integration.

## 1. Create a Google Cloud Project

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Click **New Project** → name it `ugc-cut-generator`
3. Select the project

## 2. Enable the Drive API

1. Go to **APIs & Services → Library**
2. Search for **Google Drive API**
3. Click **Enable**

## 3. Create OAuth2 Credentials

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User type: **External**
   - App name: `UGC Cut Generator`
   - Add your email as a test user
4. Application type: **Desktop app**
5. Click **Create**
6. Click **Download JSON**
7. Rename the file to `credentials.json` and place it in the root of this project

## 4. First Run (OAuth Flow)

On first run, a browser window will open asking you to authorise access to your Google Drive. After authorising, a `token.json` file is created locally — you won't need to do this again.

```bash
python main.py --source drive --folder-url "https://drive.google.com/drive/folders/YOUR_FOLDER_ID"
```

## Notes

- `credentials.json` and `token.json` are in `.gitignore` — never commit them
- The app only requests **read-only** access to Drive (`drive.readonly` scope)
- If the creator shares a folder link with you, make sure it's set to **"Anyone with the link can view"** or add your Google account as a viewer
