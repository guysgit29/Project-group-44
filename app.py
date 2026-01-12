from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_session import Session
from datetime import timedelta,datetime
from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager,Pilot,FlightAttendant
from models.flight import Flight
#
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

    # אם מחובר מנהל – לעבור ישר לדשבורד שלו
    if session.get("role") == "manager":
        return redirect(url_for("manager_dashboard"))

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

    active_bookings, history_bookings = Booking.get_user_flights_split(session['user_id'])

    return render_template(
        'my_flights.html',
        active=active_bookings,
        history=history_bookings
    )
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



# ------------------------------------------------------------
# Manage booking
# ------------------------------------------------------------
@app.route('/manage_booking/<booking_id>')
def manage_booking(booking_id):
    booking = Booking(booking_id, None, None)
    order_data, seats = booking.get_details()

    if not order_data:
        return redirect(url_for('home_page'))

    # --- Build full name from email (Registered or Guest) ---
    email = (order_data.get("registered_email") or order_data.get("guest_email") or "").strip().lower()
    full_name = ""

    if email:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT first_name_en, last_name_en
                FROM RegisteredUser
                WHERE email = %s
            """, (email,))
            row = cursor.fetchone()

            if not row:
                cursor.execute("""
                    SELECT first_name_en, last_name_en
                    FROM GuestUser
                    WHERE email = %s
                """, (email,))
                row = cursor.fetchone()

        if row:
            first = (row.get("first_name_en") or "").strip()
            last = (row.get("last_name_en") or "").strip()
            full_name = f"{first} {last}".strip()

    order_data["full_name"] = full_name if full_name else email

    can_cancel, show_block_message, cancel_block_reason = Booking.calc_cancel_flags(order_data)

    return render_template(
        'manage_booking.html',
        order=order_data,
        seats=seats,
        can_cancel=can_cancel,
        show_block_message=show_block_message,
        cancel_block_reason=cancel_block_reason
    )


# ------------------------------------------------------------
# Cancel confirmation page
# ------------------------------------------------------------
@app.route('/cancel_confirm/<booking_id>')
def cancel_booking_confirm(booking_id):
    booking = Booking(booking_id, None, None)
    order_data, _ = booking.get_details()

    if not order_data:
        return redirect(url_for('home_page'))

    can_cancel, _, _ = Booking.calc_cancel_flags(order_data)

    if not can_cancel:
        return redirect(url_for('manage_booking', booking_id=booking_id))

    return render_template('cancel_confirm.html', booking_id=booking_id)


# ------------------------------------------------------------
# Execute cancellation
# ------------------------------------------------------------
@app.route('/cancel_booking_execute/<booking_id>', methods=['POST'])
def cancel_booking_execute(booking_id):
    booking = Booking(booking_id, None, None)
    order_data, _ = booking.get_details()

    if not order_data:
        return redirect(url_for('home_page'))

    can_cancel, _, _ = Booking.calc_cancel_flags(order_data)

    if can_cancel:
        b = Booking.get_by_id(booking_id)
        if b and b.status != "Canceled by Customer":
            b.cancel()

    return redirect(url_for('manage_booking', booking_id=booking_id))

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

    origin = request.args.get("origin", "")
    destination = request.args.get("destination", "")

    max_col = 0
    max_row = 0
    if seats:
        max_col = max(int(s["column_number"]) for s in seats)
        max_row = max(int(s["row_num"]) for s in seats)

    return render_template(
        "seat_selection.html",
        flight_number=flight_id_int,
        origin=origin,
        destination=destination,
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
            session.permanent = True  # ✅ חשוב
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


# ================================
# app.py  (רק ה-route מחדש)
# ================================
# ================================
# app.py  (להחליף את ה-route הזה)
# ================================
@app.route("/manager_flights")
def manager_flights():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    Flight.sync_completed_flights()

    selected_status = (request.args.get("status", "") or "").strip()

    aircraft_id_raw = (request.args.get("aircraft_id", "") or "").strip()
    aircraft_id = int(aircraft_id_raw) if aircraft_id_raw.isdigit() else None

    flights = Flight.list_for_manager(selected_status, aircraft_id)

    # ✅ לרשימת בחירה כמו הסטטוס
    aircraft_ids = Flight.get_all_aircraft_ids()

    return render_template(
        "manager_flights.html",
        flights=flights,
        selected_status=selected_status,
        selected_aircraft_id=aircraft_id_raw,
        aircraft_ids=aircraft_ids
    )

# --- Checkout ---

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # GET: ?flight_number=1360&selected_seats=...
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

    # -------------------------------------------------
    # Prefill + lock when logged in
    # -------------------------------------------------
    prefill = {
        "first_name": "",
        "last_name": "",
        "email": "",
        "passport_number": "",
        "phone_number": "",
        "lock_fields": False,
    }

    logged_in_registered = (session.get("role") == "customer" and session.get("user_id"))

    if logged_in_registered:
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    RU.email,
                    RU.first_name_en,
                    RU.last_name_en,
                    RU.passport_number,
                    (
                        SELECT RP.phone_number
                        FROM RegisteredPhone RP
                        WHERE RP.email = RU.email
                        ORDER BY RP.phone_number
                        LIMIT 1
                    ) AS phone_number
                FROM RegisteredUser RU
                WHERE RU.email = %s
                LIMIT 1
                """,
                (session["user_id"],),
            )
            row = cursor.fetchone()

        if row:
            prefill["first_name"] = row.get("first_name_en", "") or ""
            prefill["last_name"] = row.get("last_name_en", "") or ""
            prefill["email"] = row.get("email", "") or session["user_id"]
            prefill["passport_number"] = row.get("passport_number", "") or ""
            prefill["phone_number"] = row.get("phone_number", "") or ""
            prefill["lock_fields"] = True

    # -------------------------------------------------
    # GET
    # -------------------------------------------------
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

    # -------------------------------------------------
    # POST
    # -------------------------------------------------
    lock = prefill["lock_fields"]

    # אם נעול (מחובר) — לא סומכים על מה שהגיע מהטופס
    first_name = prefill["first_name"] if lock else (request.form.get("first_name") or "").strip()
    last_name  = prefill["last_name"]  if lock else (request.form.get("last_name") or "").strip()
    email      = prefill["email"]      if lock else (request.form.get("email") or "").strip().lower()

    # שדות חדשים
    passport_number = prefill["passport_number"] if lock else (request.form.get("passport_number") or "").strip()
    phone_number    = prefill["phone_number"]    if lock else (request.form.get("phone_number") or "").strip()

    payment_method = request.form.get("payment_method") or "card"

    # ולידציה בסיסית
    if not first_name or not last_name or not email:
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_number": phone_number,
                "lock_fields": lock,
            },
            error="אנא מלא את כל השדות הנדרשים.",
        )

    if not phone_number:
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_number": phone_number,
                "lock_fields": lock,
            },
            error="אנא הזן מספר טלפון.",
        )

    # Guest מנסה להזמין עם מייל רשום
    if (not logged_in_registered) and RegisteredUser.email_exists(email):
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_number": phone_number,
                "lock_fields": False,
            },
            error="עליך להתחבר לחשבונך כדי לבצע הזמנה עם כתובת מייל זו",
        )

    created_id = Booking.create_booking_with_tickets(
        flight_number=flight_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        selected_seats=selected_seats,
        payment_method=payment_method,
        logged_in_registered=bool(logged_in_registered),
        phone_number=phone_number,          # חדש
        passport_number=passport_number,    # חדש (לא נשמר; רק אם תרצה לוגיקה)
    )

    if not created_id:
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_number": phone_number,
                "lock_fields": lock,
            },
            error="לא ניתן להשלים הזמנה. ייתכן שמושב נתפס או שיש חוסר התאמה בנתוני מושבים לטיסה.",
        )

    return redirect(url_for("order_confirmation", booking_id=created_id))

