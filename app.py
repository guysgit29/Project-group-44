from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import mysql.connector
import os
from contextlib import contextmanager
from utills import *
#
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
    except Exception as e:
        print(f"Error connecting to Local DB: {e}")

    return render_template('home_page.html', origins=origins_list, destinations=destinations_list)
# --- דף התחברות ---
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        login_input = request.form.get('username')
        password_input = request.form.get('password')
        123123123123123

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

            return render_template('login.html', error="Invalid ID/Email or Password")
        except Exception as e:
            print(f"Login error: {e}")
            return render_template('login.html', error="Connection Error")

    return render_template('login.html')


@app.route('/search')
def search_flights():
    origin = request.args.get('origin')
    destination = request.args.get('destination')

    # אם המשתמש נכנס סתם לדף בלי פרמטרים
    if not origin or not destination:
        return redirect(url_for('home_page'))

    found_flights = []
    try:
        with db_cur() as cursor:
            # שליפת טיסות לפי מקור ויעד (ללא תאריך)
            query = """
                SELECT * FROM Flight 
                WHERE origin = %s AND destination = %s 
                ORDER BY departure_time ASC
            """
            cursor.execute(query, (origin, destination))
            found_flights = cursor.fetchall()
    except Exception as e:
        print(f"Search Error: {e}")

    return render_template('results.html',
                           flights=found_flights,
                           origin=origin,
                           dest=destination)

@app.route('/my-flights')
def my_flights_page():
    # בדיקה אם המשתמש מחובר
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_email = session['user_id']
    my_flights = []

    try:
        with db_cur() as cursor:
            # שליפת נתונים מטבלת Booking ו-Flight
            query = """
                SELECT 
                    F.flight_number, 
                    F.origin, 
                    F.destination, 
                    F.departure_time, 
                    B.booking_id, 
                    B.price, 
                    B.booking_status
                FROM Flight F
                JOIN Booking B ON F.flight_number = B.flight_number
                WHERE B.email = %s
                ORDER BY F.departure_time ASC
            """
            cursor.execute(query, (user_email,))
            my_flights = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching user flights: {e}")

    return render_template('my_flights.html', flights=my_flights)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home_page'))


@app.route('/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        f_name = request.form.get('first_name', '')
        l_name = request.form.get('last_name', '')
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        birth_date = request.form.get('birth_date', '')
        passport = request.form.get('passport_number', '')

        if password != confirm_password:
            return render_template('registration.html', error="Passwords do not match.")

        try:
            with db_cur() as cursor:
                cursor.execute(
                    "SELECT 1 FROM RegisteredUser WHERE email = %s",
                    (email,)
                )
                if cursor.fetchone():
                    return render_template(
                        'registration.html',
                        error="Email already registered."
                    )
        except Exception as e:
            print(f"DB error: {e}")
            return render_template('registration.html', error="Database error.")

        create_user(f_name, l_name, email, password, birth_date, passport)
        return redirect('/')

    return render_template('registration.html')

@app.route('/search_booking', methods=['GET', 'POST'])
def search_booking():
    if request.method == 'POST':
        order_input = request.form.get('order_id')
        email_input = request.form.get('email')

        try:
            with db_cur() as cursor:
                # התיקון: בדיקה מול שתי עמודות האימייל הקיימות ב-SQL שלך
                query = """
                    SELECT booking_id FROM Booking 
                    WHERE booking_id = %s 
                    AND (registered_email = %s OR guest_email = %s)
                """
                cursor.execute(query, (order_input, email_input, email_input))
                order = cursor.fetchone()

                if order:
                    # שימוש בפורמט dict כי ה-cursor מוגדר כ-dictionary=True
                    return redirect(url_for('manage_booking', booking_id=order['booking_id']))
                else:
                    return render_template('search_booking.html', error="הזמנה לא נמצאה, אנא נסה שוב או פנה אל שירות הלקוחות.")
        except Exception as e:
            print(f"Database Error: {e}")
            return render_template('search_booking.html', error="שגיאה בחיבור לבסיס הנתונים.")

    return render_template('search_booking.html')

@app.route('/manage_booking/<booking_id>')
def manage_booking(booking_id):
    try:
        with db_cur() as cursor:
            # שליפת פרטי הזמנה (נשאר אותו דבר)
            query = """
                SELECT b.*, f.origin, f.destination, f.departure_time, f.arrival_time, f.flight_status
                FROM Booking b
                JOIN Flight f ON b.flight_number = f.flight_number
                WHERE b.booking_id = %s
            """
            cursor.execute(query, (booking_id,))
            order_data = cursor.fetchone()

            # התיקון: שליפת מושבים מטבלת Ticket במקום Seats_in_Booking
            cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (booking_id,))
            seats_data = cursor.fetchall()

        if order_data:
            return render_template('manage_booking.html', order=order_data, seats=seats_data)
        return redirect('/')
    except Exception as e:
        print(f"Error: {e}")
        return "שגיאה בטעינת נתונים"


@app.route('/cancel_booking_confirm/<booking_id>')
def cancel_booking_confirm(booking_id):
    # רק מציג את דף האישור עם מספר ההזמנה
    return render_template('cancel_confirm.html', booking_id=booking_id)


@app.route('/cancel_booking_execute/<booking_id>', methods=['POST'])
def cancel_booking_execute(booking_id):
    try:
        with db_cur() as cursor:
            # שלב א': בדיקה שההזמנה עדיין לא בוטלה (כדי לא לחלק את המחיר ב-20 פעם שנייה)
            cursor.execute("SELECT booking_status FROM Booking WHERE booking_id = %s", (booking_id,))
            current_status = cursor.fetchone()

            if current_status and current_status['booking_status'] == 'Canceled by Customer':
                print(f"Booking {booking_id} is already canceled.")
                return redirect(url_for('manage_booking', booking_id=booking_id))

            # שלב ב': מחיקת המושבים מטבלת Ticket
            # זה משחרר את המושבים פיזית מההזמנה בבסיס הנתונים
            cursor.execute("DELETE FROM Ticket WHERE booking_id = %s", (booking_id,))

            # שלב ג': עדכון הסטטוס והמחיר ל-5% (חלקי 20)
            query = """
                UPDATE Booking 
                SET booking_status = 'Canceled by Customer',
                    price = price / 20
                WHERE booking_id = %s
            """
            cursor.execute(query, (booking_id,))

        print(f"Booking {booking_id} canceled successfully: price reduced to 5% and seats released.")
        return redirect(url_for('manage_booking', booking_id=booking_id))

    except Exception as e:
        # הדפסת השגיאה המדויקת לטרמינל לצרכי Debugging
        print(f"Error during cancellation process: {e}")
        return "חלה שגיאה בעדכון הביטול במסד הנתונים."

if __name__ == '__main__':
    app.run(debug=True)