from flask_bcrypt import Bcrypt
from flask import Flask,render_template,request,jsonify,Response
from chat import get_response
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, session, flash
import secrets
from attendance_taker import take_attendance
import attendance_taker
import pandas as pd
from datetime import datetime, timedelta
import logging
from flask_cors import CORS
import os
import base64
from apscheduler.schedulers.background import BackgroundScheduler
from flask_mail import Mail, Message
import queue
import atexit


os.environ["OPENCV_AVFOUNDATION_SKIP_AUTH"] = "1"
logging.basicConfig(level=logging.DEBUG)
app = Flask(__name__)
CORS(app)
app.config['DEBUG'] = True
mail = Mail(app)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='s.f.carrentalsystem@gmail.com',
    MAIL_PASSWORD='gdbjkhlpvnehuvqv'
)

# Generate a random secret key
secret_key = secrets.token_hex(24)
app.secret_key = secret_key
bcrypt = Bcrypt(app)
notifications = {}

# Establish MySQL database connection
database_connection = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="",
    database="Thesis"
)

# Create a cursor object to execute SQL queries
cursor = database_connection.cursor()
TIMETABLE_FILE = 'timetable.csv'
scheduler = BackgroundScheduler()
scheduler.start()

@app.route('/')
def open():
    return render_template('index.html')

# User registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        study_program = request.form['study_program']
        year_of_study = request.form['year_of_study']
        picture = request.form['photoData']

        # Check if user with the same email already exists
        cursor.execute("SELECT * FROM Log WHERE Email = %s", (email,))
        user = cursor.fetchone()
        if user:
            flash("Email already exists. Please choose a different email.", "error")
            return redirect(url_for('register'))
        picture = base64.b64decode(picture.split(',')[1])

        # Insert user into database
        cursor.execute("INSERT INTO Log (First_Name, Last_Name, Program, Study_Year, Picture, Email, Password) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                       (first_name, last_name, study_program, year_of_study, picture, email, password))
        database_connection.commit()


        # Retrieve the ID of the newly registered user
        cursor.execute("SELECT user_id FROM Log WHERE Email = %s", (email,))
        user_id = cursor.fetchone()[0]

        # Store user ID and email in session
        session['user_id'] = user_id
        session['email'] = email

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')

def fetch_attendance_data(user_id):
    query = """
    SELECT course_name, COUNT(*) AS absences
    FROM Absences
    WHERE user_id = %s
    GROUP BY course_name
    """
    cursor.execute(query, (user_id,))
    attendance_data = cursor.fetchall()
    return attendance_data

@app.route('/attendance')
def show_attendance():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in to view this page", "error")
        return redirect(url_for('login'))

    attendance_data = fetch_attendance_data(user_id)
    return render_template('attendance.html', attendance_data=attendance_data)

@app.post("/predict")
def predict():
    text = request.get_json().get("message")
    response = get_response(text)
    message = {"answer": response}
    return jsonify(message)


# User login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Query to fetch user data by email from the Log table
        cursor.execute("SELECT user_id, First_Name, Last_Name, Email, Password FROM Log WHERE Email = %s", (email,))
        user = cursor.fetchone()

        if user:
            user_id, first_name, last_name, email, hashed_password = user

            # Check the password hash
            if bcrypt.check_password_hash(hashed_password, password):
                session['user_id'] = user_id
                session['first_name'] = first_name
                session['last_name'] = last_name
                return redirect(url_for('profile'))
            else:
                return "Invalid credentials"
        else:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/profile')
def profile():
    # Check if user is logged in
    if 'user_id' in session:
        user_id = session['user_id']
        # Fetch user data from database using the user ID stored in the session
        cursor.execute("SELECT * FROM Log WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        if user:
            # Pass user data to the profile template
            return render_template('profile.html', user=user)
        else:
            flash("User not found", "error")
            return redirect(url_for('login'))
    else:
        flash("Please log in to view this page", "error")
        return redirect(url_for('login'))  # Redirect to login page if user is not logged in

@app.route('/indoor_navigation.html')
def indoor_navigation():
    return render_template('indoor_navigation.html')

@app.route('/absence_taker')
def absence_taker():
    # Check if user is logged in
    if 'user_id' in session:
        user_id = session['user_id']
        return render_template('absence_taker.html', user_id=user_id)  # Pass user_id to absence_taker.html
    else:
        flash("Please log in to view this page", "error")
        return redirect(url_for('login'))  # Redirect to login page if user is not logged in

# Route to handle attendance taking
@app.route('/take_attendance', methods=['POST'])
def handle_attendance():
    if 'user_id' in session:
        user_id = session['user_id']
        latitude = session.get('latitude')
        longitude = session.get('longitude')
        if latitude is None or longitude is None:
            return jsonify({"error": "Missing location data"}), 400

            # Call the take_attendance function
        result = attendance_taker.take_attendance(latitude, longitude, user_id)
        # Return the result as JSON response
        return jsonify(result)
    else:
        return jsonify({"error": "User not logged in"}), 401

@app.route('/submit_location', methods=['POST'])
def submit_location():
    try:
        data = request.get_json()
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return jsonify({"error": "Missing latitude or longitude"}), 400

        # Save location in session or handle as needed
        session['latitude'] = latitude
        session['longitude'] = longitude
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/start_attendance', methods=['POST'])
def start_attendance():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "User not logged in"}), 401

        user_id = session['user_id']
        latitude = session.get('latitude')
        longitude = session.get('longitude')

        if latitude is None or longitude is None:
            return jsonify({"error": "Missing location data"}), 400

        print(f"Starting attendance with latitude: {latitude}, longitude: {longitude}, user_id: {user_id}")
        result = attendance_taker.take_attendance(latitude, longitude, user_id)
        return jsonify({"message": "Attendance process completed", "result": result}), 200
    except Exception as e:
        print(f"Error in /start_attendance: {e}")  # Debugging line
        return jsonify({"error": str(e)}), 500


