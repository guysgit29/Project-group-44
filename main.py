from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import mysql.connector
import os
from contextlib import contextmanager
from utills import *

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


# --- זה קטע חדש שהוספתי ---
@app.route('/search')
def search_flights():
    origin = request.args.get('origin')
    destination = request.args.get('destination')

    try:
        with db_cur() as cursor:
            # שליפת טיסות לפי מקור ויעד
            query = "SELECT * FROM Flight WHERE origin = %s AND destination = %s ORDER BY departure_time ASC"
            cursor.execute(query, (origin, destination))
            found_flights = cursor.fetchall()

            # שליחה ל-results.html
            return render_template('results.html', flights=found_flights, origin=origin, dest=destination)

    except Exception as e:
        return "Error searching flights"


@app.route('/my-flights')
def my_flights_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_email = session['user_id']

    try:
        with db_cur() as cursor:
            # שאילתה חכמה שמחברת טיסה להזמנה
            query = """
                SELECT F.*, B.booking_id, B.price, B.booking_status
                FROM Flight F
                JOIN Booking B ON F.flight_number = B.flight_number
                WHERE B.email = %s
            """
            cursor.execute(query, (user_email,))
            my_flights = cursor.fetchall()

            return render_template('my_flights.html', flights=my_flights)

    except Exception:
        return "Error loading flights"
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home_page'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    # אם הבקשה היא POST, זה אומר שהמשתמש לחץ על "הירשם"
    if request.method == 'POST':
        # 1. שליפת הנתונים מהשדות בטופס ה-HTML (לפי ה-name שהגדרנו)
        f_name = request.form['first_name']
        l_name = request.form['last_name']
        user_email = request.form['email']
        user_password = request.form['password']

        # 2. קריאה לפונקציה שמעדכנת את ה-DB
        create_user(f_name, l_name, user_email, user_password)

        # 3. הפניה לדף התחברות או לדף הבית
        return redirect('/')

        # אם זו בקשת GET (סתם נכנסו לדף), מציגים את הטופס
    return render_template('registration.html')




if __name__ == '__main__':
    app.run(debug=True)