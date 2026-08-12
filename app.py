from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
import os
import pandas as pd
from functools import wraps
from datetime import datetime   # ← Important
from scheduler import run_scheduler

app = Flask(__name__)
app.secret_key = "disco_scheduler_2026_secret_key_change_me"

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "staff1": {"password": "staff123", "role": "staff"}
}

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                flash('Please login first')
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash('Access denied')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username]['password'] == password:
            session['user'] = username
            session['role'] = USERS[username]['role']
            flash(f'Welcome, {username}!')
            return redirect(url_for('index'))
        flash('Invalid credentials')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out')
    return redirect(url_for('login'))


@app.route('/')
@login_required()
def index():
    return render_template('index.html')


@app.route('/upload', methods=['GET', 'POST'])
@login_required('admin')
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        
        if file and file.filename.endswith(('.xlsx', '.csv')):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'staff_data.xlsx')
            file.save(filepath)
            flash('Staff data uploaded successfully!')
            return redirect(url_for('generate'))
    
    return render_template('upload.html')


@app.route('/generate')
@login_required('admin')
def generate():
    try:
        output_file, roster_df, status, summary = run_scheduler()
        
        # ✅ Important: Always save latest CSV for staff to view
        roster_df.to_csv('latest_schedule.csv', index=False)
        
        flash('Schedule generated successfully!', 'success')
        return render_template('result.html', 
                               filename=output_file, 
                               roster=roster_df.head(50),
                               summary=summary)
    except Exception as e:
        flash(f'Error generating schedule: {str(e)}', 'danger')
        return redirect(url_for('index'))


@app.route('/download/<filename>')
@login_required()
def download_file(filename):
    try:
        return send_file(filename, as_attachment=True)
    except:
        flash("File not found")
        return redirect(url_for('index'))


@app.route('/my-schedule')
@login_required('staff')
def my_schedule():
    try:
        roster_df = pd.read_csv('latest_schedule.csv')
        
        # Try to match staff by username or Staff_ID
        user = session.get('user')
        
        # Option 1: If staff username matches Staff_ID (e.g. staff1 → S001)
        my_roster = roster_df[roster_df['Staff_ID'].astype(str).str.contains(user, na=False)]
        
        # Option 2: If you want to map usernames to Staff_IDs (Recommended)
        staff_mapping = {
            "staff1": "S001",
            "staff2": "S002",
            "staff3": "S003",
            # Add more mappings here
        }
        
        staff_id = staff_mapping.get(user)
        if staff_id:
            my_roster = roster_df[roster_df['Staff_ID'].astype(str) == staff_id]
        
        if my_roster.empty:
            flash("No schedule found for your Staff ID. Please contact Admin.", "warning")
            return redirect(url_for('index'))
            
        return render_template('my_schedule.html', roster=my_roster)
        
    except FileNotFoundError:
        flash("No schedule available yet. Please ask Admin to generate one.", "warning")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('index'))


@app.route('/full-roster')
@login_required()
def full_roster():
    try:
        # Try to read the latest schedule
        roster_df = pd.read_csv('latest_schedule.csv')
        
        if roster_df.empty:
            flash("Schedule is empty. Please generate a new one.", "warning")
            return redirect(url_for('index'))
            
        return render_template('full_roster.html', 
                             roster=roster_df.head(200), 
                             total_rows=len(roster_df))
        
    except FileNotFoundError:
        flash("No schedule available yet. Please ask Admin to generate one first.", "warning")
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Error loading roster: {str(e)}", "danger")
        return redirect(url_for('index'))




@app.route('/submit-preferences', methods=['GET', 'POST'])
@login_required('staff')
def submit_preferences():
    if request.method == 'POST':
        pref_night = int(request.form.get('pref_night', 1))
        max_night = int(request.form.get('max_night_shifts', 3))
        off_days = request.form.get('pref_off_days', '').strip()
        
        preferences = {
            'staff_id': session.get('user'),
            'pref_night': pref_night,
            'max_night_shifts': max_night,
            'pref_off_days': off_days,
            'updated_at': datetime.now().strftime('%Y-%m-%d %H:%M')
        }
        
        pref_df = pd.DataFrame([preferences])
        pref_file = 'staff_preferences.csv'
        
        if os.path.exists(pref_file):
            existing = pd.read_csv(pref_file)
            existing = existing[existing['staff_id'] != preferences['staff_id']]
            pref_df = pd.concat([existing, pref_df], ignore_index=True)
        
        pref_df.to_csv(pref_file, index=False)
        
        flash('✅ Your preferences have been saved successfully!', 'success')
        return redirect(url_for('my_schedule'))
    
    return render_template('submit_preferences.html')


@app.route('/staff-preferences')
@login_required('admin')
def staff_preferences():
    try:
        pref_df = pd.read_csv('staff_preferences.csv')
        return render_template('staff_preferences.html', preferences=pref_df)
    except FileNotFoundError:
        flash("No preferences submitted yet.", "info")
        return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)