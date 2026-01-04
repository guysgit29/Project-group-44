from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import os

# ייבוא הצינורות לבסיס הנתונים
from utills import db_cur

# ייבוא המחלקות שיצרנו בתיקיית models
from models.customers import RegisteredUser
from models.employees import Manager
from models.flights import Flight
from models.booking import Booking

app = Flask(__name__)

# הגדרות Session (נשאר כפי שהיה לך)
session_dir = os.path.join(os.getcwd(), 'flask_session_data')
if not os.path.exists(session_dir):
    os.makedirs(session_dir)

app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=session_dir,
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
    SESSION_REFRESH_EACH_REQUEST=True,
    SECRET_KEY="fly_tau_super_secret"
)
Session(app)


# --- דף הבית ---
@app.route('/')
def home_page():
    with db_cur() as cursor:
        cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
        origins = cursor.fetchall()
        cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
        destinations = cursor.fetchall()
    return render_template('home_page.html', origins=origins, destinations=destinations)


# --- התחברות (לוגיקה משולבת למנהל ולקוח) ---
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        login_input = request.form.get('username')
        password_input = request.form.get('password')

        with db_cur() as cursor:
            # 1. בדיקה אם מנהל (חיבור טבלאות עובד ומנהל)
            query_mgr = """
                SELECT E.*, M.password 
                FROM Employee E JOIN Manager M ON E.id = M.id 
                WHERE E.id = %s AND M.password = %s
            """
            cursor.execute(query_mgr, (login_input, password_input))
            mgr_row = cursor.fetchone()
            manager = Manager.from_db(mgr_row)

            if manager:
                session['user_id'] = manager.id
                session['role'] = 'manager'
                session['name'] = manager.first_name
                return redirect(url_for('home_page'))

            # 2. בדיקה אם לקוח רשום
            cursor.execute("SELECT * FROM RegisteredUser WHERE email = %s AND password = %s",
                           (login_input, password_input))
            user_row = cursor.fetchone()
            user = RegisteredUser.from_db(user_row)

            if user:
                session['user_id'] = user.email
                session['role'] = 'customer'
                session['name'] = user.first_name
                return redirect(url_for('home_page'))

        return render_template('login.html', error="Invalid ID/Email or Password")
    return render_template('login.html')


# --- חיפוש טיסות ---
@app.route('/search')
def search_flights():
    origin = request.args.get('origin')
    dest = request.args.get('destination')

    if not origin or not dest:
        return redirect(url_for('home_page'))

    with db_cur() as cursor:
        query = "SELECT * FROM Flight WHERE origin = %s AND destination = %s ORDER BY departure_time ASC"
        cursor.execute(query, (origin, dest))
        rows = cursor.fetchall()
        # הפיכת כל שורה מה-DB לאובייקט Flight
        found_flights = [Flight.from_db(row) for row in rows]

    return render_template('results.html', flights=found_flights, origin=origin, dest=dest)


# --- הרשמה ---
@app.route('/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        # יצירת אובייקט משתמש חדש
        new_user = RegisteredUser(
            email=request.form.get('email').strip().lower(),
            first_name_en=request.form.get('first_name'),
            last_name_en=request.form.get('last_name'),
            password=request.form.get('password'),
            birth_date=request.form.get('birth_date'),
            passport=request.form.get('passport_number')
        )

        try:
            new_user.save()  # המתודה שכתבנו בתוך המחלקה
            return redirect(url_for('home_page'))
        except Exception as e:
            return render_template('registration.html', error="Registration failed.")

    return render_template('registration.html')


# --- ניהול הזמנה ---
@app.route('/search_booking', methods=['GET', 'POST'])
def search_booking():
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        email = request.form.get('email')

        with db_cur() as cursor:
            query = "SELECT * FROM Booking WHERE booking_id = %s AND (registered_email = %s OR guest_email = %s)"
            cursor.execute(query, (order_id, email, email))
            row = cursor.fetchone()
            booking = Booking.from_db(row)

            if booking:
                return redirect(url_for('manage_booking', booking_id=booking.booking_id))
            return render_template('search_booking.html', error="Booking not found.")

    return render_template('search_booking.html')


@app.route('/manage_booking/<booking_id>')
def manage_booking(booking_id):
    with db_cur() as cursor:
        # שליפת פרטי הזמנה
        cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
        booking = Booking.from_db(cursor.fetchone())

        # שליפת מושבים לכרטיס
        cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (booking_id,))
        tickets = cursor.fetchall()

    return render_template('manage_booking.html', booking=booking, tickets=tickets)


# --- ביטול הזמנה (שימוש בלוגיקה בתוך ה-Model) ---
@app.route('/cancel_booking_execute/<booking_id>', methods=['POST'])
def cancel_booking_execute(booking_id):
    with db_cur() as cursor:
        cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
        booking = Booking.from_db(cursor.fetchone())

        if booking and booking.status != 'Canceled by Customer':
            booking.cancel()  # כאן קורית כל הלוגיקה של ה-5% ומחיקת המושבים

    return redirect(url_for('manage_booking', booking_id=booking_id))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home_page'))


if __name__ == '__main__':
    app.run(debug=True)