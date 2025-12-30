from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import mysql.connector
import os

app = Flask(__name__)

# Session configuration for PythonAnywhere
# Using a local folder for session storage
session_dir = os.path.join(os.getcwd(), 'flask_session_data')
if not os.path.exists(session_dir):
    os.makedirs(session_dir)

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=session_dir,
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_REFRESH_EACH_REQUEST=True
)
Session(app)

def get_db_connection():
    connection = mysql.connector.connect(
        host='guyeylat.mysql.pythonanywhere-services.com',
        user='GuyEylat',
        password='', # Enter your MySQL password here
        database='GuyEylat$default',
        autocommit=True
    )
    return connection


@app.route('/')
def home_page():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT DISTINCT origin FROM FlightLength")
    origins = cursor.fetchall()

    cursor.execute("SELECT DISTINCT destination FROM FlightLength")
    destinations = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('home_page.html', origins=origins, destinations=destinations)


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        # Get data from the form
        login_input = request.form.get('username')  # Can be Email or ID
        password_input = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Check if the user is a Manager (Login by ID)
        cursor.execute("SELECT * FROM Manager WHERE id = %s AND password = %s", (login_input, password_input))
        manager = cursor.fetchone()

        if manager:
            session['user_id'] = manager['id']
            session['role'] = 'manager'
            cursor.close()
            conn.close()
            return redirect(url_for('manager_dashboard'))  # Create this route later

        # 2. Check if the user is a Registered Customer (Login by Email)
        cursor.execute("SELECT * FROM RegisteredUser WHERE email = %s AND password = %s", (login_input, password_input))
        customer = cursor.fetchone()

        cursor.close()
        conn.close()

        if customer:
            session['user_id'] = customer['email']
            session['role'] = 'customer'
            return redirect(url_for('home_page'))

        # If login failed
        return render_template('client_login_page.html', error="Invalid ID/Email or Password")

    return render_template('client_login_page.html')

@app.route('/register')
def registration():
    return render_template('registration.html')

if __name__ == '__main__':
    app.run(debug=True)