import os
import json
import base64
import re
from datetime import datetime
from flask import Flask, jsonify, request, session, redirect, url_for, render_template
from flask_cors import CORS
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from dotenv import load_dotenv
import html

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'confessions-secret-key-change-in-prod')
CORS(app)

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.readonly'
]

CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get('GOOGLE_CLIENT_ID'),
        "client_secret": os.environ.get('GOOGLE_CLIENT_SECRET'),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [os.environ.get('REDIRECT_URI', 'http://localhost:5000/oauth2callback')]
    }
}

# State file for persisting confession numbers
STATE_FILE = 'confession_state.json'

# Credentials file for persisting Gmail OAuth tokens
CREDS_FILE = 'gmail_credentials.json'

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"public_number": 1, "subscriber_number": 1, "color_index": 0, "sub_color_index": 0}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def save_credentials(creds):
    """Persist OAuth credentials to disk so they survive server restarts."""
    data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES
    }
    with open(CREDS_FILE, 'w') as f:
        json.dump(data, f)

def load_credentials_from_file():
    """Load saved credentials from disk, return dict or None."""
    if os.path.exists(CREDS_FILE):
        with open(CREDS_FILE, 'r') as f:
            return json.load(f)
    return None

COLORS = [
    "#C5A8D4",  # lavender
    "#6CC76C",  # green
    "#E89090",  # salmon
    "#2C3E4A",  # dark navy
    "#7AA8F0",  # cornflower blue
    "#6B2D8B",  # deep purple
    "#6B2535",  # burgundy
    "#E5BE4A",  # golden yellow
]

HOLIDAY_KEYWORDS = {
    "christmas": {"keywords": ["christmas", "xmas", "santa claus", "christmas tree", "christmas eve", "christmas day", "festive season", "carols"], "emoji": "🎄"},
    "mothers_day": {"keywords": ["mothers day", "mother's day", "happy mothers", "mothers day today"], "emoji": "💐"},
    "fathers_day": {"keywords": ["fathers day", "father's day", "happy fathers", "fathers day today"], "emoji": "👨‍👧"},
    "easter": {"keywords": ["easter", "good friday", "easter sunday", "easter egg", "easter bunny", "easter weekend"], "emoji": "🐣"},
    "new_year": {"keywords": ["new year", "new years", "happy new year", "nye", "new years eve", "new years day", "january 1", "new year's"], "emoji": "🎆"},
    "valentines": {"keywords": ["valentine", "valentines day", "valentine's day", "happy valentines", "february 14", "be my valentine"], "emoji": "❤️"},
}

def detect_holiday(text):
    text_lower = text.lower()
    for holiday, data in HOLIDAY_KEYWORDS.items():
        for kw in data["keywords"]:
            if kw in text_lower:
                return data["emoji"]
    return None

def get_gmail_service():
    creds_data = session.get('credentials')

    # Fall back to file-persisted credentials if session is empty
    if not creds_data:
        creds_data = load_credentials_from_file()
        if not creds_data:
            return None
        # Restore into session so subsequent requests are faster
        session['credentials'] = creds_data

    creds = Credentials(**creds_data)
    service = build('gmail', 'v1', credentials=creds)

    # Persist refreshed token back to both session and file
    updated = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES
    }
    session['credentials'] = updated
    save_credentials(creds)
    return service

def parse_email_body(service, msg_id):
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    
    body = ""
    payload = msg.get('payload', {})
    
    def extract_body(part):
        if part.get('mimeType') == 'text/plain':
            data = part.get('body', {}).get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
        elif part.get('mimeType') == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                raw = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                # Strip HTML tags
                clean = re.sub('<[^<]+?>', ' ', raw)
                clean = html.unescape(clean)
                return clean
        for sub in part.get('parts', []):
            result = extract_body(sub)
            if result:
                return result
        return ""
    
    body = extract_body(payload)
    
    # Parse fields
    parsed = {
        'confession': '',
        'location': '',
        'email': '',
        'phone': '',
    }
    
    lines = body.split('\n')
    current_field = None
    current_value = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        lower = line.lower()
        if lower.startswith('confession:') or lower.startswith('confession :'):
            if current_field:
                parsed[current_field] = ' '.join(current_value).strip()
            current_field = 'confession'
            current_value = [line.split(':', 1)[1].strip()] if ':' in line else []
        elif lower.startswith('location:') or lower.startswith('location :') or lower.startswith('city:'):
            if current_field:
                parsed[current_field] = ' '.join(current_value).strip()
            current_field = 'location'
            current_value = [line.split(':', 1)[1].strip()] if ':' in line else []
        elif lower.startswith('email:') or lower.startswith('email :'):
            if current_field:
                parsed[current_field] = ' '.join(current_value).strip()
            current_field = 'email'
            current_value = [line.split(':', 1)[1].strip()] if ':' in line else []
        elif lower.startswith('phone:') or lower.startswith('phone :'):
            if current_field:
                parsed[current_field] = ' '.join(current_value).strip()
            current_field = 'phone'
            current_value = [line.split(':', 1)[1].strip()] if ':' in line else []
        elif lower.startswith('email me with') or lower.startswith('newsletter'):
            if current_field:
                parsed[current_field] = ' '.join(current_value).strip()
            current_field = None
            current_value = []
        else:
            if current_field:
                current_value.append(line)
    
    if current_field and current_value:
        parsed[current_field] = ' '.join(current_value).strip()
    
    # If parsing failed, use whole body as confession
    if not parsed['confession'] and body.strip():
        # Try simpler approach - look for confession keyword anywhere
        match = re.search(r'[Cc]onfession[:\s]+(.+?)(?:\n\s*[A-Za-z]+:|$)', body, re.DOTALL)
        if match:
            parsed['confession'] = match.group(1).strip()
        else:
            parsed['confession'] = body.strip()[:500]
    
    loc_match = re.search(r'[Ll]ocation[:\s]+(.+?)(?:\n|$)', body)
    if loc_match and not parsed['location']:
        parsed['location'] = loc_match.group(1).strip()
    
    return parsed

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/authorize')
def authorize():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
    flow.redirect_uri = CLIENT_CONFIG['web']['redirect_uris'][0]
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES, state=session.get('state'))
    flow.redirect_uri = CLIENT_CONFIG['web']['redirect_uris'][0]
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    session['credentials'] = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES
    }
    save_credentials(creds)  # persist to disk
    return redirect('/')