@app.route("/order_confirmation/<booking_id>")
def order_confirmation(booking_id):
    booking = Booking(booking_id, None, None)
    order_data, seats = booking.get_details()

    if not order_data:
        return redirect(url_for("home_page"))

    # --- Build full name from RegisteredUser / GuestUser by email ---
    email = (order_data.get("registered_email") or order_data.get("guest_email") or "").strip().lower()
    full_name = ""

    if email:
        with DB.get_cursor() as cursor:
            # try RegisteredUser first
            cursor.execute(
                """
                SELECT first_name_en, last_name_en
                FROM RegisteredUser
                WHERE email = %s
                """,
                (email,)
            )
            row = cursor.fetchone()

            # if not found -> try GuestUser
            if not row:
                cursor.execute(
                    """
                    SELECT first_name_en, last_name_en
                    FROM GuestUser
                    WHERE email = %s
                    """,
                    (email,)
                )
                row = cursor.fetchone()

        if row:
            first = (row.get("first_name_en") or "").strip()
            last = (row.get("last_name_en") or "").strip()
            full_name = f"{first} {last}".strip()

    # add field to order_data (dict) so template can use order.full_name
    order_data["full_name"] = full_name if full_name else email  # fallback: show email if name missing

    return render_template("order_confirmation.html", order=order_data, seats=seats)


