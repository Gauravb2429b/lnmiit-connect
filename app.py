from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3, hashlib, random, string, smtplib, pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__, static_folder='.')
app.secret_key = 'lnmiit_connect_secret_2024'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
CORS(app, supports_credentials=True)

DB = 'lnmiit.db'
IST = pytz.timezone('Asia/Kolkata')

ADMIN_EMAIL     = 'lnmiit.connects@gmail.com'
ADMIN_PASS_HASH = hashlib.sha256('gsr@ts@ak@ug'.encode()).hexdigest()

def get_ist_now():
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

def calc_year(email):
    """Auto calculate college year from email roll number"""
    try:
        roll = email.split('@')[0]
        joining_year = 2000 + int(roll[:2])
        now = datetime.now(IST)
        # Academic year starts July 8
        if now.month < 7 or (now.month == 7 and now.day < 8):
            academic_year = now.year - 1
        else:
            academic_year = now.year
        year = academic_year - joining_year + 1
        return max(1, min(4, year))  # clamp between 1-4
    except:
        return 1

# ── EMAIL CONFIG ──────────────────────────────────────────
GMAIL_USER = 'lnmiit.connects@gmail.com'
GMAIL_PASS = 'sralmyptlesotika'  # app password without spaces

def send_otp_email(to_email, otp):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'{otp} is your LNMIIT Connect verification code'
    msg['From']    = f'LNMIIT Connect <{GMAIL_USER}>'
    msg['To']      = to_email

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#0d0d14;border-radius:16px;">
      <div style="font-size:22px;font-weight:700;color:#a5b4fc;margin-bottom:8px;">🔗 LNMIIT Connect</div>
      <div style="font-size:15px;color:#eeeef5;margin-bottom:24px;">Your verification code is:</div>
      <div style="font-size:42px;font-weight:800;letter-spacing:10px;color:#6366f1;background:#1a1a2e;padding:20px;border-radius:12px;text-align:center;">{otp}</div>
      <div style="font-size:13px;color:#8888a8;margin-top:20px;">This code expires in <b>10 minutes</b>. Do not share it with anyone.</div>
      <div style="font-size:12px;color:#44445a;margin-top:16px;">If you didn't request this, ignore this email.</div>
    </div>
    """
    msg.attach(MIMEText(html, 'html'))
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_PASS)
            smtp.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f'Email error: {e}')
        return False

# in-memory OTP store: { email: { otp, expires_at, data } }
otp_store = {}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def is_admin():
    return session.get('role') == 'admin'

def is_coordinator_of(club_id):
    uid = session.get('user_id')
    if not uid: return False
    conn = get_db()
    row = conn.execute('SELECT 1 FROM club_coordinators WHERE club_id=? AND user_id=?', (club_id, uid)).fetchone()
    conn.close()
    return row is not None

# ── INIT DB ───────────────────────────────────────────────
def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            anon_username TEXT    UNIQUE,
            email         TEXT    UNIQUE NOT NULL,
            password      TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'student',
            year          INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS clubs (
            id       INTEGER PRIMARY KEY,
            name     TEXT    NOT NULL,
            category TEXT    NOT NULL,
            emoji    TEXT    NOT NULL,
            desc     TEXT,
            members  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS club_coordinators (
            club_id  INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            PRIMARY KEY (club_id, user_id),
            FOREIGN KEY (club_id) REFERENCES clubs(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS join_requests (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            club_id    INTEGER NOT NULL,
            status     TEXT    NOT NULL DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (student_id, club_id),
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (club_id)    REFERENCES clubs(id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            message    TEXT    NOT NULL,
            is_read    INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wz_messages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            anon_username  TEXT    NOT NULL,
            message        TEXT    NOT NULL,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at     DATETIME DEFAULT (datetime('now', '+12 hours')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wz_threads (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            anon_username  TEXT    NOT NULL,
            title          TEXT    NOT NULL,
            body           TEXT,
            votes          INTEGER DEFAULT 0,
            reply_count    INTEGER DEFAULT 0,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at     DATETIME DEFAULT (datetime('now', '+12 hours')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wz_replies (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id      INTEGER NOT NULL,
            user_id        INTEGER NOT NULL,
            anon_username  TEXT    NOT NULL,
            message        TEXT    NOT NULL,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (thread_id) REFERENCES wz_threads(id),
            FOREIGN KEY (user_id)   REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS wz_votes (
            thread_id INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            PRIMARY KEY (thread_id, user_id)
        );
        CREATE TABLE IF NOT EXISTS wz_polls (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id  INTEGER NOT NULL UNIQUE,
            question   TEXT NOT NULL,
            FOREIGN KEY (thread_id) REFERENCES wz_threads(id)
        );
        CREATE TABLE IF NOT EXISTS wz_poll_options (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id  INTEGER NOT NULL,
            option   TEXT NOT NULL,
            votes    INTEGER DEFAULT 0,
            FOREIGN KEY (poll_id) REFERENCES wz_polls(id)
        );
        CREATE TABLE IF NOT EXISTS wz_poll_votes (
            poll_id   INTEGER NOT NULL,
            option_id INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            PRIMARY KEY (poll_id, user_id)
        );
    ''')
    clubs = [
        (1,  'Astronomy Club',     'Science & Tech', '🔭', 'Stargazing sessions, telescope workshops, and space science events at LNMIIT.',             0),
        (2,  'Cipher',             'Science & Tech', '🔐', 'Cryptography, cybersecurity challenges, and CTF competitions.',                             0),
        (3,  'Cybros',             'Science & Tech', '💻', 'The official coding club — competitive programming, hackathons, and open source projects.', 0),
        (4,  'DebSoc',             'Science & Tech', '🎤', 'Debate society — MUNs, parliamentary debates, and public speaking workshops.',              0),
        (5,  'E Cell',             'Science & Tech', '💡', 'Entrepreneurship cell — startup ideas, investor talks, and business competitions.',         0),
        (6,  'Phoenix',            'Science & Tech', '🚀', 'Aerospace and rocketry club — model rockets, drone racing, and aerospace events.',          0),
        (7,  'Quizzinga',          'Science & Tech', '🧠', 'Quiz club — inter-college quizzes and general knowledge events.',                           0),
        (8,  'Finlogue',           'Science & Tech', '📈', 'Finance and economics club — stock market simulations and fintech talks.',                  0),
        (9,  'Aaveg',              'Cultural',       '🎪', 'The annual cultural fest committee — organizing LNMIIT\'s biggest cultural celebration.',   0),
        (10, 'Capriccio',          'Cultural',       '🎵', 'Music club — jam sessions, open mics, and college festival performances.',                  0),
        (11, 'Eminence',           'Cultural',       '✨', 'Fashion and lifestyle club — styling events, ramp walks, and personality development.',     0),
        (12, 'Fundoo',             'Cultural',       '🎭', 'Drama and theatre club — stage performances and annual productions.',                       0),
        (13, 'Imagination',        'Cultural',       '🎨', 'Fine arts club — painting, sketching, digital art, and campus art exhibitions.',            0),
        (14, 'Insignia',           'Cultural',       '📷', 'Photography and videography club — capture campus life.',                                   0),
        (15, 'Literary Committee', 'Cultural',       '📚', 'Creative writing, poetry slams, book clubs, and the annual college magazine.',              0),
        (16, 'Media Cell',         'Cultural',       '📰', 'Campus media — newsletters, social media, PR, and college news coverage.',                 0),
        (17, 'Rendition',          'Cultural',       '💃', 'Dance club — classical, folk, and western dance forms.',                                    0),
        (18, 'Sankalp',            'Cultural',       '🌸', 'Social initiative club — community service, fundraising, and outreach programs.',           0),
        (19, 'Vignette',           'Cultural',       '🎬', 'Film and cinematography club — screenings, short films, and filmmaking workshops.',         0),
        (20, 'Cricket',            'Sports',         '🏏', 'Campus cricket league and inter-college tournaments every semester.',                       0),
        (21, 'Badminton',          'Sports',         '🏸', 'Court bookings, training sessions, and state-level tournament participation.',              0),
        (22, 'Chess',              'Sports',         '♟️', 'Chess tournaments, coaching sessions, and inter-college competitions.',                     0),
        (23, 'Basketball',         'Sports',         '🏀', 'Basketball practice, inter-college tournaments, and campus league matches.',                0),
        (24, 'Football',           'Sports',         '⚽', 'Inter-college tournaments and practice sessions every evening at the ground.',              0),
        (25, 'Kabaddi',            'Sports',         '🤼', 'Kabaddi training and inter-college competitions representing LNMIIT.',                      0),
        (26, 'Lawn Tennis',        'Sports',         '🎾', 'Tennis coaching, court sessions, and inter-college tennis tournaments.',                    0),
        (27, 'Squash',             'Sports',         '🎱', 'Squash training and competitive matches at the LNMIIT squash courts.',                      0),
        (28, 'Table Tennis',       'Sports',         '🏓', 'TT tournaments, practice sessions, and inter-college table tennis events.',                 0),
        (29, 'Volleyball',         'Sports',         '🏐', 'Volleyball practice and inter-college tournaments on campus.',                              0),
        (30, 'Zenith',             'Sports',         '🏅', 'Annual sports fest committee — organizing LNMIIT\'s inter-college sports events.',          0),
        (31, 'COSHA Committee',    'Societies',      '🏛️', 'Council of Student Hostel Affairs — managing hostel life and student welfare.',             0),
        (32, 'C Cell',             'Societies',      '🔬', 'Cultural cell — coordinating cultural activities and inter-college events.',                0),
        (33, 'Alumni Association', 'Societies',      '🤝', 'Connecting students with LNMIIT alumni for mentorship, networking, and career guidance.',   0),
        (34, 'TPCR',               'Societies',      '💼', 'Training, Placement & Corporate Relations — internships, placements, and career prep.',     0),
    ]
    c.executemany('INSERT OR IGNORE INTO clubs VALUES (?,?,?,?,?,?)', clubs)
    conn.commit()
    conn.close()

# ── ADMIN ROUTES ──────────────────────────────────────────
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    d = request.json
    if (d.get('email') == ADMIN_EMAIL and
            hashlib.sha256(d.get('password','').encode()).hexdigest() == ADMIN_PASS_HASH):
        session.permanent = True
        session['role'] = 'admin'
        return jsonify({'message': 'Welcome, Admin!', 'role': 'admin'})
    return jsonify({'error': 'Wrong email or password'}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/admin/students', methods=['GET'])
def admin_students():
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    q = request.args.get('q', '').strip()
    conn = get_db()
    if q:
        rows = conn.execute(
            "SELECT DISTINCT id,name,email,role FROM users WHERE name LIKE ? OR email LIKE ? ORDER BY name",
            (f'%{q}%', f'%{q}%')
        ).fetchall()
    else:
        rows = conn.execute("SELECT DISTINCT id,name,email,role FROM users ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/clubs', methods=['GET'])
def admin_clubs():
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    rows = conn.execute('SELECT id,name,category,emoji FROM clubs ORDER BY category,name').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── PUBLIC STUDENT SEARCH (for dashboard) ────────────────
@app.route('/api/students/search', methods=['GET'])
def search_students():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, email FROM users WHERE (name LIKE ? OR email LIKE ?) AND id != ? ORDER BY name LIMIT 20",
        (f'%{q}%', f'%{q}%', uid)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/coordinators', methods=['GET'])
def admin_coordinators():
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    rows = conn.execute('''
        SELECT cc.club_id, c.name as club_name, c.emoji,
               u.id as user_id, u.name as user_name, u.email
        FROM club_coordinators cc
        JOIN clubs c ON c.id = cc.club_id
        JOIN users u ON u.id = cc.user_id
        ORDER BY c.name
    ''').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/admin/assign-coordinator', methods=['POST'])
def admin_assign():
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    d = request.json
    user_id, club_id = d.get('user_id'), d.get('club_id')
    if not user_id or not club_id: return jsonify({'error': 'Missing fields'}), 400
    conn = get_db()
    conn.execute('UPDATE users SET role="coordinator" WHERE id=?', (user_id,))
    conn.execute('INSERT OR IGNORE INTO club_coordinators VALUES (?,?)', (club_id, user_id))
    # auto add coordinator as approved member
    try:
        conn.execute(
            'INSERT OR IGNORE INTO join_requests (student_id, club_id, status) VALUES (?,?,?)',
            (user_id, club_id, 'approved')
        )
    except: pass
    conn.commit()
    conn.close()
    return jsonify({'message': 'Coordinator assigned!'})

@app.route('/api/admin/remove-coordinator', methods=['POST'])
def admin_remove_coord():
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    d = request.json
    user_id, club_id = d.get('user_id'), d.get('club_id')
    conn = get_db()
    conn.execute('DELETE FROM club_coordinators WHERE club_id=? AND user_id=?', (club_id, user_id))
    # also remove their auto membership
    conn.execute('DELETE FROM join_requests WHERE club_id=? AND student_id=?', (club_id, user_id))
    remaining = conn.execute('SELECT COUNT(*) as cnt FROM club_coordinators WHERE user_id=?', (user_id,)).fetchone()['cnt']
    if remaining == 0:
        conn.execute('UPDATE users SET role="student" WHERE id=?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Coordinator removed'})

# ── AUTH ──────────────────────────────────────────────────
# ── SEND OTP ──────────────────────────────────────────────
@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    d = request.json
    email = d.get('email', '').strip()
    if not email.endswith('@lnmiit.ac.in'):
        return jsonify({'error': 'Only @lnmiit.ac.in emails allowed'}), 400

    # check email not already registered
    conn = get_db()
    existing = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
    conn.close()
    if existing:
        return jsonify({'error': 'Email already registered. Please sign in.'}), 409

    # generate 6-digit OTP
    otp = ''.join(random.choices(string.digits, k=6))
    otp_store[email] = {
        'otp': otp,
        'expires_at': datetime.now() + timedelta(minutes=10),
        'data': d  # store all signup data temporarily
    }

    success = send_otp_email(email, otp)
    if success:
        return jsonify({'message': 'OTP sent to your email!'})
    else:
        return jsonify({'error': 'Failed to send email. Try again.'}), 500

# ── VERIFY OTP & REGISTER ─────────────────────────────────
@app.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    d = request.json
    email = d.get('email', '').strip()
    otp   = d.get('otp', '').strip()

    if email not in otp_store:
        return jsonify({'error': 'No OTP found. Please request a new one.'}), 400

    stored = otp_store[email]
    if datetime.now() > stored['expires_at']:
        del otp_store[email]
        return jsonify({'error': 'OTP expired. Please request a new one.'}), 400

    if stored['otp'] != otp:
        return jsonify({'error': 'Wrong OTP. Please try again.'}), 400

    # OTP correct — register user
    data = stored['data']
    del otp_store[email]
    auto_year = calc_year(email)
    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (name, anon_username, email, password, role, year) VALUES (?,?,?,?,?,?)',
            (data['name'], data['anon_username'], email, hash_pw(data['password']), 'student', auto_year)
        )
        conn.commit()
        return jsonify({'message': 'Account created successfully!'})
    except sqlite3.IntegrityError as e:
        if 'anon_username' in str(e):
            return jsonify({'error': 'Anonymous username already taken!'}), 409
        return jsonify({'error': 'Email already registered'}), 409
    finally:
        conn.close()

# ── REGISTER (now handled by OTP flow above) ──────────────
@app.route('/api/register', methods=['POST'])
def register():
    d = request.json
    if not d or not all(k in d for k in ['name','email','password','anon_username']):
        return jsonify({'error': 'Missing fields'}), 400

    name = d['name'].strip()
    anon = d['anon_username'].strip()

    import re
    words = name.split()
    if len(words) < 2:
        return jsonify({'error': 'Please enter your full name (first and last name)'}), 400
    if re.search(r'\d', name):
        return jsonify({'error': 'Name should not contain numbers'}), 400
    if len(name) < 4:
        return jsonify({'error': 'Please enter a valid full name'}), 400

    conn = get_db()
    try:
        conn.execute(
            'INSERT INTO users (name, anon_username, email, password, role) VALUES (?,?,?,?,?)',
            (name, anon, d['email'], hash_pw(d['password']), 'student')
        )
        conn.commit()
        return jsonify({'message': 'Registered successfully'})
    except sqlite3.IntegrityError as e:
        if 'anon_username' in str(e):
            return jsonify({'error': 'Anonymous username already taken!'}), 409
        return jsonify({'error': 'Email already registered'}), 409
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    d = request.json
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE email=? AND password=?',
                        (d['email'], hash_pw(d['password']))).fetchone()
    conn.close()
    if not user: return jsonify({'error': 'Invalid credentials'}), 401
    session.permanent = True
    session['user_id'] = user['id']
    session['role']    = user['role']
    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'anon_username': user['anon_username'] or user['name'],
        'email': user['email'],
        'role': user['role'],
        'year': user['year'] or 1
    })

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out'})

@app.route('/api/me', methods=['GET'])
def me():
    if session.get('role') == 'admin':
        return jsonify({'id': 0, 'name': 'Admin', 'email': ADMIN_EMAIL, 'role': 'admin', 'anon_username': 'Admin🛡️', 'year': 0})
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    user = conn.execute('SELECT id,name,anon_username,email,role,year FROM users WHERE id=?', (uid,)).fetchone()
    conn.close()
    if not user: return jsonify({'error': 'User not found'}), 404
    return jsonify(dict(user))

# ── PUBLIC PROFILE ────────────────────────────────────────
@app.route('/api/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    user = conn.execute(
        'SELECT id,name,anon_username,year FROM users WHERE id=?', (user_id,)
    ).fetchone()
    if not user:
        conn.close()
        return jsonify({'error': 'User not found'}), 404

    # get their joined clubs
    clubs = conn.execute('''
        SELECT c.id, c.name, c.emoji, c.category
        FROM join_requests jr
        JOIN clubs c ON c.id = jr.club_id
        WHERE jr.student_id = ? AND jr.status = 'approved'
    ''', (user_id,)).fetchall()

    # get MY joined clubs for mutual detection
    my_clubs = conn.execute('''
        SELECT club_id FROM join_requests
        WHERE student_id = ? AND status = 'approved'
    ''', (uid,)).fetchall()
    my_club_ids = {r['club_id'] for r in my_clubs}

    conn.close()

    club_list = []
    for c in clubs:
        club_list.append({
            'id': c['id'],
            'name': c['name'],
            'emoji': c['emoji'],
            'category': c['category'],
            'mutual': c['id'] in my_club_ids
        })

    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'anon_username': user['anon_username'],
        'year': user['year'] or 1,
        'clubs': club_list
    })

# ── CLUBS ─────────────────────────────────────────────────
@app.route('/api/clubs', methods=['GET'])
def get_clubs():
    uid = session.get('user_id')
    conn = get_db()
    clubs = conn.execute('SELECT * FROM clubs ORDER BY category, name').fetchall()
    result = []
    for club in clubs:
        c = dict(club)
        # real member count from approved requests
        count = conn.execute(
            'SELECT COUNT(*) as cnt FROM join_requests WHERE club_id=? AND status="approved"',
            (club['id'],)
        ).fetchone()['cnt']
        c['members'] = count
        if uid:
            req = conn.execute('SELECT status FROM join_requests WHERE student_id=? AND club_id=?',
                               (uid, club['id'])).fetchone()
            c['request_status'] = req['status'] if req else None
        else:
            c['request_status'] = None
        result.append(c)
    conn.close()
    return jsonify(result)

# ── JOIN REQUESTS ─────────────────────────────────────────
@app.route('/api/clubs/<int:club_id>/request', methods=['POST'])
def request_join(club_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    try:
        conn.execute('INSERT INTO join_requests (student_id, club_id, status) VALUES (?,?,?)',
                     (uid, club_id, 'pending'))
        # get student name and club name
        student = conn.execute('SELECT name FROM users WHERE id=?', (uid,)).fetchone()
        club    = conn.execute('SELECT name FROM clubs WHERE id=?', (club_id,)).fetchone()
        # notify all coordinators of this club
        coords = conn.execute('SELECT user_id FROM club_coordinators WHERE club_id=?', (club_id,)).fetchall()
        for coord in coords:
            conn.execute(
                'INSERT INTO notifications (user_id, message) VALUES (?,?)',
                (coord['user_id'], f"{student['name']} has requested to join {club['name']}")
            )
        conn.commit()
        return jsonify({'message': 'Join request sent!'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Request already exists'}), 409
    finally:
        conn.close()

@app.route('/api/clubs/<int:club_id>/request', methods=['DELETE'])
def cancel_request(club_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    conn.execute('DELETE FROM join_requests WHERE student_id=? AND club_id=? AND status="pending"',
                 (uid, club_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Request cancelled'})

# ── COORDINATOR ───────────────────────────────────────────
@app.route('/api/coordinator/clubs', methods=['GET'])
def coordinator_clubs():
    uid = session.get('user_id')
    if not uid or session.get('role') != 'coordinator':
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    clubs = conn.execute('''
        SELECT c.* FROM clubs c
        JOIN club_coordinators cc ON cc.club_id = c.id
        WHERE cc.user_id = ?
    ''', (uid,)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in clubs])

@app.route('/api/coordinator/clubs/<int:club_id>/requests', methods=['GET'])
def get_requests(club_id):
    if not is_coordinator_of(club_id): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    rows = conn.execute('''
        SELECT jr.id, jr.status, jr.created_at, u.id as user_id, u.name, u.email
        FROM join_requests jr JOIN users u ON u.id = jr.student_id
        WHERE jr.club_id = ? AND jr.status = 'pending' ORDER BY jr.created_at
    ''', (club_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/coordinator/clubs/<int:club_id>/members', methods=['GET'])
def get_members(club_id):
    if not is_coordinator_of(club_id): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    rows = conn.execute('''
        SELECT jr.id as request_id, u.id as user_id, u.name, u.email, jr.updated_at
        FROM join_requests jr JOIN users u ON u.id = jr.student_id
        WHERE jr.club_id = ? AND jr.status = 'approved' ORDER BY jr.updated_at DESC
    ''', (club_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/coordinator/requests/<int:req_id>/approve', methods=['POST'])
def approve_request(req_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    req = conn.execute('SELECT * FROM join_requests WHERE id=?', (req_id,)).fetchone()
    if not req or not is_coordinator_of(req['club_id']):
        conn.close(); return jsonify({'error': 'Unauthorized'}), 403
    conn.execute('UPDATE join_requests SET status="approved", updated_at=CURRENT_TIMESTAMP WHERE id=?', (req_id,))
    conn.execute('UPDATE clubs SET members = members + 1 WHERE id=?', (req['club_id'],))
    # notify student
    club = conn.execute('SELECT name FROM clubs WHERE id=?', (req['club_id'],)).fetchone()
    conn.execute('INSERT INTO notifications (user_id, message) VALUES (?,?)',
                 (req['student_id'], f"🎉 Your request to join {club['name']} has been approved!"))
    conn.commit(); conn.close()
    return jsonify({'message': 'Approved!'})

@app.route('/api/coordinator/requests/<int:req_id>/reject', methods=['POST'])
def reject_request(req_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    req = conn.execute('SELECT * FROM join_requests WHERE id=?', (req_id,)).fetchone()
    if not req or not is_coordinator_of(req['club_id']):
        conn.close(); return jsonify({'error': 'Unauthorized'}), 403
    conn.execute('UPDATE join_requests SET status="rejected", updated_at=CURRENT_TIMESTAMP WHERE id=?', (req_id,))
    # notify student
    club = conn.execute('SELECT name FROM clubs WHERE id=?', (req['club_id'],)).fetchone()
    conn.execute('INSERT INTO notifications (user_id, message) VALUES (?,?)',
                 (req['student_id'], f"Your request to join {club['name']} was not approved this time."))
    conn.commit(); conn.close()
    return jsonify({'message': 'Rejected'})

# ── NOTIFICATIONS ─────────────────────────────────────────
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    rows = conn.execute(
        'SELECT id, message, is_read, created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20',
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/notifications/read', methods=['POST'])
def mark_notifications_read():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    conn.execute('UPDATE notifications SET is_read=1 WHERE user_id=?', (uid,))
    conn.commit(); conn.close()
    return jsonify({'message': 'Marked as read'})

@app.route('/api/notifications/unread-count', methods=['GET'])
def unread_count():
    uid = session.get('user_id')
    if not uid: return jsonify({'count': 0})
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) as cnt FROM notifications WHERE user_id=? AND is_read=0', (uid,)).fetchone()['cnt']
    conn.close()
    return jsonify({'count': count})

@app.route('/api/coordinator/clubs/<int:club_id>/members/<int:user_id>/remove', methods=['POST'])
def remove_member(club_id, user_id):
    if not is_coordinator_of(club_id): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute('DELETE FROM join_requests WHERE club_id=? AND student_id=?', (club_id, user_id))
    conn.execute('UPDATE clubs SET members = MAX(members - 1, 0) WHERE id=?', (club_id,))
    conn.commit(); conn.close()
    return jsonify({'message': 'Member removed'})

# ── WARZONE ───────────────────────────────────────────────
def cleanup_expired():
    conn = get_db()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute("DELETE FROM wz_replies WHERE thread_id IN (SELECT id FROM wz_threads WHERE expires_at <= ?)", (now,))
    conn.execute("DELETE FROM wz_votes WHERE thread_id IN (SELECT id FROM wz_threads WHERE expires_at <= ?)", (now,))
    conn.execute("DELETE FROM wz_threads WHERE expires_at <= ?", (now,))
    conn.execute("DELETE FROM wz_messages WHERE expires_at <= ?", (now,))
    conn.commit()
    conn.close()

@app.route('/api/warzone/stats')
def warzone_stats():
    uid = session.get('user_id')
    if not uid and not is_admin(): return jsonify({'error': 'Not logged in'}), 401
    cleanup_expired()
    conn = get_db()
    live_users     = conn.execute("SELECT COUNT(DISTINCT user_id) FROM wz_messages WHERE created_at >= datetime('now', '-15 minutes')").fetchone()[0]
    msgs_today     = conn.execute("SELECT COUNT(*) FROM wz_messages WHERE created_at >= datetime('now', '-24 hours')").fetchone()[0]
    active_threads = conn.execute("SELECT COUNT(*) FROM wz_threads WHERE expires_at > datetime('now')").fetchone()[0]
    replies_today  = conn.execute("SELECT COUNT(*) FROM wz_replies WHERE created_at >= datetime('now', '-24 hours')").fetchone()[0]
    conn.close()
    return jsonify({'live_users': live_users, 'msgs_today': msgs_today, 'active_threads': active_threads, 'replies_today': replies_today})

@app.route('/api/warzone/chat', methods=['GET'])
def get_chat():
    uid = session.get('user_id')
    if not uid and not is_admin(): return jsonify({'error': 'Not logged in'}), 401
    cleanup_expired()
    after = request.args.get('after', 0, type=int)
    conn  = get_db()
    rows  = conn.execute("""
        SELECT m.id, m.anon_username, m.message, m.created_at,
               COALESCE(u.year, 0) as year
        FROM wz_messages m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.id > ? AND m.expires_at > datetime('now')
        ORDER BY m.id ASC LIMIT 80
    """, (after,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/warzone/chat', methods=['POST'])
def post_chat():
    uid = session.get('user_id')
    if not uid and not is_admin(): return jsonify({'error': 'Not logged in'}), 401
    d   = request.json
    msg = (d.get('message') or '').strip()
    if not msg:        return jsonify({'error': 'Empty message'}), 400
    if len(msg) > 500: return jsonify({'error': 'Too long (max 500)'}), 400
    conn = get_db()
    if is_admin():
        # admin posts as Admin🛡️
        conn.execute("INSERT INTO wz_messages (user_id, anon_username, message) VALUES (?,?,?)", (0, 'Admin🛡️', msg))
        conn.commit(); conn.close()
        return jsonify({'message': 'Sent!'})
    user = conn.execute('SELECT anon_username FROM users WHERE id=?', (uid,)).fetchone()
    if not user: conn.close(); return jsonify({'error': 'User not found'}), 404
    recent = conn.execute("SELECT COUNT(*) FROM wz_messages WHERE user_id=? AND created_at >= datetime('now', '-10 seconds')", (uid,)).fetchone()[0]
    if recent >= 5: conn.close(); return jsonify({'error': 'Slow down!'}), 429
    conn.execute("INSERT INTO wz_messages (user_id, anon_username, message) VALUES (?,?,?)", (uid, user['anon_username'], msg))
    conn.commit(); conn.close()
    return jsonify({'message': 'Sent!'})

@app.route('/api/warzone/threads', methods=['GET'])
def get_threads():
    uid = session.get('user_id')
    if not uid and not is_admin(): return jsonify({'error': 'Not logged in'}), 401
    cleanup_expired()
    sort = request.args.get('sort', 'hot')
    order = {'hot': 'ORDER BY (t.votes * 2 + t.reply_count) DESC, t.created_at DESC', 'new': 'ORDER BY t.created_at DESC', 'top': 'ORDER BY t.votes DESC, t.created_at DESC'}.get(sort, 'ORDER BY t.created_at DESC')
    conn = get_db()
    rows = conn.execute(f"""
        SELECT t.id, t.anon_username, t.title, t.body, t.votes,
               t.reply_count, t.created_at, t.expires_at, u.year
        FROM wz_threads t
        JOIN users u ON u.id = t.user_id
        WHERE t.expires_at > datetime('now')
        {order} LIMIT 50
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/warzone/threads', methods=['POST'])
def post_thread():
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    d     = request.json
    title = (d.get('title') or '').strip()
    body  = (d.get('body')  or '').strip()
    poll  = d.get('poll')  # optional: { question: str, options: [str] }
    if not title:         return jsonify({'error': 'Title required'}), 400
    if len(title) > 150:  return jsonify({'error': 'Title too long'}), 400
    if len(body)  > 1000: return jsonify({'error': 'Body too long'}), 400
    conn = get_db()
    user = conn.execute('SELECT anon_username FROM users WHERE id=?', (uid,)).fetchone()
    if not user: conn.close(); return jsonify({'error': 'User not found'}), 404
    recent = conn.execute("SELECT COUNT(*) FROM wz_threads WHERE user_id=? AND created_at >= datetime('now', '-1 hour')", (uid,)).fetchone()[0]
    if recent >= 3: conn.close(); return jsonify({'error': 'Max 3 threads/hour'}), 429
    cursor = conn.execute("INSERT INTO wz_threads (user_id, anon_username, title, body) VALUES (?,?,?,?)",
                          (uid, user['anon_username'], title, body or None))
    thread_id = cursor.lastrowid
    # add poll if provided
    if poll and poll.get('question') and poll.get('options'):
        opts = [o.strip() for o in poll['options'] if o.strip()][:4]  # max 4 options
        if len(opts) >= 2:
            poll_cursor = conn.execute("INSERT INTO wz_polls (thread_id, question) VALUES (?,?)", (thread_id, poll['question']))
            poll_id = poll_cursor.lastrowid
            for opt in opts:
                conn.execute("INSERT INTO wz_poll_options (poll_id, option) VALUES (?,?)", (poll_id, opt))
    conn.commit(); conn.close()
    return jsonify({'message': 'Thread posted!'})

