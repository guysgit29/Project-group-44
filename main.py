from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import mysql.connector
import os
from contextlib import contextmanager

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
        host='GuyEylat.mysql.pythonanywhere-services.com',
        user='GuyEylat',
        password='GROUP044',
        database='GuyEylat$default',
        autocommit=True
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
            password="root",  # הסיסמה שלך
            database="flytau",  # שם הדאטה בייס המקומי
            autocommit=True
        )
        # הוספתי כאן dictionary=True כדי שהתוצאות יחזרו כמילון
        # זה קריטי כדי שה-HTML (item.code) יעבוד תקין
        cursor = mydb.cursor(dictionary=True)
        yield cursor

    except mysql.connector.Error as err:
        # במקרה של שגיאה, נזרוק אותה כדי שנוכל לתפוס אותה ב-Route
        raise err

    finally:
        if cursor:
            cursor.close()
        if mydb:
            mydb.close()


# --- דף הבית ---
@app.route('/')
def home_page():
    # משתנים שיכילו את הרשימות
    origins_list = []
    destinations_list = []

    try:
        with db_cur() as cursor:
            # 1. שליפת רשימת המקורות (רק איפה שיש טיסות יוצאות)
            query_origins = "SELECT DISTINCT origin FROM Flight ORDER BY origin ASC"
            cursor.execute(query_origins)
            origins_list = cursor.fetchall()
            # יחזיר רשימה כזו: [{'origin': 'TLV'}, {'origin': 'JFK'}...]

            # 2. שליפת רשימת היעדים (רק איפה שיש טיסות נכנסות)
            query_destinations = "SELECT DISTINCT destination FROM Flight ORDER BY destination ASC"
            cursor.execute(query_destinations)
            destinations_list = cursor.fetchall()
            # יחזיר רשימה כזו: [{'destination': 'LHR'}, {'destination': 'CDG'}...]

        print("Loaded origins and destinations from Local DB")

    except Exception as e:
        print(f"Error connecting to Local DB: {e}")

    # אנחנו שולחים את שתי הרשימות בנפרד ל-HTML
    return render_template('home_page.html',
                           origins=origins_list,
                           destinations=destinations_list)


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