# --- Manager: flight view (Completed only) ---

@app.route("/manager_flight_view/<int:flight_number>")
def manager_flight_view(flight_number):
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    # אפשר להשאיר, לא חובה. זה רק מסנכרן סטטוסים שנחתו
    Flight.sync_completed_flights()

    flight = Flight.get_by_number(flight_number)
    if not flight:
        return redirect(url_for("manager_flights"))

    # ✅ אין שום הגבלה לפי סטטוס — פורטל טיסה לכל טיסה
    aircraft = Flight.get_aircraft_by_id(flight["aircraft_id"])
    attendants = FlightAttendant.get_assigned_for_flight(flight_number)
    pilots = Pilot.get_assigned_for_flight(flight_number)

    return render_template(
        "manager_flight_view.html",
        flight=flight,
        aircraft=aircraft,
        attendants=attendants,
        pilots=pilots
    )

@app.route("/manager_flight_manage/<int:flight_number>", methods=["GET", "POST"])
def manager_flight_manage(flight_number):
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    # סנכרון טיסות שנחתו
    Flight.sync_completed_flights()

    # פרטי טיסה
    flight = Flight.get_by_number(flight_number)
    if not flight:
        return redirect(url_for("manager_flights"))

    flight["aircraft_size"] = Flight.get_aircraft_size_for_flight(flight_number)

    # טיסה שהושלמה – למסך צפייה בלבד
    if (flight.get("flight_status") or "").strip() == "Completed":
        return redirect(url_for("manager_flight_view", flight_number=flight_number))

    # --------
    # POST – שיבוץ / הסרה
    # --------
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "assign_pilot":
            pid = int(request.form.get("pilot_id"))
            ok, msg = Pilot.assign_to_flight(pid, flight_number)
            session["flash_msg"] = msg

        elif action == "remove_pilot":
            pid = int(request.form.get("pilot_id"))
            ok, msg = Pilot.remove_from_flight(pid, flight_number)
            session["flash_msg"] = msg

        elif action == "assign_attendant":
            aid = int(request.form.get("attendant_id"))
            ok, msg = FlightAttendant.assign_to_flight(aid, flight_number)
            session["flash_msg"] = msg

        elif action == "remove_attendant":
            aid = int(request.form.get("attendant_id"))
            ok, msg = FlightAttendant.remove_from_flight(aid, flight_number)
            session["flash_msg"] = msg

        return redirect(url_for("manager_flight_manage", flight_number=flight_number))

    # --------
    # GET – טעינת נתונים למסך
    # --------

    # הודעת פעולה אחרונה (אם קיימת)
    flash_msg = session.pop("flash_msg", None)

    # משובצים בפועל
    assigned_pilots = Pilot.get_assigned_for_flight(flight_number)
    assigned_attendants = FlightAttendant.get_assigned_for_flight(flight_number)

    # ✅ זמינים בלבד (כולל הסמכה + בלי חפיפה + ✅ מיקום דיפולטי TLV אם אין היסטוריה)
    all_pilots = Pilot.list_all(flight_number)
    all_attendants = FlightAttendant.list_all(flight_number)

    # חישובי נדרש / שובצו / חסר
    required = Flight.get_required_crew_counts(flight_number)

    assigned_counts = {
        "pilots": len(assigned_pilots),
        "attendants": len(assigned_attendants)
    }

    missing_counts = {
        "pilots": max(0, required["pilots"] - assigned_counts["pilots"]),
        "attendants": max(0, required["attendants"] - assigned_counts["attendants"])
    }

    return render_template(
        "manager_flight_manage.html",
        flight=flight,
        assigned_pilots=assigned_pilots,
        assigned_attendants=assigned_attendants,
        all_pilots=all_pilots,
        all_attendants=all_attendants,
        required=required,
        assigned_counts=assigned_counts,
        missing_counts=missing_counts,
        flash_msg=flash_msg
    )