def record_absences():
    try:
        current_time = datetime.now()
        current_day = current_time.strftime("%A")
        logging.debug(f"Current time: {current_time}, Current day: {current_day}")

        # Fetch timetable
        timetable = pd.read_csv(TIMETABLE_FILE)

        # Loop through each row in the timetable
        for index, row in timetable.iterrows():
            day = row['Day']
            if day == current_day:
                for time_slot in ['09:00 - 11:00', '11:00 - 13:00', '13:00 - 15:00']:
                    course_name = row[time_slot]
                    if pd.notna(course_name):
                        start_time_str, end_time_str = time_slot.split(' - ')
                        start_time = datetime.strptime(start_time_str, '%H:%M').time()
                        end_time = datetime.strptime(end_time_str, '%H:%M').time()
                        logging.debug(f"Checking time slot: {time_slot}, Course: {course_name}, Start time: {start_time}, End time: {end_time}")

                        # Check if current time is within the class time slot
                        if start_time <= current_time.time() <= end_time:
                            logging.debug(f"Current time {current_time.time()} is within the slot {time_slot} for course {course_name}")

                            # Check if any student has not checked in
                            cursor.execute("SELECT user_id FROM Log")
                            students = cursor.fetchall()
                            for student in students:
                                student_id = student[0]
                                cursor.execute("SELECT * FROM Attendance WHERE user_id = %s AND Course = %s AND DATE(Time) = %s",
                                               (student_id, course_name, current_time.date()))
                                attendance_record = cursor.fetchone()
                                if not attendance_record:
                                    formatted_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
                                    cursor.execute("INSERT INTO Absences (user_id, course_name, date) VALUES (%s, %s, %s)",
                                                   (student_id, course_name, formatted_time))
                                    database_connection.commit()
                                    logging.debug(f"Recorded absence for student {student_id} in course {course_name}")

    except Exception as e:
        logging.error(f"Error in record_absences: {e}")

