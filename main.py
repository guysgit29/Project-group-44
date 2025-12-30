from flask import Flask, render_template, request, redirect, session
from flask_session import Session
from datetime import timedelta, date
from contextlib import contextmanager
import mysql.connector

app = Flask(__name__)

def get_db_connection():
    connection = mysql.connector.connect(
        host='guyeylat.mysql.pythonanywhere-services.com',
        user='guyeylat',
        password='12345678',
        database='guyeylat$flytau'
    )
    return connection

@contextmanager
def db_cur():
    mydb = None
    cursor = None
    try:
        mydb = mysql.connector.connect(
            host="localhost",
            user="root",
            password="root",
            database="",
            autocommit=True
        )
        cursor = mydb.cursor()
        yield cursor

    except mysql.connector.Error as err:
        raise err

    finally:
        if cursor:
            cursor.close()
        if mydb:
            mydb.close()


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
    print("hello")