@app.route("/aircrafts")
def aircrafts():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    filters = Aircraft.parse_filters(request.args)
    aircrafts, classes_map, flights_map = Aircraft.list_page_data(filters)

    return render_template(
        "aircrafts.html",
        aircrafts=aircrafts,
        classes_map=classes_map,
        flights_map=flights_map,
        filters=filters
    )


@app.route("/aircrafts/new", methods=["GET", "POST"])
def add_aircraft():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    if request.method == "GET":
        return render_template(
            "add_aircraft.html",
            manufacturers=Aircraft.MANUFACTURERS,
            error=None
        )

    pending, error = Aircraft.build_pending_from_form(request.form)
    if error:
        return render_template(
            "add_aircraft.html",
            manufacturers=Aircraft.MANUFACTURERS,
            error=error
        )

    session["pending_new_aircraft"] = pending
    return redirect(url_for("add_aircraft_confirm"))


from models.aircrafts import Aircraft

@app.route("/aircrafts/new/confirm", methods=["GET", "POST"])
def add_aircraft_confirm():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    pending = session.get("pending_new_aircraft")
    if not pending:
        return redirect(url_for("add_aircraft"))

    if request.method == "GET":
        return render_template("add_aircraft_confirm.html", a=pending)

    Aircraft.create_from_pending(pending)

    session.pop("pending_new_aircraft", None)
    flash("מטוס נוסף בהצלחה", "success")
    return redirect(url_for("aircrafts"))

from datetime import datetime
import re

def _require_manager():
    return session.get("role") == "manager"

def _draft_get():
    return session.get("new_flight_draft") or {}

def _draft_set(d: dict):
    session["new_flight_draft"] = d
    session.modified = True

def _draft_clear():
    session.pop("new_flight_draft", None)
    session.modified = True

def _parse_date_time(date_str: str, time_str: str) -> datetime | None:
    # date: YYYY-MM-DD  time: HH:MM
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception:
        return None

def _normalize_airport(s: str) -> str:
    return (s or "").strip().upper()

def _validate_time_hhmmss(t: str) -> bool:
    # HH:MM:SS
    return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}", (t or "").strip()))

@app.route("/manager_flight_create", methods=["GET", "POST"])
def manager_flight_create():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    error = None

    origins = Flight.get_route_origins_distinct()
    destinations = Flight.get_route_destinations_distinct()

    if request.method == "POST":
        origin = _normalize_airport(request.form.get("origin"))
        destination = _normalize_airport(request.form.get("destination"))
        flight_date = (request.form.get("flight_date") or "").strip()
        flight_time = (request.form.get("flight_time") or "").strip()

        dep_dt = _parse_date_time(flight_date, flight_time)
        if not origin or not destination or not dep_dt:
            error = "חובה לבחור מקור, יעד, תאריך ושעה"
        else:
            info = Flight.get_route_info(origin, destination)
            if not info:
                error = "הנתיב לא קיים ב-FlightLength. קודם הוסף קו טיסה."
            else:
                duration_sec = int(info["duration_sec"] or 0)
                require_large = duration_sec > 6 * 3600

                arr_dt = Flight.compute_arrival(dep_dt, origin, destination)

                _draft_set({
                    "origin": origin,
                    "destination": destination,
                    "departure_dt": dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "arrival_dt_preview": str(arr_dt) if arr_dt else None,
                    "duration_sec": duration_sec,
                    "require_large": require_large,
                    "aircraft_id": None,
                    "pilot_ids": [],
                    "attendant_ids": [],
                })
                return redirect(url_for("manager_assign_aircraft"))

    # GET or error
    draft = _draft_get()
    return render_template(
        "manager_flight_create_step1.html",
        error=error,
        origins=origins,
        destinations=destinations,
        prefill={
            "origin": draft.get("origin", ""),
            "destination": draft.get("destination", ""),
        }
    )

