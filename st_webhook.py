#!/usr/bin/env python

#eventlet WSGI server
import eventlet
eventlet.monkey_patch()

#Flask Libs
from flask import Flask, abort, request, jsonify, render_template, send_from_directory, session, redirect, url_for, flash

#Flask Login Libs
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.urls import url_parse
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_required, current_user, login_user, logout_user

#Web Sockets
from flask_socketio import SocketIO, send, emit, join_room, leave_room, disconnect, rooms

#HTTP Libs
import requests

#JSON Libs
import json

#datetime
from datetime import datetime, timedelta

#My Libs
from smartthings import SmartThings
from my_secrets.secrets import SECRET_KEY, ST_WEBHOOK, CORS_ALLOWED_ORIGINS


# Replace the second item with your local IP address info
LOCAL_NETWORK_IP = ['127.0.0.1', '192.168.2.']

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins=CORS_ALLOWED_ORIGINS)
app.config['SECRET_KEY'] = SECRET_KEY

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db' # Defines our flask-login user database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Mute flask-sqlalchemy warning message
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) # Flask session expiration
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30) # Remember Me cookie expiration (Not sure this works???)
app.config['REMEMBER_COOKIE_SECURE'] = None # Change to True if you want to force using HTTPS to store cookies.
app.config['REMEMBER_COOKIE_HTTPONLY'] = True # Prevents cookies from being accessed on the client-side.

db = SQLAlchemy(app) # This gives us our database/datamodel object

login_manager = LoginManager(app) # This creates our login manager object
login_manager.login_view = 'login' # Defines our login view (basically calls url_for('login'))

class User(UserMixin, db.Model): # This is our User class/model.  It will store our valid users.
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True) # primary keys are required by SQLAlchemy
    active = db.Column(db.Boolean) # This value must be True (1) before the user can login.
    email = db.Column(db.String(100), unique=True) # This is our username.  Must be unique.
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    role = db.Column(db.String(25))
    # db.relationship defines the one-to-many relationship with the UserLogin class/table and can be accessible here (but we won't use it that way)
    #   backref tells sqlalchemy that we can also go from UserLogin to User
    #   lazy='dynamic' tells sqlalchemy not to automatically load the related data into the logins attribute.  It could get large.
    logins = db.relationship('UserLogin', backref='users', lazy='dynamic')

class UserLogin(db.Model): # This is our UserLogin class/model.  It will store login related data for our users
    __tablename__ = 'user_login'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    event = db.Column(db.String(50))
    date = db.Column(db.String(100))
    ip = db.Column(db.String(50))

class FailedLogin(db.Model): # This is our FailedLogin class/model.  It will store failed login attempts.
    __tablename__ = 'failed_login'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100))
    password = db.Column(db.String(100))
    date = db.Column(db.String(100))
    ip = db.Column(db.String(50))

class UserLogging(db.Model): # This is our UserLogging class/model.  It will allow us to turn logging on/off by login-type.
    __tablename__ = 'user_logging'
    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(50), unique=True)
    log_event = db.Column(db.Boolean, server_default='True')

db.create_all() # Creates our database and tables as defined in the above classes.

if not UserLogging.query.filter(UserLogging.event == 'login').first():
    log = UserLogging(event = 'login', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'logout').first():
    log = UserLogging(event = 'logout', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'connect').first():
    log = UserLogging(event = 'connect', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'disconnect').first():
    log = UserLogging(event = 'disconnect', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'config-view').first():
    log = UserLogging(event = 'config-view', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'config-update').first():
    log = UserLogging(event = 'config-update', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'presence-update').first():
    log = UserLogging(event = 'presence-update', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'scene-update').first():
    log = UserLogging(event = 'scene-update', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'user-update').first():
    log = UserLogging(event = 'user-update', log_event = True)
    db.session.add(log)
    db.session.commit()
