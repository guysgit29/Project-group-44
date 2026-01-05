from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
import os

# Internal Model Imports
from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager
from models.flight import Flight

app = Flask(__name__)

# --- Flask Configuration ---
# secret_key is required for secure session signing
app.secret_key = 'flytau_secret_key'

# Session configuration using local filesystem
app.config.update(
    SESSION_TYPE="filesystem",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)
Session(app)


# --- Main Routes ---

@app.route('/')
def home_page():
    """
    Renders the landing page.
    Uses Flight model to fetch distinct origins and destinations.
    """
    origins, destinations = Flight.get_all_origins_and_destinations()
    return render_template('home_page.html', origins=origins, destinations=destinations)

#
@app.route('/search')
def search_flights():
    """
    Handles flight search requests.
    """
    origin = request.args.get('origin')
    destination = request.args.get('destination')

    if not origin or not destination:
        return redirect(url_for('home_page'))

    found_flights = Flight.search(origin, destination)
    return render_template('results.html',
                           flights=found_flights,
                           origin=origin,
                           dest=destination)


@app.route('/my_flights')
def my_flights():
    """
    Displays bookings for the logged-in user.
    """
    if 'user_id' not in session:
        return redirect(url_for('login_page'))

    user_flights = Booking.get_user_flights(session['user_id'])
    return render_template('my_flights.html', flights=user_flights)


# --- Booking Management Routes ---

@app.route('/search_booking', methods=['GET', 'POST'])
def search_booking():
    """
    Retrieves a booking by ID and Email.
    Fixes AttributeError by calling the verified model method.
    """
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        email = request.form.get('email')

        booking = Booking.get_by_id_and_email(order_id, email)
        if booking:
            return redirect(url_for('manage_booking', booking_id=booking.booking_id))
        return render_template('search_booking.html', error="Booking not found.")
    return render_template('search_booking.html')


@app.route('/manage_booking/<booking_id>')
def manage_booking(booking_id):
    """
    Displays full details for a specific booking.
    """
    booking = Booking(booking_id, None, None)
    order_data, seats = booking.get_details()
    if order_data:
        return render_template('manage_booking.html', order=order_data, seats=seats)
    return redirect(url_for('home_page'))


# --- Cancellation Flow ---

@app.route('/cancel_confirm/<booking_id>')
def cancel_booking_confirm(booking_id):
    """
    Renders the confirmation page.
    Name matches 'url_for' in templates to prevent BuildError.
    """
    return render_template('cancel_confirm.html', booking_id=booking_id)


@app.route('/cancel_booking_execute/<booking_id>', methods=['POST'])
def cancel_booking_execute(booking_id):
    """Executes the cancellation in the database"""
    # שלב 1: שליפת האובייקט מה-DB
    booking = Booking.get_by_id(booking_id)

    # שלב 2: ביצוע הביטול (הלוגיקה בתוך המודל)
    if booking and booking.status != 'Canceled by Customer':
        booking.cancel()

        # שלב 3: חזרה לדף ניהול ההזמנה כדי לראות את הסטטוס המעודכן
    return redirect(url_for('manage_booking', booking_id=booking_id))

# --- Authentication Routes ---

@app.route('/registration', methods=['GET', 'POST'])
def registration():
    """Processes new user registration."""
    if request.method == 'POST':
        user, error = RegisteredUser.register(request.form)
        if error:
            return render_template('registration.html', error=error)
        return redirect(url_for('home_page'))
    return render_template('registration.html')


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    """Authenticates users and sets session roles."""
    if request.method == 'POST':
        uid = request.form.get('username')
        pwd = request.form.get('password')

        user = Manager.login(uid, pwd) or RegisteredUser.login(uid, pwd)
        if user:
            session['user_id'] = getattr(user, 'id', getattr(user, 'email', None))
            session['role'] = 'manager' if isinstance(user, Manager) else 'customer'
            return redirect(url_for('home_page'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Clears user session."""
    session.clear()
    return redirect(url_for('home_page'))


if __name__ == '__main__':
    app.run(debug=True)