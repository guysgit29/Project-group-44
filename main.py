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
        password='12345678', # Enter your MySQL password here
        database='GuyEylat$default',
        autocommit=True
    )
    return connection

@app.route('/')
def home_page():
    return render_template('home_page.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        # Authentication logic will go here
        pass
    return render_template('client_login_page.html')

@app.route('/register')
def registration():
    return render_template('registration.html')

if __name__ == '__main__':
    app.run(debug=True)