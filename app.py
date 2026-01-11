from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta

from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager
from models.flight import Flight

app = Flask(__name__)

# --- Flask Configuration ---
app.secret_key = 'flytau_secret_key'

app.config.update(
    SESSION_TYPE="filesystem",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)
Session(app)

# --- Main Routes ---

@app.route('/')
def home_page():
    """Landing page with search dropdowns."""
    origins, destinations = Flight.get_all_origins_and_destinations()
    return render_template('home_page.html', origins=origins, destinations=destinations)

#
@app.route('/search')
def search_flights():
    """Flight search."""
    origin = request.args.get('origin')
    destination = request.args.get('destination')

    if not origin or not destination:
        return redirect(url_for('home_page'))

    found_flights = Flight.search(origin, destination)
    return render_template('results.html', flights=found_flights, origin=origin, dest=destination)


@app.route('/my_flights')
def my_flights():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    Booking.sync_past_bookings()
    all_bookings = Booking.get_user_flights(session['user_id'])
    from datetime import datetime
    now = datetime.now()
    active_bookings = []
    history_bookings = []
    for b in all_bookings:
        if b['departure_time'] > now and b['booking_status'] == 'Active':
            active_bookings.append(b)
        else:
            history_bookings.append(b)
    return render_template('my_flights.html',
                           active=active_bookings,
                           history=history_bookings)

# --- Booking Management Routes ---

@app.route('/search_booking', methods=['GET', 'POST'])
def search_booking():
    """Find booking by id + email."""
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
    """Booking details page."""
    booking = Booking(booking_id, None, None)
    order_data, seats = booking.get_details()
    if order_data:
        return render_template('manage_booking.html', order=order_data, seats=seats)
    return redirect(url_for('home_page'))

# --- Cancellation Flow ---

@app.route('/cancel_confirm/<booking_id>')
def cancel_booking_confirm(booking_id):
    """Cancel confirmation page."""
    return render_template('cancel_confirm.html', booking_id=booking_id)


@app.route('/cancel_booking_execute/<booking_id>', methods=['POST'])
def cancel_booking_execute(booking_id):
    """Executes cancellation."""
    booking = Booking.get_by_id(booking_id)
    if booking and booking.status != 'Canceled by Customer':
        booking.cancel()
    return redirect(url_for('manage_booking', booking_id=booking_id))

# --- Authentication Routes ---

@app.route('/registration', methods=['GET', 'POST'])
@app.route('/registration', methods=['GET', 'POST'])
def registration():
    # מאיפה המשתמש הגיע (למשל מה-checkout)
    next_url = request.args.get("next") if request.method == "GET" else request.form.get("next")

    if request.method == 'POST':
        user, error = RegisteredUser.register(request.form)

        if error:
            return render_template('registration.html', error=error, next=next_url)

        session['user_id'] = user.email
        session['role'] = 'customer'

        if next_url:
            return redirect(next_url)

        return redirect(url_for('home_page'))

    return render_template('registration.html', next=next_url)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'GET':
        next_url = request.args.get("next")
        return render_template("login.html", error=None, next=next_url)

    # POST
    email = request.form.get("username")
    pwd = request.form.get("password")
    next_url = request.form.get("next")

    user = RegisteredUser.login(email, pwd)
    if user:
        session["user_id"] = user.email
        session["role"] = "customer"

        # אם הגיע מ־checkout — חזור לשם
        if next_url:
            return redirect(next_url)

        # אחרת רגיל
        return redirect(url_for("home_page"))

    return render_template("login.html", error="Invalid Email or Password", next=next_url)

@app.route('/logout')
def logout():
    """Logout."""
    session.clear()
    return redirect(url_for('home_page'))

# --- Seat Selection + Pricing ---

@app.route('/seat_selection/<flight_id>')
def seat_selection(flight_id):
    flight_id_int = int(flight_id)
    seats = Flight.get_seat_map(flight_id_int)

    # Dynamic columns/rows from actual data
    max_col = 0
    max_row = 0
    if seats:
        max_col = max(int(s["column_number"]) for s in seats)
        max_row = max(int(s["row_num"]) for s in seats)

    return render_template(
        "seat_selection.html",
        flight_number=flight_id_int,
        all_seats=seats,
        max_col=max_col,
        max_row=max_row
    )

