"""
Google Drive client — downloads all video clips from a shared folder.
Requires OAuth2 credentials from Google Cloud Console.
See scripts/setup_drive.md for setup instructions.
"""

import os
import re
from pathlib import Path
from tqdm import tqdm

from src.config import GOOGLE_DRIVE_CREDENTIALS_PATH, TEMP_DIR, SUPPORTED_EXTENSIONS


def _get_folder_id(folder_url: str) -> str:
    """Extract folder ID from a Google Drive URL."""
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", folder_url)
    if not match:
        raise ValueError(f"Could not extract folder ID from URL: {folder_url}")
    return match.group(1)


def _build_service():
    """Build and return an authenticated Google Drive service."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    token_path = "./token.json"
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_DRIVE_CREDENTIALS_PATH, scopes
            )
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def download_folder(folder_url: str) -> list[str]:
    """
    Download all video files from a Google Drive folder.
    Returns list of local file paths.
    """
    from googleapiclient.http import MediaIoBaseDownload
    import io

    folder_id = _get_folder_id(folder_url)
    service = _build_service()

    print(f"📂 Fetching file list from Drive folder...")
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, mimeType, size)",
        pageSize=200,
    ).execute()

    files = results.get("files", [])
    video_files = [
        f for f in files
        if Path(f["name"]).suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not video_files:
        raise ValueError(f"No video files found in Drive folder. Supported formats: {SUPPORTED_EXTENSIONS}")

    print(f"Found {len(video_files)} video files. Downloading...")

    local_paths = []
    for file in tqdm(video_files, desc="Downloading clips"):
        local_path = os.path.join(TEMP_DIR, file["name"])

        if os.path.exists(local_path):
            print(f"  ↩ Skipping {file['name']} (already downloaded)")
            local_paths.append(local_path)
            continue

        request = service.files().get_media(fileId=file["id"])
        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request, chunksize=10 * 1024 * 1024)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        local_paths.append(local_path)

    print(f"✅ Downloaded {len(local_paths)} clips to {TEMP_DIR}")
    return local_paths


def get_local_clips(folder_path: str) -> list[str]:
    """Return all video file paths from a local folder."""
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Local folder not found: {folder_path}")

    clips = [
        str(f) for f in sorted(folder.iterdir())
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not clips:
        raise ValueError(f"No video files found in {folder_path}")

    print(f"✅ Found {len(clips)} clips in {folder_path}")
    return clips