@app.route("/manager_assign_aircraft", methods=["GET", "POST"])
def manager_assign_aircraft():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get()
    if not draft.get("origin") or not draft.get("destination") or not draft.get("departure_dt"):
        return redirect(url_for("manager_flight_create"))

    origin = draft["origin"]
    dep_dt = datetime.strptime(draft["departure_dt"], "%Y-%m-%d %H:%M:%S")
    require_large = bool(draft.get("require_large"))

    aircrafts = Flight.list_available_aircrafts_for_route(origin, dep_dt, require_large)

    error = None
    if request.method == "POST":
        aircraft_id = (request.form.get("aircraft_id") or "").strip()
        if not aircraft_id:
            error = "חובה לבחור מטוס"
        else:
            draft["aircraft_id"] = int(aircraft_id)
            _draft_set(draft)
            return redirect(url_for("manager_assign_crew"))

    return render_template(
        "manager_flight_assign_aircraft.html",
        error=error,
        draft=draft,
        aircrafts=aircrafts,
        require_large=require_large
    )

@app.route("/manager_assign_crew", methods=["GET", "POST"])
def manager_assign_crew():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get()
    if not draft.get("aircraft_id"):
        return redirect(url_for("manager_assign_aircraft"))

    origin = draft["origin"]
    dep_dt = datetime.strptime(draft["departure_dt"], "%Y-%m-%d %H:%M:%S")
    require_large = bool(draft.get("require_large"))

    # כמה צריך?
    # משתמשים בלוגיקה שלך: small/large לפי aircraft_size בפועל
    aircraft_size = Flight.get_aircraft_size(int(draft["aircraft_id"]))  # שלך כבר קיים
    need = Flight.get_required_crew_counts_for_size(aircraft_size) if hasattr(Flight, "get_required_crew_counts_for_size") else None
    if not need:
        # fallback על הפונקציה שכבר יש לך (אבל היא לפי flight_number; פה אין)
        need = {"pilots": 3, "attendants": 6} if aircraft_size == "large" else {"pilots": 2, "attendants": 3}

    pilots = Flight.list_available_pilots_for_new_flight(origin, dep_dt, require_large=(aircraft_size == "large"))
    attendants = Flight.list_available_attendants_for_new_flight(origin, dep_dt, require_large=(aircraft_size == "large"))

    error = None
    if request.method == "POST":
        pilot_ids = request.form.getlist("pilot_ids")
        attendant_ids = request.form.getlist("attendant_ids")

        # enforce exact counts
        if len(pilot_ids) != int(need["pilots"]):
            error = f"חובה לבחור בדיוק {need['pilots']} טייסים"
        elif len(attendant_ids) != int(need["attendants"]):
            error = f"חובה לבחור בדיוק {need['attendants']} דיילים"
        else:
            draft["pilot_ids"] = [int(x) for x in pilot_ids]
            draft["attendant_ids"] = [int(x) for x in attendant_ids]
            _draft_set(draft)
            return redirect(url_for("manager_flight_confirm"))

    return render_template(
        "manager_flight_assign_crew.html",
        error=error,
        draft=draft,
        pilots=pilots,
        attendants=attendants,
        need=need,
        aircraft_size=aircraft_size
    )

@app.route("/manager_flight_confirm", methods=["GET", "POST"])
def manager_flight_confirm():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get()
    required_keys = ["origin", "destination", "departure_dt", "aircraft_id", "pilot_ids", "attendant_ids"]
    if any(k not in draft or draft.get(k) in (None, "", []) for k in ["origin", "destination", "departure_dt", "aircraft_id"]):
        return redirect(url_for("manager_flight_create"))

    # load preview data
    origin = draft["origin"]
    destination = draft["destination"]
    dep_dt = datetime.strptime(draft["departure_dt"], "%Y-%m-%d %H:%M:%S")
    arr_preview = draft.get("arrival_dt_preview")
    aircraft_id = int(draft["aircraft_id"])
    pilot_ids = draft.get("pilot_ids") or []
    attendant_ids = draft.get("attendant_ids") or []

    aircraft = Flight.get_aircraft_by_id(aircraft_id)
    aircraft_size = (aircraft.get("aircraft_size") or "").strip().lower() if aircraft else ""

    # validate route exists again
    info = Flight.get_route_info(origin, destination)
    if not info:
        return redirect(url_for("manage_flight_routes"))

    # final create
    error = None
    if request.method == "POST":
        flight_number = Flight.generate_next_flight_number()

        # HARD RULE: >6h requires large
        duration_sec = int(info["duration_sec"] or 0)
        if duration_sec > 6 * 3600 and aircraft_size != "large":
            error = "לא ניתן לאשר: טיסה מעל 6 שעות חייבת מטוס Large"
        else:
            # insert into Flight (trigger calculates arrival_time)
            with DB.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO Flight (flight_number, aircraft_id, origin, destination, departure_time, flight_status)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (int(flight_number), int(aircraft_id), origin, destination, dep_dt, "Active"))

                for pid in pilot_ids:
                    cursor.execute("""
                        INSERT INTO Pilots_on_Flights (id, flight_number)
                        VALUES (%s,%s)
                    """, (int(pid), int(flight_number)))

                for aid in attendant_ids:
                    cursor.execute("""
                        INSERT INTO FlightAttendants_on_Flights (id, flight_number)
                        VALUES (%s,%s)
                    """, (int(aid), int(flight_number)))

            _draft_clear()
            return redirect(url_for("manager_flight_manage", flight_number=int(flight_number)))

    return render_template(
        "manager_flight_confirm.html",
        error=error,
        draft=draft,
        flight_number_preview="(ייווצר אוטומטית באישור)",
        origin=origin,
        destination=destination,
        departure_dt=dep_dt,
        arrival_preview=arr_preview,
        aircraft=aircraft,
        pilot_ids=pilot_ids,
        attendant_ids=attendant_ids,
    )