@app.route('/process_booking', methods=['POST'])
def process_booking():
    """
    Calculates total price by class_type per selected seat.
    No Seat.seat_number/base_price usage.
    """
    flight_num = request.form.get('flight_number')
    selected_seats = request.form.getlist('selected_seats')  # e.g. Economy-2-3

    if not selected_seats:
        return redirect(url_for('seat_selection', flight_id=flight_num))

    # Recommended: keep the user's choices for the checkout step as well
    session["flight_number"] = flight_num
    session["selected_seats"] = selected_seats

    total_price = 0.0
    details = []

    with DB.get_cursor() as cursor:
        for seat_str in selected_seats:
            class_type, row_num, col_num = seat_str.split('-')

            cursor.execute(
                """
                SELECT class_price
                FROM Classes_on_Flights
                WHERE flight_number = %s AND class_type = %s
                """,
                (int(flight_num), class_type)
            )
            res = cursor.fetchone()
            price = float(res["class_price"]) if res and res["class_price"] is not None else 0.0

            total_price += price
            details.append({
                "seat": f"{row_num}{col_num}",
                "class": class_type,
                "price": price
            })

    return render_template(
        'payment_summary.html',
        details=details,
        total=total_price,
        flight_number=flight_num,
        selected_seats=selected_seats   # REQUIRED for the updated payment_summary.html
    )

@app.route("/manager_login", methods=["GET", "POST"])
def manager_login():
    if request.method == "POST":
        emp_id_raw = request.form.get("id", "")
        password = request.form.get("password", "")

        emp_id_raw = emp_id_raw.strip()
        password = password.strip()

        if not emp_id_raw.isdigit():
            return render_template("manager_login.html", error="תעודת עובד חייבת להיות מספר")

        emp_id = int(emp_id_raw)

        manager = Manager.login(emp_id, password)
        if manager:
            session["user_id"] = manager.id
            session["role"] = "manager"
            session["first_name"] = manager.first_name_he
            session["last_name"] = manager.last_name_he
            return redirect("/manager_dashboard")

        return render_template("manager_login.html", error="תעודת עובד או סיסמה שגויים")

    return render_template("manager_login.html")

@app.route("/manager_dashboard")
def manager_dashboard():
    # הגנה: רק מנהל יכול להיכנס
    if session.get("role") != "manager":
        return redirect("/manager_login")

    return render_template("manager_dashboard.html")
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # GET: מגיע עם querystring: ?flight_number=1360&selected_seats=...
    # POST: מגיע מהטופס עם hidden inputs
    flight_number = (
        request.form.get("flight_number")
        if request.method == "POST"
        else request.args.get("flight_number")
    )

    selected_seats = (
        request.form.getlist("selected_seats")
        if request.method == "POST"
        else request.args.getlist("selected_seats")
    )

    if not flight_number or not selected_seats:
        return redirect(url_for("home_page"))

    flight_id = int(flight_number)
    details, total = Booking.get_pricing_for_selected_seats(flight_id, selected_seats)

    # ---- prefill + lock all fields when logged in ----
    prefill = {"first_name": "", "last_name": "", "email": "", "lock_fields": False}

    if session.get("role") == "customer" and session.get("user_id"):
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT email, first_name_en, last_name_en
                FROM RegisteredUser
                WHERE email = %s
                """,
                (session["user_id"],),
            )
            row = cursor.fetchone()

        if row:
            prefill["first_name"] = row.get("first_name_en", "") or ""
            prefill["last_name"] = row.get("last_name_en", "") or ""
            prefill["email"] = row.get("email", "") or session["user_id"]
            prefill["lock_fields"] = True

    if request.method == "GET":
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill=prefill,
            error=None,
        )

    # POST
    # אם נעול (מחובר) — אל תסמוך על מה שהגיע מהטופס, תיקח מה-prefill
    lock = prefill["lock_fields"]
    first_name = prefill["first_name"] if lock else (request.form.get("first_name") or "").strip()
    last_name  = prefill["last_name"]  if lock else (request.form.get("last_name") or "").strip()
    email      = prefill["email"]      if lock else (request.form.get("email") or "").strip().lower()

    payment_method = request.form.get("payment_method") or "card"

    # Guest מנסה להזמין עם מייל רשום
    if session.get("role") != "customer" and RegisteredUser.email_exists(email):
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={"first_name": first_name, "last_name": last_name, "email": email, "lock_fields": False},
            error="עליך להתחבר לחשבונך כדי לבצע הזמנה עם כתובת מייל זו",
        )

    created_id = Booking.create_booking_with_tickets(
        flight_number=flight_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        selected_seats=selected_seats,
        payment_method=payment_method,
        logged_in_registered=(session.get("role") == "customer"),
    )

    if not created_id:
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={"first_name": first_name, "last_name": last_name, "email": email, "lock_fields": False},
            error="לא ניתן להשלים הזמנה. ייתכן שמושב נתפס או שיש חוסר התאמה בנתוני מושבים לטיסה.",
        )

    return redirect(url_for("order_confirmation", booking_id=created_id))

@app.route("/order_confirmation/<booking_id>")
def order_confirmation(booking_id):
    booking = Booking(booking_id, None, None)
    order_data, seats = booking.get_details()

    if not order_data:
        return redirect(url_for("home_page"))

    return render_template("order_confirmation.html", order=order_data, seats=seats)
if __name__ == '__main__':
    app.run(debug=True)