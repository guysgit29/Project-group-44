from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import os

# ייבוא מהקבצים החדשים שלך
from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager

app = Flask(__name__)

# הגדרת Secret Key חיונית לעבודה עם Session
app.secret_key = 'flytau_secret_key'

# הגדרות Session
app.config.update(
    SESSION_TYPE="filesystem",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)
Session(app)

@app.route('/')
def home_page():
    with DB.get_cursor() as cursor:
        cursor.execute("SELECT DISTINCT origin FROM Flight ORDER BY origin ASC")
        origins = cursor.fetchall()
        cursor.execute("SELECT DISTINCT destination FROM Flight ORDER BY destination ASC")
        destinations = cursor.fetchall()
    return render_template('home_page.html', origins=origins, destinations=destinations)

@app.route('/search_booking', methods=['GET', 'POST'])
def search_booking():
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        email = request.form.get('email')
        booking = Booking.get_by_id_and_email(order_id, email)
        if booking:
            return redirect(url_for('manage_booking', booking_id=booking.booking_id))
        return render_template('search_booking.html', error="הזמנה לא נמצאה.")
    return render_template('search_booking.html')

@app.route('/manage_booking/<booking_id>')
def manage_booking(booking_id):
    booking = Booking(booking_id, None, None, None)
    order_data, seats = booking.get_details()
    if order_data:
        return render_template('manage_booking.html', order=order_data, seats=seats)
    return redirect('/')

# --- כאן התיקון: הפונקציה שהייתה חסרה וגרמה ל-BuildError ---
@app.route('/cancel_booking_confirm/<booking_id>')
def cancel_booking_confirm(booking_id):
    """דף המבקש אישור סופי מהמשתמש לפני ביטול"""
    return render_template('cancel_confirm.html', booking_id=booking_id)

@app.route('/cancel_booking_execute/<booking_id>', methods=['POST'])
def cancel_booking_execute(booking_id):
    with DB.get_cursor() as cursor:
        cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
        booking = Booking.from_db(cursor.fetchone())

    if booking and booking.status != 'Canceled by Customer':
        booking.cancel() # ביצוע הביטול בפועל דרך המודל
    return redirect(url_for('manage_booking', booking_id=booking_id))

@app.route('/registration', methods=['GET', 'POST'])
def registration():
    if request.method == 'POST':
        user = RegisteredUser(
            request.form.get('email'),
            request.form.get('first_name'),
            request.form.get('last_name'),
            request.form.get('password'),
            request.form.get('birth_date'),
            request.form.get('passport_number')
        )
        user.save()
        return redirect('/')
    return render_template('registration.html')

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        uid, pwd = request.form.get('username'), request.form.get('password')
        user = Manager.login(uid, pwd) or RegisteredUser.login(uid, pwd)
        if user:
            session['user_id'] = getattr(user, 'id', getattr(user, 'email', None))
            session['role'] = 'manager' if isinstance(user, Manager) else 'customer'
            return redirect(url_for('home_page'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home_page'))

if __name__ == '__main__':
    app.run(debug=True)