@app.route("/manage_flight_routes", methods=["GET", "POST"])
def manage_flight_routes():
    # ---- filters (GET) ----
    filter_origin = (request.args.get("filter_origin") or "").strip()
    filter_destination = (request.args.get("filter_destination") or "").strip()

    error = None
    success = None
    add_prefill = {"origin": "", "destination": "", "length_minutes": ""}

    if request.method == "POST":
        origin = (request.form.get("origin") or "").strip()
        destination = (request.form.get("destination") or "").strip()
        length_minutes = (request.form.get("length_minutes") or "").strip()

        add_prefill = {"origin": origin, "destination": destination, "length_minutes": length_minutes}

        if not origin or not destination or not length_minutes:
            error = "נא למלא מקור, יעד ואורך טיסה"
        elif not _is_time_ok(length_minutes):
            error = "לא ניתן להוסיף: אורך טיסה חייב להיות בפורמט HH:MM או HH:MM:SS"
        else:
            # נורמליזציה: אם HH:MM -> נוסיף :00
            if re.match(r"^\d{1,2}:\d{2}$", length_minutes):
                length_minutes = length_minutes + ":00"

            try:
                with DB.get_cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO FlightLength (origin, destination, length_minutes)
                        VALUES (%s, %s, %s)
                        """,
                        (origin, destination, length_minutes),
                    )
                success = "קו טיסה נוסף בהצלחה"
                add_prefill = {"origin": "", "destination": "", "length_minutes": ""}
            except Exception as e:
                # כפילות PK (origin,destination) או בעיית DB אחרת
                error = "לא ניתן להוסיף: הקו כבר קיים או שיש שגיאה בנתונים"

    # ---- dropdown data ----
    with DB.get_cursor() as cursor:
        cursor.execute("SELECT DISTINCT origin FROM FlightLength ORDER BY origin")
        origins_rows = cursor.fetchall() or []
        origins = [r["origin"] for r in origins_rows]

        if filter_origin:
            cursor.execute(
                "SELECT DISTINCT destination FROM FlightLength WHERE origin=%s ORDER BY destination",
                (filter_origin,),
            )
        else:
            cursor.execute("SELECT DISTINCT destination FROM FlightLength ORDER BY destination")
        dest_rows = cursor.fetchall() or []
        destinations = [r["destination"] for r in dest_rows]

        # ---- routes list ----
        q = "SELECT origin, destination, length_minutes FROM FlightLength"
        where = []
        params = []

        if filter_origin:
            where.append("origin=%s")
            params.append(filter_origin)
        if filter_destination:
            where.append("destination=%s")
            params.append(filter_destination)

        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY origin, destination"

        cursor.execute(q, tuple(params))
        routes = cursor.fetchall() or []

    return render_template(
        "manage_flight_routes.html",
        routes=routes,
        origins=origins,
        destinations=destinations,
        filter_origin=filter_origin,
        filter_destination=filter_destination,
        add_prefill=add_prefill,
        error=error,
        success=success,
    )


if __name__ == '__main__':
    app.run(debug=True)