@app.route('/api/auth-status')
def auth_status():
    authenticated = 'credentials' in session or load_credentials_from_file() is not None
    return jsonify({'authenticated': authenticated})

@app.route('/api/confessions')
def get_confessions():
    service = get_gmail_service()
    if not service:
        return jsonify({'error': 'Not authenticated', 'authenticated': False}), 401
    
    sort = request.args.get('sort', 'newest')
    
    try:
        # Get unread emails from inbox, newest first
        result = service.users().messages().list(
            userId='me',
            labelIds=['INBOX', 'UNREAD'],
            maxResults=50,
            q='to:info@confessionsza.com OR in:inbox is:unread'
        ).execute()
        
        messages = result.get('messages', [])
        confessions = []
        
        for msg_ref in messages[:50]:
            msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']).execute()
            
            headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
            date_str = headers.get('Date', '')
            
            # Parse date
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(date_str)
                date_formatted = dt.strftime('%d %b %Y, %H:%M')
                date_iso = dt.isoformat()
                date_ts = dt.timestamp()
            except:
                date_formatted = date_str[:20] if date_str else 'Unknown date'
                date_iso = ''
                date_ts = 0
            
            parsed = parse_email_body(service, msg_ref['id'])
            
            confession_text = parsed.get('confession', '').strip()
            if not confession_text:
                continue
            
            holiday_emoji = detect_holiday(confession_text)
            
            confessions.append({
                'id': msg_ref['id'],
                'confession': confession_text,
                'location': parsed.get('location', '').strip(),
                'date': date_formatted,
                'date_iso': date_iso,
                'date_ts': date_ts,
                'holiday_emoji': holiday_emoji,
                'subject': headers.get('Subject', '(No subject)')
            })
        
        # Sort
        if sort == 'oldest':
            confessions.sort(key=lambda x: x['date_ts'])
        else:
            confessions.sort(key=lambda x: x['date_ts'], reverse=True)
        
        return jsonify({'confessions': confessions, 'authenticated': True})
    
    except Exception as e:
        return jsonify({'error': str(e), 'authenticated': True}), 500

@app.route('/api/state')
def get_state():
    state = load_state()
    return jsonify(state)

@app.route('/api/state', methods=['POST'])
def update_state():
    data = request.json
    state = load_state()
    if 'public_number' in data:
        state['public_number'] = int(data['public_number'])
    if 'subscriber_number' in data:
        state['subscriber_number'] = int(data['subscriber_number'])
    if 'color_index' in data:
        state['color_index'] = int(data['color_index']) % len(COLORS)
    if 'sub_color_index' in data:
        state['sub_color_index'] = int(data['sub_color_index']) % len(COLORS)
    save_state(state)
    return jsonify(state)

@app.route('/api/accept', methods=['POST'])
def accept_confession():
    """Mark a confession as read (accepted/posted) - removes from unread queue"""
    service = get_gmail_service()
    if not service:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    msg_id = data.get('id')
    post_type = data.get('type', 'public')  # 'public' or 'subscriber'
    
    state = load_state()
    
    if post_type == 'subscriber':
        number = state['subscriber_number']
        state['subscriber_number'] += 1
        state['sub_color_index'] = (state['sub_color_index'] + 1) % len(COLORS)
    else:
        number = state['public_number']
        state['public_number'] += 1
        state['color_index'] = (state['color_index'] + 1) % len(COLORS)
    
    save_state(state)
    
    # Mark as read AND archive (remove from inbox)
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD', 'INBOX']}
        ).execute()
    except Exception as e:
        print(f"Error archiving: {e}")
    
    return jsonify({'success': True, 'number': number, 'state': state})

@app.route('/api/reject', methods=['POST'])
def reject_confession():
    """Archive a confession"""
    service = get_gmail_service()
    if not service:
        return jsonify({'error': 'Not authenticated'}), 401
    
    data = request.json
    msg_id = data.get('id')
    
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['INBOX', 'UNREAD']}
        ).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/colors')
def get_colors():
    return jsonify({'colors': COLORS})

# Temporary in-memory image store for iOS save
import time
temp_images = {}

@app.route('/api/temp-image', methods=['POST'])
def store_temp_image():
    data = request.json
    image_b64 = data.get('image')
    if not image_b64:
        return jsonify({'error': 'No image'}), 400
    # Generate a unique key
    key = str(int(time.time() * 1000))
    temp_images[key] = image_b64
    # Clean up old images (keep only last 10)
    if len(temp_images) > 10:
        oldest = sorted(temp_images.keys())[0]
        del temp_images[oldest]
    return jsonify({'url': '/api/temp-image/' + key})

@app.route('/api/temp-image/<key>')
def serve_temp_image(key):
    image_b64 = temp_images.get(key)
    if not image_b64:
        return 'Image not found', 404
    image_data = base64.b64decode(image_b64)
    from flask import Response
    return Response(
        image_data,
        mimetype='image/png',
        headers={
            'Content-Disposition': 'inline; filename="confession.png"',
            'Content-Type': 'image/png',
            'Cache-Control': 'no-store'
        }
    )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
