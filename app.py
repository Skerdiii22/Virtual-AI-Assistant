from flask_bcrypt import Bcrypt
from flask import Flask,render_template,request,jsonify
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


os.environ["OPENCV_AVFOUNDATION_SKIP_AUTH"] = "1"
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app)
app.config['DEBUG'] = True

# Generate a random secret key
secret_key = secrets.token_hex(24)
app.secret_key = secret_key
bcrypt = Bcrypt(app)

# Establish MySQL database connection
database_connection = mysql.connector.connect(
    host="localhost",
    port=3306,
    user="root",
    password="",  # MySQL password
    database="Thesis"
)

# Create a cursor object to execute SQL queries
cursor = database_connection.cursor()

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
        # Call the take_attendance function
        result = take_attendance(user_id)
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

        print(f"Starting attendance with latitude: {latitude}, longitude: {longitude}, user_id: {user_id}")  # Debugging line
        result = attendance_taker.take_attendance(latitude, longitude, user_id)
        return jsonify({"message": "Attendance process completed", "result": result}), 200
    except Exception as e:
        print(f"Error in /start_attendance: {e}")  # Debugging line
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(
        debug=True, passthrough_errors=True,
        use_debugger=False, use_reloader=False
    )
