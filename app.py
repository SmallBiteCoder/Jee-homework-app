from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_pymongo import PyMongo
from bcrypt import hashpw, checkpw, gensalt
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import uuid
import os
from bson import ObjectId

from uuid import uuid4

from dotenv import load_dotenv
load_dotenv() 

app = Flask(__name__)
app.secret_key = os.urandom(24)


app.config["MONGO_URI"] =os.getenv("MONGO_URI")

mongo = PyMongo(app)

jee_db = mongo.cx['jee_tracker'] # type: ignore





    
@app.route('/update_syllabus/<syllabus_id>', methods=['POST'])
def update_syllabus(syllabus_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = jee_db.users.find_one({'username': session['username']})
    user_id = user['_id']
    completed = request.json.get('completed', False)

    # Remove old record if it exists
    jee_db.syllabus.update_one(
        {'_id': ObjectId(syllabus_id)},
        {'$pull': {'completed_by': {'user_id': user_id}}}
    )

    # Add new record
    if completed:
        jee_db.syllabus.update_one(
            {'_id': ObjectId(syllabus_id)},
            {'$push': {'completed_by': {'user_id': user_id}}}
        )

    return jsonify({'success': True})

@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = jee_db.users.find_one({'username': session['username']})
    today = datetime.now().strftime('%Y-%m-%d')
    homeworks = list(jee_db.homework.find({'date': today}))
    syllabus = list(jee_db.syllabus.find())
    backlog = list(jee_db.backlog.find({'user_id': user['_id']}))
    revisions = list(jee_db.revisions.find({'user_id': user['_id']}))
    time_logs = list(jee_db.time_logs.find({'user_id': user['_id'], 'date': today}))
    revisions_raw = list(jee_db.revisions.find({'user_id': user['_id']}))

# Flatten the revisions
    revisions = []
    for rev in revisions_raw:
        for date in rev['dates']:
            revisions.append({
                'topic': rev['topic'],
                'date': date,
                '_id': str(rev['_id']),
                  'uid' : str(uuid4())  # optional: to allow completion
            })
    

    print(revisions)

    return render_template('index.html', user=user, homeworks=homeworks, syllabus=syllabus, backlog=backlog, revisions=revisions, time_logs=time_logs,date=today
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')
        user = jee_db.users.find_one({'username': username})
        if user and checkpw(password, user['password']):
            session['username'] = username
            session.permanent = True
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')
        email = request.form['email']
        if jee_db.users.find_one({'username': username}):
            flash('Username already exists')
        else:
            hashed = hashpw(password, gensalt())
            jee_db.users.insert_one({'_id': str(uuid.uuid4()), 'username': username, 'password': hashed, 'email': email})
            session['username'] = username
            return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/account', methods=['GET', 'POST'])
def account():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = jee_db.users.find_one({'username': session['username']})
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        if password:
            hashed = hashpw(password.encode('utf-8'), gensalt())
            jee_db.users.update_one({'_id': user['_id']}, {'$set': {'email': email, 'password': hashed}})
        else:
            jee_db.users.update_one({'_id': user['_id']}, {'$set': {'email': email}})
        flash('Account updated')
    return render_template('account.html', user=user)

@app.route('/add_homework', methods=['GET', 'POST'])
def add_homework():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        admin_code = request.form['admin_code']
        if admin_code != 'ADMIN123':  # Replace with secure admin code
            flash('Invalid admin code')
            return redirect(url_for('index'))
        title = request.form['title']
        description = request.form['description']
        date = request.form['date']
        jee_db.homework.insert_one({'title': title, 'description': description, 'date': date, 'completed_by': []})
        
        return redirect(url_for('index'))
    return render_template('add_homework.html')

@app.route('/completed_by/<homework_id>')
def completed_by(homework_id):
    homework = jee_db.homework.find_one({'_id': ObjectId(homework_id)})
    if not homework:
        return jsonify({'error': 'Homework not found'}), 404

    user_ids = homework.get('completed_by', [])
    users = list(jee_db.users.find({'_id': {'$in': user_ids}}, {'username': 1}))
    usernames = [user['username'] for user in users]

    return jsonify(usernames)

@app.route('/complete_homework/<homework_id>', methods=['POST'])
def complete_homework(homework_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user = jee_db.users.find_one({'username': session['username']})
    if not user:
        return jsonify({'error': 'User not found'}), 404

    user_id = user['_id']
    hw_id = ObjectId(homework_id)

    # Check if user already completed it
    homework = jee_db.homework.find_one({'_id': hw_id})
    if not homework:
        return jsonify({'error': 'Homework not found'}), 404

    if user_id in homework.get('completed_by', []):
        # ✅ User already marked it, so remove
        jee_db.homework.update_one(
            {'_id': hw_id},
            {'$pull': {'completed_by': user_id}}
        )
        status = 'removed'
    else:
        # ✅ User not in list, so add
        jee_db.homework.update_one(
            {'_id': hw_id},
            {'$addToSet': {'completed_by': user_id}}
        )
        status = 'added'

    return jsonify({'success': True, 'status': status})



@app.route('/past_homework')
def past_homework():
    if 'username' not in session:
        return redirect(url_for('login'))
    today = datetime.now().strftime('%Y-%m-%d')
    homeworks = list(jee_db.homework.find({'date': {'$ne': today}}))
    return render_template('past_homework.html', homeworks=homeworks)

@app.route('/add_syllabus', methods=['GET', 'POST'])
def add_syllabus():
    if 'username' not in session:
        return redirect(url_for('login'))
    user = jee_db.users.find_one({'username': session['username']})
    if request.method == 'POST':
        admin_code = request.form['admin_code']
        if admin_code != 'ADMIN123':
            flash('Invalid admin code')
            return redirect(url_for('index'))
        topic = request.form['topic']
        target = request.form['target']
        jee_db.syllabus.insert_one({'user_id': user['_id'], 'topic': topic, 'target': target, 'completed': False})
        return redirect(url_for('index'))
    return render_template('add_syllabus.html')

@app.route('/add_backlog', methods=['POST'])
def add_backlog():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user = jee_db.users.find_one({'username': session['username']})
    topic = request.form['topic']
    jee_db.backlog.insert_one({'user_id': user['_id'], 'topic': topic, 'created_at': datetime.now()})
    return redirect(url_for('index'))

@app.route('/add_revision', methods=['POST'])
def add_revision():
    if 'username' not in session:
        return redirect(url_for('login'))

    topic = request.form.get('topic', '').strip()
    dates = request.form.getlist('dates')  # Handles multiple

    if not topic or not dates:
        return redirect(url_for('index'))  # Prevent empty

    user = jee_db.users.find_one({'username': session['username']})
    jee_db.revisions.insert_one({
        'user_id': user['_id'],
        'topic': topic,
        'dates': dates
    })
    return redirect(url_for('index'))

@app.route('/complete_revision/<revision_id>', methods=['POST'])
def complete_revision(revision_id):
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    date = data.get('date')

    user = jee_db.users.find_one({'username': session['username']})

    jee_db.revisions.update_one(
        {'_id': ObjectId(revision_id), 'user_id': user['_id']},
        {'$pull': {'dates': date}}
    )

    # Optional: Delete the whole doc if no dates left
    jee_db.revisions.delete_one({'_id': ObjectId(revision_id), 'user_id': user['_id'], 'dates': {'$size': 0}})

    return jsonify({'success': True})

@app.route('/add_revision_modal', methods=['POST'])
def add_revision_modal():
    print("adding")
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    topic = data.get('topic', '').strip()
    dates = data.get('dates', [])

    if not topic or not dates:
        return jsonify({'error': 'Invalid input'}), 400

    user = jee_db.users.find_one({'username': session['username']})
    jee_db.revisions.insert_one({
        'user_id': user['_id'],
        'topic': topic,
        'dates': dates
    })

    return jsonify({'success': True})


@app.route('/add_time_log', methods=['POST'])
def add_time_log():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    user = jee_db.users.find_one({'username': session['username']})
    hours = float(request.form['hours'])
    date = datetime.now().strftime('%Y-%m-%d')
    jee_db.time_logs.insert_one({'user_id': user['_id'], 'hours': hours,  'date': date})
    return redirect(url_for('index'))

@app.route('/complete_backlog/<backlog_id>', methods=['POST'])
def complete_backlog(backlog_id):
    print("working")
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    print("user")
    user = jee_db.users.find_one({'username': session['username']})
    jee_db.backlog.delete_one({'_id': ObjectId(backlog_id), 'user_id': user['_id']})
    return jsonify({'success': True})


@app.route('/leaderboard')
def leaderboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    today = datetime.now().strftime('%Y-%m-%d')
    pipeline = [
        {'$match': {'date': today}},
        {'$group': {'_id': '$user_id', 'total_hours': {'$sum': '$hours'}}}
    ]
    today_leaderboard = list(jee_db.time_logs.aggregate(pipeline))
    pipeline = [
        {'$group': {'_id': '$user_id', 'total_hours': {'$sum': '$hours'}}}
    ]
    total_leaderboard = list(jee_db.time_logs.aggregate(pipeline))
    users = {u['_id']: u['username'] for u in jee_db.users.find()}
    return render_template('leaderboard.html', today_leaderboard=today_leaderboard, total_leaderboard=total_leaderboard, users=users)

if __name__ == '__main__':
    app.run(debug=True)