# Schedule the record_absences function to run every day at the end of each class slot
scheduler.add_job(record_absences, 'cron', hour='11,13,15', minute=5)






def send_notification(email, subject, body, user_id):
    try:
        msg = Message(subject, sender='s.f.carrentalsystem@gmail.com', recipients=[email])
        msg.body = body
        mail.send(msg)  # Use the mail instance to send the message
        if user_id not in notifications:
            notifications[user_id] = queue.Queue()
        notifications[user_id].put(body)  # Add the notification to the queue for the user
        logging.info(f"Notification sent to {email}: {body}")
    except Exception as e:
        logging.error(f"Error sending email: {e}")

def fetch_todays_classes():
    df = pd.read_csv(TIMETABLE_FILE)
    today = datetime.now().strftime("%A")
    todays_classes = df[df['Day'] == today]
    logging.debug(f"Today's classes: {todays_classes}")
    return todays_classes

def notify_upcoming_classes():
    try:
        query = "SELECT user_id, Email FROM Log"
        cursor.execute(query)
        users = cursor.fetchall()
        logging.debug(f"Fetched users: {users}")

        for user_id, email in users:
            classes = fetch_todays_classes()
            now = datetime.now()

            for _, class_ in classes.iterrows():
                for time_slot in ['09:00 - 11:00', '11:00 - 13:00', '13:00 - 15:00']:
                    class_name = class_[time_slot]
                    if pd.notna(class_name):
                        start_time_str, end_time_str = time_slot.split(' - ')
                        start_time = datetime.strptime(start_time_str, '%H:%M').time()

                        # Notify 10 minutes before class starts
                        notification_time = (datetime.combine(now.date(), start_time) - timedelta(minutes=10)).time()
                        logging.debug(f"Current time: {now.time()}, Notification time: {notification_time}, Start time: {start_time}")

                        if notification_time <= now.time() < start_time:
                            send_notification(email, "Upcoming Class", f"Your class '{class_name}' is starting in 10 minutes.", user_id)

    except Exception as e:
        logging.error(f"Error in notify_upcoming_classes: {e}")

def fetch_tomorrows_classes():
    df = pd.read_csv(TIMETABLE_FILE)
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%A")
    tomorrows_classes = df[df['Day'] == tomorrow]
    logging.debug(f"Tomorrow's classes: {tomorrows_classes}")
    return tomorrows_classes

def notify_study_reminder():
    try:
        query = "SELECT user_id, Email FROM Log"
        cursor.execute(query)
        users = cursor.fetchall()
        logging.debug(f"Fetched users for study reminder: {users}")

        for user_id, email in users:
            classes = fetch_tomorrows_classes()
            if not classes.empty:
                class_names = ', '.join(classes[['09:00 - 11:00', '11:00 - 13:00', '13:00 - 15:00']].fillna('').values.flatten())
                class_names = ', '.join(filter(None, class_names.split(',')))
                send_notification(email, "Study Reminder", f"Remember to study for your classes tomorrow: {class_names}.", user_id)

    except Exception as e:
        logging.error(f"Error in notify_study_reminder: {e}")

@app.route('/notifications')
def notifications_sse():
    def notify():
        user_id = session.get('user_id')
        if user_id and user_id in notifications:
            while not notifications[user_id].empty():
                yield f"data: {notifications[user_id].get()}\n\n"
    return Response(notify(), mimetype='text/event-stream')

# Schedule notification jobs
scheduler = BackgroundScheduler()
scheduler.add_job(notify_upcoming_classes, 'interval', minutes=1)
scheduler.add_job(notify_study_reminder, 'cron', hour=18)
scheduler.start()

# Ensure the scheduler stops when the application stops
atexit.register(lambda: scheduler.shutdown())



if __name__ == "__main__":
    app.run(
        debug=True, passthrough_errors=True,
        use_debugger=False, use_reloader=False
    )
