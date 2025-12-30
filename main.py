from flask import Flask, render_template, request, redirect, session
from flask_session import Session
from datetime import timedelta, date

app = Flask(__name__)

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR="/flask_session_data",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=10),
    SESSION_REFRESH_EACH_REQUEST=True,
    SESSION_COOKIE_SECURE=True
)

Session(app)


@app.route('/')
def home_page():
    # Renders the main landing page for guests and users
    return render_template('home_page.html')

@app.route('/login')
def login_page():
    # Managers login with ID, Customers with Email [cite: 16, 80]
    return render_template('client_login_page.html')

@app.route('/register')
def registration():
    # Interface for new customers to sign up [cite: 79, 80]
    return render_template('registration.html')

if __name__ == '__main__':
    app.run(debug=True)