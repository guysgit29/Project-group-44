from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import mysql.connector
import os
from contextlib import contextmanager

app = Flask(__name__)

# הגדרות Session לעבודה לוקאלית
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

@contextmanager
def db_cur():
    mydb = None
    cursor = None
    try:
        mydb = mysql.connector.connect(
            host="localhost",
            user="root",
            password="rootroot", # הסיסמה המעודכנת שלך
            database="flytau",
            autocommit=True
        )
        cursor = mydb.cursor(dictionary=True)
        yield cursor
    except mysql.connector.Error as err:
        raise err
    finally:
        if cursor: cursor.close()
        if mydb: mydb.close()

# --- דף הבית ---
@app.route('/')
def home_page():
    origins_list = []
    destinations_list = []
    try:
        with db_cur() as cursor:
            cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
            origins_list = cursor.fetchall()
            cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
            destinations_list = cursor.fetchall()
        print("Loaded origins and destinations from Local DB")
    except Exception as e:
        print(f"Error connecting to Local DB: {e}")

    return render_template('home_page.html', origins=origins_list, destinations=destinations_list)

# --- דף התחברות ---
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        login_input = request.form.get('username')
        password_input = request.form.get('password')

        # שימוש ב-db_cur כדי למנוע OperationalError לוקאלית
        try:
            with db_cur() as cursor:
                # 1. בדיקה אם מנהל
                cursor.execute("SELECT * FROM Manager WHERE id = %s AND password = %s", (login_input, password_input))
                manager = cursor.fetchone()
                if manager:
                    session['user_id'] = manager['id']
                    session['role'] = 'manager'
                    return redirect(url_for('home_page'))

                # 2. בדיקה אם לקוח רשום
                cursor.execute("SELECT * FROM RegisteredUser WHERE email = %s AND password = %s", (login_input, password_input))
                customer = cursor.fetchone()
                if customer:
                    session['user_id'] = customer['email']
                    session['role'] = 'customer'
                    return redirect(url_for('home_page'))

            return render_template('client_login_page.html', error="Invalid ID/Email or Password")
        except Exception as e:
            print(f"Login error: {e}")
            return render_template('client_login_page.html', error="Connection Error")

    return render_template('client_login_page.html')

# --- דף חיפוש הזמנה פעילה (פותר את ה-BuildError) ---
@app.route('/search_order')
def search_order():
    # בשלב זה מחזיר טקסט כדי שלא תהיה שגיאה בטעינת דף הבית
    return "דף חיפוש הזמנה פעילה - בבנייה"

@app.route('/register')
def registration():
    return render_template('registration.html')

if __name__ == '__main__':
    app.run(debug=True)