@app.route('/api/warzone/threads/<int:thread_id>/replies', methods=['GET'])
def get_replies(thread_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    rows = conn.execute("SELECT id, anon_username, message, created_at FROM wz_replies WHERE thread_id=? ORDER BY created_at ASC", (thread_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route('/api/warzone/threads/<int:thread_id>/replies', methods=['POST'])
def post_reply(thread_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    d   = request.json
    msg = (d.get('message') or '').strip()
    if not msg:        return jsonify({'error': 'Empty reply'}), 400
    if len(msg) > 500: return jsonify({'error': 'Too long (max 500)'}), 400
    conn = get_db()
    thread = conn.execute("SELECT id FROM wz_threads WHERE id=? AND expires_at > datetime('now')", (thread_id,)).fetchone()
    if not thread: conn.close(); return jsonify({'error': 'Thread expired'}), 404
    user = conn.execute('SELECT anon_username FROM users WHERE id=?', (uid,)).fetchone()
    conn.execute("INSERT INTO wz_replies (thread_id, user_id, anon_username, message) VALUES (?,?,?,?)", (thread_id, uid, user['anon_username'], msg))
    conn.execute("UPDATE wz_threads SET reply_count = reply_count + 1 WHERE id=?", (thread_id,))
    conn.commit(); conn.close()
    return jsonify({'message': 'Reply posted!'})

@app.route('/api/warzone/threads/<int:thread_id>/vote', methods=['POST'])
def vote_thread(thread_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    thread = conn.execute("SELECT id FROM wz_threads WHERE id=? AND expires_at > datetime('now')", (thread_id,)).fetchone()
    if not thread: conn.close(); return jsonify({'error': 'Thread not found'}), 404
    try:
        conn.execute("INSERT INTO wz_votes (thread_id, user_id) VALUES (?,?)", (thread_id, uid))
        conn.execute("UPDATE wz_threads SET votes = votes + 1 WHERE id=?", (thread_id,))
        conn.commit()
        new_votes = conn.execute("SELECT votes FROM wz_threads WHERE id=?", (thread_id,)).fetchone()[0]
        conn.close()
        return jsonify({'votes': new_votes})
    except Exception:
        conn.close()
        return jsonify({'error': 'Already voted'}), 409

# ── ADMIN DELETE THREAD ───────────────────────────────────
@app.route('/api/warzone/threads/<int:thread_id>/delete', methods=['POST'])
def delete_thread(thread_id):
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute('DELETE FROM wz_replies WHERE thread_id=?', (thread_id,))
    conn.execute('DELETE FROM wz_votes WHERE thread_id=?', (thread_id,))
    conn.execute('DELETE FROM wz_poll_votes WHERE poll_id IN (SELECT id FROM wz_polls WHERE thread_id=?)', (thread_id,))
    conn.execute('DELETE FROM wz_poll_options WHERE poll_id IN (SELECT id FROM wz_polls WHERE thread_id=?)', (thread_id,))
    conn.execute('DELETE FROM wz_polls WHERE thread_id=?', (thread_id,))
    conn.execute('DELETE FROM wz_threads WHERE id=?', (thread_id,))
    conn.commit(); conn.close()
    return jsonify({'message': 'Thread deleted'})

# ── ADMIN DELETE CHAT MESSAGE ─────────────────────────────
@app.route('/api/warzone/chat/<int:msg_id>/delete', methods=['POST'])
def delete_message(msg_id):
    if not is_admin(): return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    conn.execute('DELETE FROM wz_messages WHERE id=?', (msg_id,))
    conn.commit(); conn.close()
    return jsonify({'message': 'Message deleted'})

# ── POLLS ─────────────────────────────────────────────────
@app.route('/api/warzone/threads/<int:thread_id>/poll', methods=['GET'])
def get_poll(thread_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    conn = get_db()
    poll = conn.execute('SELECT * FROM wz_polls WHERE thread_id=?', (thread_id,)).fetchone()
    if not poll: conn.close(); return jsonify(None)
    options = conn.execute('SELECT * FROM wz_poll_options WHERE poll_id=?', (poll['id'],)).fetchall()
    voted = conn.execute('SELECT option_id FROM wz_poll_votes WHERE poll_id=? AND user_id=?', (poll['id'], uid)).fetchone()
    conn.close()
    return jsonify({
        'id': poll['id'],
        'question': poll['question'],
        'options': [dict(o) for o in options],
        'voted_option': voted['option_id'] if voted else None
    })

@app.route('/api/warzone/threads/<int:thread_id>/poll/vote', methods=['POST'])
def vote_poll(thread_id):
    uid = session.get('user_id')
    if not uid: return jsonify({'error': 'Not logged in'}), 401
    d = request.json
    option_id = d.get('option_id')
    conn = get_db()
    poll = conn.execute('SELECT * FROM wz_polls WHERE thread_id=?', (thread_id,)).fetchone()
    if not poll: conn.close(); return jsonify({'error': 'No poll found'}), 404
    try:
        conn.execute('INSERT INTO wz_poll_votes (poll_id, option_id, user_id) VALUES (?,?,?)', (poll['id'], option_id, uid))
        conn.execute('UPDATE wz_poll_options SET votes = votes + 1 WHERE id=?', (option_id,))
        conn.commit()
        options = conn.execute('SELECT * FROM wz_poll_options WHERE poll_id=?', (poll['id'],)).fetchall()
        conn.close()
        return jsonify({'options': [dict(o) for o in options]})
    except:
        conn.close()
        return jsonify({'error': 'Already voted'}), 409

# ── STATIC ────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('page1', 'index.html')

@app.route('/page1/<path:filename>')
def serve_page1(filename):
    return send_from_directory('page1', filename)

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

if __name__ == '__main__':
    init_db()
    print("\n LNMIIT Connect is running!")
    print(" App:         http://127.0.0.1:5000/dashboard.html")
    print(" Admin panel: http://127.0.0.1:5000/admin.html\n")
    app.run(debug=True, port=5000, host='0.0.0.0')