if not UserLogging.query.filter(UserLogging.event == 'log-delete').first():
    log = UserLogging(event = 'log-delete', log_event = True)
    db.session.add(log)
    db.session.commit()

# Create first user if it doesn't already exist.  Notice it doesn't have to be a valid email.  It basically serves as our username.
if not User.query.filter(User.email == 'jeff@example.com').first():
    user = User(
        active=True,
        email='jeff@example.com',
        password=generate_password_hash('Password', method='sha256'), # We don't store the actual password, just the hash.
        name='Jeff',
        role='Admin'
    )
    db.session.add(user)
    db.session.commit()


@login_manager.user_loader # This is the login manager user loader.  Used to load current_user.
def load_user(user_id):
    # since the user_id is the primary key of our user table, use it in the query for the user
    user = User.query.get(int(user_id))
    if user and user.active and len(user.password) > 0: # Only return the user if they are active
        return user
    return None


@socketio.on('connect')
def socket_connect():
    session['room'] = 'testing'
    print(session)
    # Make sure the current_user is still authenticated.
    if current_user.is_authenticated:
        data = json.dumps({'status': 'connected'})
        emit('conn', data, broadcast=False)
        location_data = json.dumps(st.location)
        room = st.location_id
        print('Joining room: %s' % room)
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        print('ip: %s' % ip)
        if UserLogging.query.filter(UserLogging.event == 'connect').filter(UserLogging.log_event == True).first():
            current_user.logins.append(UserLogin(event='connect', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
            db.session.commit()
        join_room(room)
        emit('location_data', location_data, broadcast=False) #We only need to send this to the user currently connecting, not all.
    else:
        print('Current user no longer authenticated!')
        emit('location_data', '', broadcast=False)  # Send an empty event to notify browser user is no longer authorized

@socketio.on('disconnect')
def socket_disconnect():
    if current_user.is_authenticated:
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        if UserLogging.query.filter(UserLogging.event == 'disconnect').filter(UserLogging.log_event == True).first():
            current_user.logins.append(UserLogin(event='disconnect', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
            db.session.commit()

@socketio.on('pingBack')
def socket_pingback():
    if current_user.is_authenticated:
        emit('pingRcv');
    else:
        print('Current user no longer authenticated!')
        emit('location_data', '', broadcast=False)  # Send an empty event to notify browser user is no longer authorized

@socketio.on('disconn')
def socket_disconn():
    print('Disconnecting unauthorized user! [user: %s]' % User.query.get(int(session['_user_id'])).email)
    try: # Wrapped in a try in case the current_user is no longer active.
        user = User.query.get(int(session['_user_id']))
        if user: # Record the web socket disconnect.  Remove if desired.
            if request.headers.getlist('X-Forwarded-For'):
                ip = request.headers.getlist('X-Forwarded-For')[0]
            else:
                ip = request.remote_addr
            if UserLogging.query.filter(UserLogging.event == 'disconnect').filter(UserLogging.log_event == True).first():
                user.logins.append(UserLogin(event='disconnect', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
                db.session.commit()
    except:
        pass
    disconnect()

@socketio.on('refresh')
def socket_refresh():
    print(session)
    # Make sure the current_user is still authenticated.
    if current_user.is_authenticated:
        if st:
            st.readData(refresh=False)
            location_data = json.dumps(st.location)
            emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.
        else:
            print('st object not defined!')
    else:
        print('Current user no longer authenticated! [user_id: %s]' % session['_user_id'])
        emit('location_data', '', broadcast=False)  # Send an empty event to notify browser user is no longer authorized

@socketio.on('update-device')
def socket_update_device(msg):
    # Make sure the current_user is still authenticated.
    if current_user.is_authenticated:
        if st:
            print('update-device: %s' % msg)
            st.changeDevice(msg['deviceId'], msg['capability'], msg['state'], current_user)
        else:
            print('st object not defined!')
    else:
        print('Current user no longer authenticated! [user_id: %s]' % session['_user_id'])
        emit('location_data', '', broadcast=False)  # Send an empty event to notify browser user is no longer authorized

@socketio.on('update-thermostat')
def socket_update_thermostat(msg):
    # Make sure the current_user is still authenticated.
    if current_user.is_authenticated:
        if st:
            print('update-thermostat: %s' % msg)
            st.changeThermostat(msg, current_user)
        else:
            print('st object not defined!')
    else:
        print('Current user no longer authenticated! [user_id: %s]' % session['_user_id'])
        emit('location_data', '', broadcast=False)  # Send an empty event to notify browser user is no longer authorized

@socketio.on('run-scene')
def socket_run_scene(msg):
    if current_user.is_authenticated:
        if st:
            print('run-scene: %s' % msg)
            if not st.runScene(msg['scene_id'], current_user):
                print('Failed running scene!')
        else:
            print('st object not defined!')
    else:
        print('Current user no longer authenticated! [user_id: %s]' % session['_user_id'])
        emit('location_data', '', broadcast=False)  # Send an empty event to notify browser user is no longer authorized

# This is the login route.  If a users tries to go directly to any URL that requires a login (has the @login_required decorator)
#   before being authenticated, they will be redirected to this URL.  This is defined in the login_manager.login_view setting above.
@app.route('/login', methods=['GET'])
def login():
    if current_user.is_authenticated: # No need to have a logged in user login again.
        return redirect(url_for('index'))
    # The 'next' query parameter will be set automatically by the login_manager
    #   if the user tried to go directly to @login_required URL before authenticating.
    next_page = request.args.get('next')
    print('next: %s' % next_page)
    if not next_page or url_parse(next_page).netloc != '':  # If there is no next query parameter, default to index.
        next_page = url_for('index')
    return render_template('login.html', next_page=next_page)

@app.route('/login', methods=['POST']) # The browser user click the Login button...
def login_post():
    email = request.form.get('email')
    password = request.form.get('password')
    remember = True if request.form.get('remember') else False

    user = User.query.filter_by(email=email).filter_by(active=True).first() # Let's see if this user exists...
    print('User: %s' % user)

    # Capture the IP address so we can check Guest users and log it...
    if request.headers.getlist('X-Forwarded-For'):
        ip = request.headers.getlist('X-Forwarded-For')[0]
    else:
        ip = request.remote_addr

    if user and user.role == 'Guest': # If this is a Guest user, make sure they are logging in from the local network only...
        if LOCAL_NETWORK_IP[0] in ip or LOCAL_NETWORK_IP[1] in ip:
            print(f'Guest User [{user.name}] is connected to local network.  Allowed...')
        else:
            print(f'Guest User [{user.name}] is NOT connected to local network.  Aborting...')
            flash(f'Guest Users Must Be Connected to Local Network')
            return redirect(url_for('login')) # If not, send them back to the Login page.

    # If the user exists in the db, but the password is empty, then take the entered password, hash it, and update the db.
    #   This is how I add a new user to the db without setting the password for them.
    if user and user.password == '':
        print('Setup user!')
        user.password=generate_password_hash(password, method='sha256')
        db.session.commit()

    # Check if the user actually exists and is active
    # Take the user-supplied password, hash it, and compare it to the hashed password in the database
    if not user or not user.active or not check_password_hash(user.password, password):
        # If there's a problem, create a FailedLogin event.
        failed_user = FailedLogin(email=email, password=password, date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip)
        db.session.add(failed_user)
        db.session.commit()

        flash('Please check your login details and try again.')
        return redirect(url_for('login')) # if the user doesn't exist or password is wrong, reload the page

    try: # This just captures the last login for the user in case we decide to use it later.
         # We wrap it in a try in case there was no previous login.
        userLogin = UserLogin.query.filter_by(user_id=user.id).filter_by(event='login').order_by(UserLogin.date.desc()).first()
        print("Last Login: %s" % userLogin.date)
    except:
        pass

    # If the above check passes, then we know the user has the right credentials
    login_user(user, remember=remember)
    session.permanent = True # This is the flask session.  It's set to permanent, but the PERMANENT_SESSION_LIFETIME is applied for expiration.

    # Record the login event.  Remove if desired.
    if UserLogging.query.filter(UserLogging.event == 'login').filter(UserLogging.log_event == True).first():
        user.logins.append(UserLogin(event='login', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()

    # This is the next query parameter that we passed through from the login GET request.
    #  If it was set, we want to now redirect the user to the URL they originally tried to go to.
    next_page = request.args.get('next')
    print('next: %s' % next_page)
    if not next_page or url_parse(next_page).netloc != '':
        next_page = url_for('index')
    return redirect(next_page)

@app.route('/logout')
def logout():
    if current_user.is_authenticated:  # If the user is logged in, record the event and log them out.
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        if UserLogging.query.filter(UserLogging.event == 'logout').filter(UserLogging.log_event == True).first():
            current_user.logins.append(UserLogin(event='logout', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
            db.session.commit()
        logout_user()
    return redirect(url_for('login')) # Logged in or not, redirect to the login page.

# Admin Home Page
@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    if UserLogging.query.filter(UserLogging.event == 'config-view').filter(UserLogging.log_event == True).first():
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        current_user.logins.append(UserLogin(event='config-view', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()
    return render_template('admin_home.html')

# Admin View User Logs
@app.route('/admin-view-logs')
@login_required
def admin_view_logs():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    results = UserLogin.query.all()
    logData = {'logs': []}
    for log in results:
        email = User.query.get(log.user_id).email
        logData['logs'].append({'id': log.id, 'user_id': log.user_id, 'email': email, 'event': log.event, 'date': log.date, 'ip': log.ip})
    return render_template('admin_logs.html', logData=logData)

# Admin Delete User Logs
@app.route('/delete-user-logs', methods=['POST'])
@login_required
def admin_delete_logs():
    print('delete-user-logs')
    if current_user.role != 'Admin':
        return 'Fail', 403
    logData = request.get_json()
    print('logData: %s' % logData)
    for log in logData['logs']:
        logRecord = UserLogin.query.get(log['id'])
        if logRecord:
            db.session.delete(logRecord)
            db.session.commit()
    if UserLogging.query.filter(UserLogging.event == 'log-delete').filter(UserLogging.log_event == True).first():
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        current_user.logins.append(UserLogin(event='log-delete', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()
    return 'OK', 200

# Admin Failed Logins
@app.route('/admin-failed-logins')
@login_required
def admin_failed_logins():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    results = FailedLogin.query.all()
    logData = {'data': []}
    for data in results:
        logData['data'].append({'id': data.id, 'email': data.email, 'password': data.password, 'date': data.date, 'ip': data.ip})
    return render_template('admin_failed_login.html', logData=logData)

# Admin Delete Failed Login
@app.route('/delete-failed-login', methods=['POST'])
@login_required
def admin_delete_failed_login():
    print('delete-failed-login')
    if current_user.role != 'Admin':
        return 'Fail', 403
    logData = request.get_json()
    print('logData: %s' % logData)
    for log in logData['logs']:
        logRecord = FailedLogin.query.get(log['id'])
        if logRecord:
            db.session.delete(logRecord)
            db.session.commit()
    if UserLogging.query.filter(UserLogging.event == 'log-delete').filter(UserLogging.log_event == True).first():
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        current_user.logins.append(UserLogin(event='log-delete', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()
    return 'OK', 200

# Admin Configure Logging
@app.route('/admin-logging')
@login_required
def admin_logging():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    results = UserLogging.query.all()
    logData = {'logs': []}
    for log in results:
        logData['logs'].append({'id': log.id, 'event': log.event, 'log_event': '1' if log.log_event else '0'})
    return render_template('admin_logging.html', logData=logData)

# Admin Updating Logging
@app.route('/update-logging', methods=['POST'])
@login_required
def update_logging():
    if current_user.role != 'Admin':
        return 'Fail', 403
    print('update-logging')
    logData = request.get_json()
    print(logData)
    for log in logData['logs']:
        print('id: %s' % log['id'])
        logRecord = UserLogging.query.get(int(log['id']))
        if logRecord:
            logRecord.log_event = True if log['log_event'] == '1' else False
            db.session.commit()
    if UserLogging.query.filter(UserLogging.event == 'config-update').filter(UserLogging.log_event == True).first():
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        current_user.logins.append(UserLogin(event='config-update', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()
    return 'OK', 200

# Admin Maintain Users
@app.route('/admin-users')
@login_required
def admin_users():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    results = User.query.all()
    userData = {"users": []}
    for user in results:
        userData['users'].append({"id": user.id, "name": user.name, "email": user.email, "role": user.role, "active": 1 if user.active else 0})
    return render_template('admin_users.html', userData=userData)

@app.route('/update-users', methods=['POST'])
@login_required
def update_users():
    if current_user.role != 'Admin':
        return 'Fail', 403
    print('update-users')
    userData = request.get_json()
    print(userData)
    for user in userData['users']:
        print('updating user: %s' % user['id'])
        userRecord = User.query.get(int(user['id']))
        if userRecord:
            userRecord.name = user['name']
            userRecord.role = user['role']
            userRecord.active = True if user['active'] == '1' else False
            if user['reset'] == '1':
                userRecord.password = ''
            db.session.commit()
    if UserLogging.query.filter(UserLogging.event == 'user-update').filter(UserLogging.log_event == True).first():
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        current_user.logins.append(UserLogin(event='user-update', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()
    return 'OK', 200

@app.route('/new-user', methods=['POST'])
@login_required
def new_user():
    if current_user.role != 'Admin':
        return 'Fail', 403
    print('new-user')
    userData = request.get_json()
    print(userData)
    if not User.query.filter(User.email == userData['email']).first():
        user = User(
            active=True if userData['active'] == '1' else False,
            email=userData['email'],
            password='',
            name=userData['name'],
            role=userData['role']
        )
        db.session.add(user)
        db.session.commit()
    if UserLogging.query.filter(UserLogging.event == 'user-update').filter(UserLogging.log_event == True).first():
        if request.headers.getlist('X-Forwarded-For'):
            ip = request.headers.getlist('X-Forwarded-For')[0]
        else:
            ip = request.remote_addr
        current_user.logins.append(UserLogin(event='user-update', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
        db.session.commit()
    return 'OK', 200

# Admin Presence Sensor Config
@app.route('/config-presence')
@login_required
def config_presence():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    configData = st.getPresence()
    return render_template('admin_presence.html', configData=configData)

@app.route('/update-presence-configs', methods=['POST'])
@login_required
def update_presence_configs():
    if current_user.role == 'Admin':
        print('update-presence-configs')
        configData = request.get_json()
        print(configData)
        if st.updatePresenceConfigs(configData):
            st.readData(refresh=False)
            location_data = json.dumps(st.location)
            socketio.emit('location_data', location_data, room=st.location_id) #Broadcase any changes to all users.
            if UserLogging.query.filter(UserLogging.event == 'presence-update').filter(UserLogging.log_event == True).first():
                if request.headers.getlist('X-Forwarded-For'):
                    ip = request.headers.getlist('X-Forwarded-For')[0]
                else:
                    ip = request.remote_addr
                current_user.logins.append(UserLogin(event='presence-update', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
                db.session.commit()
            return 'OK', 200
        return 'Fail', 200
    return 'Fail', 403

# Admin Scenes Config
@app.route('/config-scenes')
@login_required
def config_scenes():
    if current_user.role != 'Admin':
        return redirect(url_for('index'))
    configData = st.getScenes()
    return render_template('admin_scenes.html', configData=configData)

@app.route('/update-scene-configs', methods=['POST'])
@login_required
def update_scene_configs():
    if current_user.role == 'Admin':
        print('update-scene-configs')
        configData = request.get_json()
        print(configData)
        print('Scene items: %d' % len(configData['scenes']))
        if st.updateSceneConfigs(configData):
            st.readData(refresh=False)
            location_data = json.dumps(st.location)
            socketio.emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.
            if UserLogging.query.filter(UserLogging.event == 'scene-update').filter(UserLogging.log_event == True).first():
                if request.headers.getlist('X-Forwarded-For'):
                    ip = request.headers.getlist('X-Forwarded-For')[0]
                else:
                    ip = request.remote_addr
                current_user.logins.append(UserLogin(event='scene-update', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
                db.session.commit()
            return 'OK', 200
        return 'Fail', 200
    return 'Fail', 403

# To access this page, the user must be logged in and also have an Admin role.
@app.route('/config-rooms')
@login_required
def config_rooms():
    if current_user.role == 'Admin':
        configData = st.getConfig()
        return render_template('admin_rooms.html', configData=configData)
    # If the user isn't an Admin, log them out, flash them a message, and send back to the login page.
    logout_user()
    flash("You must be an Administrator to access this page!")
    return redirect(url_for('login'))

# Obviously, we want to make sure the user is logged in here and is an admin.
@app.route('/update-room-configs', methods=['POST'])
@login_required
def update_room_configs():
    if current_user.role == 'Admin':
        print('update-room-configs')
        configData = request.get_json()
        print(configData)
        print('Location items: %d' % len(configData['location']))
        if st.updateConfigs(configData):
            st.readData(refresh=False)
            location_data = json.dumps(st.location)
            socketio.emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.
            if UserLogging.query.filter(UserLogging.event == 'config-update').filter(UserLogging.log_event == True).first():
                if request.headers.getlist('X-Forwarded-For'):
                    ip = request.headers.getlist('X-Forwarded-For')[0]
                else:
                    ip = request.remote_addr
                current_user.logins.append(UserLogin(event='config-update', date=datetime.now().strftime('%m/%d/%y %H:%M:%S'), ip=ip))
                db.session.commit()
            return 'OK', 200
        return 'Fail', 200
    return 'Fail', 403

# Admin Refresh Scenes
@app.route('/admin-refresh-scenes', methods=['POST'])
@login_required
def admin_refresh_scenes():
    if current_user.role != 'Admin':
        return 'Fail', 403
    if st.loadAllScenes():
        if st.readAllScenes():
            location_data = json.dumps(st.location)
            socketio.emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.            
            return 'OK', 200
    return 'Fail', 200

# Admin Refresh All Devices Status
@app.route('/admin-refresh-device-status', methods=['POST'])
@login_required
def admin_refresh_device_status():
    if current_user.role != 'Admin':
        return 'Fail', 403
    if st.loadAllDevicesStatus():
        location_data = json.dumps(st.location)
        socketio.emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.            
        return 'OK', 200
    return 'Fail', 200

# Admin Refresh All Devices Health
@app.route('/admin-refresh-device-health', methods=['POST'])
@login_required
def admin_refresh_device_health():
    if current_user.role != 'Admin':
        return 'Fail', 403
    if st.loadAllDevicesHealth():
        location_data = json.dumps(st.location)
        socketio.emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.            
        return 'OK', 200
    return 'Fail', 200

# Admin Refresh Foundation Data (App, Location, Rooms, Devices)
@app.route('/admin-refresh-foundation', methods=['POST'])
@login_required
def admin_refresh_foundation():
    if current_user.role != 'Admin':
        return 'Fail', 403
    if st.loadData():
        if st.readData(refresh=False):
            location_data = json.dumps(st.location)
            socketio.emit('location_data', location_data, room=st.location_id) #Broadcast any changes to all users.            
            return 'OK', 200        
    return 'Fail', 200

# Only logged in users can see the dashboard.
@app.route('/', methods=['GET'])
@login_required
def index():
    return render_template('dashboard.html')

@app.route('/', methods=['POST'])
def smarthings_requests():
    content = request.get_json()
    print('AppId: %s\nLifeCycle: %s' % (content['appId'], content['lifecycle']))

    if (content['lifecycle'] == 'PING'):
        print('PING: %s' % content)
        challenge = content['pingData']['challenge']
        data = {'pingData':{'challenge': challenge}}
        return jsonify(data)

    elif (content['lifecycle'] == 'CONFIRMATION'):
        confirmationURL = content['confirmationData']['confirmationUrl']
        r = requests.get(confirmationURL)
        print('CONFIRMATION\nContent: %s\nURL: %s\nStatus: %s' % (content,confirmationURL,r.status_code))
        if r.status_code == 200:
            return r.text
        else:
            abort(r.status_code)

    elif (content['lifecycle'] == 'CONFIGURATION' and content['configurationData']['phase'] == 'INITIALIZE'):
        print(content['configurationData']['phase'])

        if content['appId'] == ST_WEBHOOK:
            data = {
                      "configurationData": {
                        "initialize": {
                          "name": "ST Test Webhook App",
                          "description": "ST Test Webhook App",
                          "id": "st_webhook_app_page_1",
                          "permissions": [
                            "r:devices:*"
                          ],
                          "firstPageId": "1"
                        }
                      }
                    }
        else:
            data = {'appId':'Not Recognized'}
            print('Initialize Unknown appId: %s' % content['appId'])

        return jsonify(data)

    elif (content['lifecycle'] == 'CONFIGURATION' and content['configurationData']['phase'] == 'PAGE'):
        print(content['configurationData']['phase'])
        pageId = content['configurationData']['pageId']

        if content['appId'] == ST_WEBHOOK:
            data = {
                      "configurationData": {
                        "page": {
                          "pageId": "1",
                          "name": "Select Devices",
                          "nextPageId": "null",
                          "previousPageId": "null",
                          "complete": "true",
                          "sections": [
                            {
                              "name": "Allow full access to all rooms and devices?",
                              "settings": [
                                {
                                  "id": "allowFullAccess",
                                  "name": "Allow?",
                                  "description": "Select Yes to allow app to function",
                                  "type": "ENUM",
                                  "required": "true",
                                  "multiple": "false",
                                  "options": [
                                     {
                                       "id": "yes",
                                       "name": "Yes"
                                     },
                                     {
                                       "id": "no",
                                       "name": "No"
                                     }
                                  ]
                                }
                              ]
                            }
                          ]
                        }
                      }
                    }
        else:
            data = {'appId':'Not Recognized'}
            print('Page Unknown appId: %s' % content['appId'])

        return jsonify(data)

    elif (content['lifecycle'] == 'INSTALL'):
        print(content['lifecycle'])
        data = {'installData':{}}
        resp = content['installData']

        if content['appId'] == ST_WEBHOOK:
            print('Installing ST Webhook')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'switch', 'switch', 'capSwitchSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'lock', 'lock', 'capLockSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'temperatureMeasurement', 'temperature', 'capTempSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'relativeHumidityMeasurement', 'humidity', 'capHumiditySubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'doorControl', 'door', 'capDoorSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'contactSensor', 'contact', 'capContactSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'motionSensor', 'motion', 'capMotionSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'switchLevel', 'level', 'capSwitchLevelSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'battery', 'battery', 'capBatterySubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'presenceSensor', 'presence', 'capPresenceSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatOperatingState', 'thermostatOperatingState', 'capOperatingStateSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatMode', 'thermostatMode', 'capModeSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatCoolingSetpoint', 'coolingSetpoint', 'capCoolSetpointSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatHeatingSetpoint', 'heatingSetpoint', 'capHeatSetpointSubscription')
            st.deviceHealthSubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'])
        else:
            data = {'appId':'Not Recognized'}
            print('Install Unknown appId: %s' % content['appId'])

        return jsonify(data)

    elif (content['lifecycle'] == 'UPDATE'):
        print(content['lifecycle'])
        data = {'updateData':{}}
        resp = content['updateData']
        print('resp: %s' % resp)

        if content['appId'] == ST_WEBHOOK:
            print('Updating ST Webhook')
            st.deleteSubscriptions(resp['authToken'], resp['installedApp']['installedAppId'])
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'switch', 'switch', 'capSwitchSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'lock', 'lock', 'capLockSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'temperatureMeasurement', 'temperature', 'capTempSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'relativeHumidityMeasurement', 'humidity', 'capHumiditySubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'doorControl', 'door', 'capDoorSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'contactSensor', 'contact', 'capContactSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'motionSensor', 'motion', 'capMotionSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'switchLevel', 'level', 'capSwitchLevelSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'battery', 'battery', 'capBatterySubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'presenceSensor', 'presence', 'capPresenceSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatOperatingState', 'thermostatOperatingState', 'capOperatingStateSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatMode', 'thermostatMode', 'capModeSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatCoolingSetpoint', 'coolingSetpoint', 'capCoolSetpointSubscription')
            st.capabilitySubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'], 'thermostatHeatingSetpoint', 'heatingSetpoint', 'capHeatSetpointSubscription')
            st.deviceHealthSubscriptions(resp['authToken'], resp['installedApp']['locationId'], resp['installedApp']['installedAppId'])
        else:
            data = {'appId':'Not Recognized'}
            print('Update Unknown appId: %s' % content['appId'])

        return jsonify(data)

    elif (content['lifecycle'] == 'OAUTH_CALLBACK'):
        print(content['lifecycle'])
        data = {'oAuthCallbackData':{}}
        return jsonify(data)

    elif (content['lifecycle'] == 'EVENT'):
        data = {'eventData':{}}

        event = content['eventData']['events'][0]

        if content['appId'] == ST_WEBHOOK:
            if event['eventType'] == 'DEVICE_EVENT':
                device = event['deviceEvent']
                emit_val = st.updateDevice(device['deviceId'], device['capability'], device['attribute'], device['value'])
                if emit_val:
                    print('emit_val: ', emit_val)
                    print('Emitting: %s: %s to room: %s' % (emit_val[0], emit_val[1], device['locationId']))
                    socketio.emit(emit_val[0],emit_val[1], room=device['locationId'])
            elif event['eventType'] == 'DEVICE_HEALTH_EVENT':
                data = event['deviceHealthEvent']
                if st.updateDeviceHealth(data['deviceId'], data['status']):
                    socketio.emit('location-data', json.dumps(st.location), room=data['locationId'])
        else:
            data = {'appId':'Not Recognized'}
            print('Event Unknown appId: %s' % content['appId'])

        return jsonify(data)

    elif (content['lifecycle'] == 'UNINSTALL'):
        print(content['lifecycle'])
        data = {'uninstallData':{}}
        return jsonify(data)

    else:
        print('Unknown Lifecycle: %s' % content['lifecycle'])
        return '',404

@app.route('/test')
def test():
    return 'OK'

@app.route('/apple-touch-icon-152x152.png')
@app.route('/apple-touch-icon-152x152-precomposed.png')
@app.route('/apple-touch-icon-120x120-precomposed.png')
@app.route('/apple-touch-icon-120x120.png')
@app.route('/apple-touch-icon-precomposed.png')
@app.route('/apple-touch-icon.png')
@app.route('/favicon.ico')
def favicon():
    print('favicon')
    return send_from_directory('/home/pi/static', 'favicon.png')

if __name__ == '__main__':
    st = SmartThings()
#    st.initialize(refresh=False) # Use this during development (after st.initialize() first) to eliminate API calls.
    st.initialize()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
