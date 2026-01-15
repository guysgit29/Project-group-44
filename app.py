from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_session import Session
from datetime import timedelta,datetime
from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager,Pilot,FlightAttendant
from models.flight import Flight
from datetime import date, datetime, timedelta
from models.employees import StaffService

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

@app.route("/manager_flights")
def manager_flights():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    Flight.sync_completed_flights()

    selected_status = (request.args.get("status", "") or "").strip()

    aircraft_id_raw = (request.args.get("aircraft_id", "") or "").strip()
    aircraft_id = int(aircraft_id_raw) if aircraft_id_raw.isdigit() else None

    flights = Flight.list_for_manager(selected_status, aircraft_id)

    for f in flights:
        # ✅ ביטול לא רלוונטי לטיסה שבוטלה/הושלמה
        if (f.get("flight_status") or "").strip() in ("Completed", "Canceled"):
            f["can_cancel"] = False
        else:
            f["can_cancel"] = Flight.can_manager_cancel(f["flight_number"])

    aircraft_ids = Flight.get_all_aircraft_ids()

    flash_msg = session.pop("flash_msg", None)

    return render_template(
        "manager_flights.html",
        flights=flights,
        selected_status=selected_status,
        selected_aircraft_id=aircraft_id_raw,
        aircraft_ids=aircraft_ids,
        flash_msg=flash_msg
    )

# --- Checkout ---
from datetime import datetime
from flask import request, redirect, url_for, render_template, session
from database import DB
from models.booking import Booking
from models.customers import RegisteredUser


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    # ----------------------------
    # Helpers
    # ----------------------------
    def _get_flight_and_seats():
        fn = (request.form.get("flight_number") if request.method == "POST" else request.args.get("flight_number"))
        seats = (request.form.getlist("selected_seats") if request.method == "POST" else request.args.getlist("selected_seats"))
        if not fn or not seats:
            return None, None
        try:
            return int(fn), seats
        except ValueError:
            return None, None

    def _split_phones(raw: str) -> list[str]:
        raw = (raw or "").strip()
        if not raw:
            return []
        raw = raw.replace(",", "\n")
        out, seen = [], set()
        for p in (x.strip() for x in raw.splitlines()):
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _render(error=None, prefill_override=None):
        pf = dict(prefill)
        if prefill_override:
            pf.update(prefill_override)
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill=pf,
            error=error,
        )

    # ----------------------------
    # Read inputs
    # ----------------------------
    flight_id, selected_seats = _get_flight_and_seats()
    if not flight_id or not selected_seats:
        return redirect(url_for("home_page"))

    details, total = Booking.get_pricing_for_selected_seats(flight_id, selected_seats)

    logged_in_registered = bool(session.get("role") == "customer" and session.get("user_id"))
    user_email = (session.get("user_id") or "").strip().lower()

    prefill = {
        "first_name": "",
        "last_name": "",
        "email": "",
        "passport_number": "",
        "phone_numbers": "",
        "lock_fields": False,
    }

    # ----------------------------
    # Prefill for logged-in user (all phones)
    # ----------------------------
    if logged_in_registered:
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT email, first_name_en, last_name_en, passport_number
                FROM RegisteredUser
                WHERE LOWER(email) = %s
                LIMIT 1
                """,
                (user_email,),
            )
            ru = cursor.fetchone()

            cursor.execute(
                """
                SELECT phone_number
                FROM RegisteredPhone
                WHERE LOWER(email) = %s
                ORDER BY phone_number
                """,
                (user_email,),
            )
            phones_rows = cursor.fetchall() or []

        if ru:
            phones = [r.get("phone_number") for r in phones_rows if r.get("phone_number")]
            prefill.update(
                {
                    "first_name": ru.get("first_name_en") or "",
                    "last_name": ru.get("last_name_en") or "",
                    "email": (ru.get("email") or user_email).lower(),
                    "passport_number": ru.get("passport_number") or "",
                    "phone_numbers": "\n".join(phones),
                    "lock_fields": True,
                }
            )

    # ----------------------------
    # GET
    # ----------------------------
    if request.method == "GET":
        return _render()

    # ----------------------------
    # POST (read values)
    # ----------------------------
    lock = bool(prefill["lock_fields"])

    def _val(name: str) -> str:
        return ((prefill.get(name) if lock else (request.form.get(name) or "")) or "").strip()

    first_name = _val("first_name")
    last_name = _val("last_name")
    email = _val("email").lower()
    passport_number = _val("passport_number")

    phone_numbers_raw = prefill.get("phone_numbers", "") if lock else (request.form.get("phone_numbers") or "")
    phones = _split_phones(phone_numbers_raw)

    payment_method = (request.form.get("payment_method") or "card").strip()

    # ----------------------------
    # Validation
    # ----------------------------
    if not first_name or not last_name or not email:
        return _render(
            error="אנא מלא את כל השדות הנדרשים.",
            prefill_override={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_numbers": phone_numbers_raw,
                "lock_fields": lock,
            },
        )

    if not phones:
        return _render(
            error="אנא הזן לפחות מספר טלפון אחד.",
            prefill_override={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_numbers": phone_numbers_raw,
                "lock_fields": lock,
            },
        )

    # Guest מנסה להזמין עם מייל רשום
    if (not logged_in_registered) and RegisteredUser.email_exists(email):
        return _render(
            error="עליך להתחבר לחשבונך כדי לבצע הזמנה עם כתובת מייל זו",
            prefill_override={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_numbers": phone_numbers_raw,
                "lock_fields": False,
            },
        )

    # ----------------------------
    # Create booking (PASS TEXT, not list)
    # ----------------------------
    created_id = Booking.create_booking_with_tickets(
        flight_number=flight_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        selected_seats=selected_seats,
        payment_method=payment_method,
        logged_in_registered=logged_in_registered,
        phone_numbers_text=phone_numbers_raw,   # ✅ זה התיקון הקריטי
        passport_number=passport_number,
    )

    if not created_id:
        return _render(
            error="לא ניתן להשלים הזמנה. ייתכן שמושב נתפס או שיש חוסר התאמה בנתוני מושבים לטיסה.",
            prefill_override={
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "passport_number": passport_number,
                "phone_numbers": phone_numbers_raw,
                "lock_fields": lock,
            },
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

from datetime import datetime, timedelta

from datetime import datetime, timedelta

@app.route("/manager_flight_manage/<int:flight_number>", methods=["GET", "POST"])
def manager_flight_manage(flight_number):
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    Flight.sync_completed_flights()

    flight = Flight.get_by_number(flight_number)
    if not flight:
        return redirect(url_for("manager_flights"))

    flight["aircraft_size"] = Flight.get_aircraft_size_for_flight(flight_number)

    st = (flight.get("flight_status") or "").strip()

    # ✅ טיסה שהושלמה – למסך צפייה בלבד
    if st == "Completed":
        return redirect(url_for("manager_flight_view", flight_number=flight_number))

    # ✅ טיסה שבוטלה – אין כניסה לניהול (חזרה לרשימה)
    # אם אצלך ב-DB זה "Canceled by Manager" ולא "Canceled" – תוסיף גם את זה כאן
    if st in ("Canceled", "Canceled by Manager"):
        session["flash_msg"] = "טיסה בוטלה"
        return redirect(url_for("manager_flights"))

    # --------
    # POST – שיבוץ / הסרה / ביטול טיסה
    # --------
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action == "cancel_flight":
            ok, msg = Flight.cancel_flight(flight_number)
            session["flash_msg"] = msg
            return redirect(url_for("manager_flight_manage", flight_number=flight_number))

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
    flash_msg = session.pop("flash_msg", None)

    assigned_pilots = Pilot.get_assigned_for_flight(flight_number)
    assigned_attendants = FlightAttendant.get_assigned_for_flight(flight_number)

    all_pilots = Pilot.list_all(flight_number)
    all_attendants = FlightAttendant.list_all(flight_number)

    required = Flight.get_required_crew_counts(flight_number)

    assigned_counts = {
        "pilots": len(assigned_pilots),
        "attendants": len(assigned_attendants),
    }

    missing_counts = {
        "pilots": max(0, required["pilots"] - assigned_counts["pilots"]),
        "attendants": max(0, required["attendants"] - assigned_counts["attendants"]),
    }

    # ✅ חישוב "יוצאת בקרוב" + can_cancel רק ל-Active/Full
    now = datetime.now()
    dep = flight.get("departure_time")

    # אם dep מגיע כמחרוזת, ננסה להמיר
    if isinstance(dep, str):
        # תתאים לפורמט שיוצא אצלך בפועל. לרוב MySQL connector מחזיר datetime, אבל לפעמים זה str.
        try:
            dep = datetime.strptime(dep, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dep = None

    is_active_like = st in ("Active", "Full")

    is_departing_soon = False
    can_cancel = False

    if is_active_like and isinstance(dep, datetime):
        time_left = dep - now
        # יוצאת בקרוב: בתוך 72 שעות, ועדיין לא יצאה
        is_departing_soon = timedelta(seconds=0) < time_left <= timedelta(hours=72)
        # אפשר לבטל: יותר מ-72 שעות
        can_cancel = time_left > timedelta(hours=72)

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
        flash_msg=flash_msg,
        can_cancel=can_cancel,
        is_departing_soon=is_departing_soon,
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

import re
from datetime import datetime

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

def _parse_date_time(date_str: str, time_str: str):
    # date: YYYY-MM-DD  time: HH:MM
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except Exception:
        return None

def _normalize_airport(s: str) -> str:
    return (s or "").strip().upper()

# ✅ HH:MM או HH:MM:SS
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$")

def _is_time_ok(t: str) -> bool:
    return bool(_TIME_RE.match((t or "").strip()))
from datetime import datetime




# =========================================================
# Step 1/5 - create flight (origin/destination/date/time)
# =========================================================
@app.route("/manager_flight_create", methods=["GET", "POST"])
def manager_flight_create():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    error = None

    # ✅ DISTINCT של כל השדות (origin+destination) מתוך FlightLength
    airports = Flight.get_all_airports_distinct()

    if request.method == "POST":
        origin = _normalize_airport(request.form.get("origin"))
        destination = _normalize_airport(request.form.get("destination"))
        flight_date = (request.form.get("flight_date") or "").strip()
        flight_time = (request.form.get("flight_time") or "").strip()

        dep_dt = _parse_date_time(flight_date, flight_time)

        if not origin or not destination or not dep_dt:
            error = "חובה לבחור מקור, יעד, תאריך ושעה"
        elif origin == destination:
            error = "מקור ויעד לא יכולים להיות אותו שדה תעופה"
        else:
            info = Flight.get_route_info(origin, destination)
            if not info:
                error = "הנתיב לא קיים ב-FlightLength. קודם הוסף קו טיסה."
            else:
                duration_sec = int(info.get("duration_sec") or 0)
                require_large = duration_sec > 6 * 3600

                arr_dt = Flight.compute_arrival(dep_dt, origin, destination)
                if arr_dt is None:
                    arrival_preview_str = None
                elif hasattr(arr_dt, "strftime"):
                    arrival_preview_str = arr_dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    arrival_preview_str = str(arr_dt)

                _draft_set({
                    "origin": origin,
                    "destination": destination,
                    "departure_dt": dep_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "arrival_dt_preview": arrival_preview_str,
                    "duration_sec": duration_sec,
                    "require_large": require_large,

                    "aircraft_id": None,
                    "aircraft_size": None,
                    "pricing": None,
                    "pilot_ids": [],
                    "attendant_ids": [],
                })
                return redirect(url_for("manager_assign_aircraft"))

    draft = _draft_get() or {}

    return render_template(
        "manager_flight_create_step1.html",
        error=error,
        origins=airports,
        destinations=airports,
        today_date=date.today().strftime("%Y-%m-%d"),
        prefill={
            "origin": draft.get("origin", ""),
            "destination": draft.get("destination", ""),
    }
)

# =========================================================
# Step 2/5 - assign aircraft
# =========================================================
@app.route("/manager_assign_aircraft", methods=["GET", "POST"])
def manager_assign_aircraft():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get() or {}

    if not draft.get("origin") or not draft.get("destination") or not draft.get("departure_dt"):
        return redirect(url_for("manager_flight_create"))

    origin = draft["origin"]
    dep_dt = datetime.strptime(draft["departure_dt"], "%Y-%m-%d %H:%M:%S")
    require_large = bool(draft.get("require_large"))

    aircrafts = Flight.list_available_aircrafts_for_route(origin, dep_dt, require_large)

    error = None
    if request.method == "POST":
        aircraft_id_raw = (request.form.get("aircraft_id") or "").strip()
        if not aircraft_id_raw:
            error = "חובה לבחור מטוס"
        else:
            new_aircraft_id = int(aircraft_id_raw)

            prev_aircraft_id = draft.get("aircraft_id")
            if prev_aircraft_id is None or int(prev_aircraft_id) != new_aircraft_id:
                # החלפת מטוס => כל מה שתלוי בו מתאפס
                draft["pilot_ids"] = []
                draft["attendant_ids"] = []
                draft["pricing"] = None

            draft["aircraft_id"] = new_aircraft_id

            # לשימוש בשלבים הבאים (Business/crew rules)
            try:
                draft["aircraft_size"] = Flight.get_aircraft_size(new_aircraft_id)
            except Exception:
                draft["aircraft_size"] = None

            _draft_set(draft)
            return redirect(url_for("manager_set_pricing"))

    return render_template(
        "manager_flight_assign_aircraft.html",
        error=error,
        draft=draft,
        aircrafts=aircrafts,
        require_large=require_large
    )


# =========================================================
# Step 3/5 - pricing (simple)
# =========================================================
@app.route("/manager_set_pricing", methods=["GET", "POST"])
def manager_set_pricing():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get() or {}

    # חייבים להגיע אחרי בחירת מטוס
    if not draft.get("aircraft_id") or not draft.get("origin") or not draft.get("destination") or not draft.get("departure_dt"):
        return redirect(url_for("manager_assign_aircraft"))

    aircraft_id = int(draft["aircraft_id"])

    # Business רק אם Large (כמו שסיכמנו)
    aircraft_size = (draft.get("aircraft_size") or Flight.get_aircraft_size(aircraft_id) or "").strip().lower()
    draft["aircraft_size"] = aircraft_size
    has_business = (aircraft_size == "large")

    pricing = draft.get("pricing") or {}
    economy_price = pricing.get("economy_price", 299.0)
    business_price = pricing.get("business_price", 599.0)

    error = None
    if request.method == "POST":
        try:
            economy_price = float(request.form.get("economy_price") or 0)
            if economy_price <= 0:
                raise ValueError("מחיר Economy חייב להיות גדול מ-0")

            new_pricing = {"economy_price": economy_price}

            if has_business:
                business_price = float(request.form.get("business_price") or 0)
                if business_price <= 0:
                    raise ValueError("מחיר Business חייב להיות גדול מ-0")
                new_pricing["business_price"] = business_price
            else:
                new_pricing["business_price"] = None

            draft["pricing"] = new_pricing
            _draft_set(draft)
            return redirect(url_for("manager_assign_crew"))

        except ValueError as e:
            error = str(e)

    return render_template(
        "manager_flight_pricing.html",
        draft=draft,
        has_business=has_business,
        economy_price=economy_price,
        business_price=business_price,
        error=error
    )


# =========================================================
# Step 4/5 - assign crew
# =========================================================
@app.route("/manager_assign_crew", methods=["GET", "POST"])
def manager_assign_crew():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get() or {}
    if not draft.get("aircraft_id"):
        return redirect(url_for("manager_assign_aircraft"))

    pricing = draft.get("pricing") or {}
    if not pricing.get("economy_price"):
        return redirect(url_for("manager_set_pricing"))

    origin = draft.get("origin")
    departure_str = draft.get("departure_dt")
    if not origin or not departure_str:
        return redirect(url_for("manager_flight_create"))

    dep_dt = datetime.strptime(departure_str, "%Y-%m-%d %H:%M:%S")

    aircraft_id = int(draft["aircraft_id"])
    aircraft_size = (draft.get("aircraft_size") or Flight.get_aircraft_size(aircraft_id) or "").strip().lower()
    draft["aircraft_size"] = aircraft_size

    need = {"pilots": 3, "attendants": 6} if aircraft_size == "large" else {"pilots": 2, "attendants": 3}

    draft.setdefault("pilot_ids", [])
    draft.setdefault("attendant_ids", [])

    error = None
    flash_msg = None
    action = request.form.get("action") if request.method == "POST" else None

    if request.method == "POST":
        if action == "assign_pilot":
            pilot_id = request.form.get("pilot_id")
            if not pilot_id:
                error = "לא נבחר טייס"
            else:
                pid = int(pilot_id)
                if pid in draft["pilot_ids"]:
                    error = "הטייס כבר שובץ"
                elif len(draft["pilot_ids"]) >= int(need["pilots"]):
                    error = f"כבר שובצו מספיק טייסים (נדרש {need['pilots']})"
                else:
                    draft["pilot_ids"].append(pid)
                    _draft_set(draft)
                    flash_msg = "טייס שובץ בהצלחה"

        elif action == "remove_pilot":
            pilot_id = request.form.get("pilot_id")
            if pilot_id:
                pid = int(pilot_id)
                if pid in draft["pilot_ids"]:
                    draft["pilot_ids"].remove(pid)
                    _draft_set(draft)
                    flash_msg = "טייס הוסר"
                else:
                    error = "הטייס לא נמצא ברשימת המשובצים"

        elif action == "assign_attendant":
            attendant_id = request.form.get("attendant_id")
            if not attendant_id:
                error = "לא נבחר דייל/ת"
            else:
                aid = int(attendant_id)
                if aid in draft["attendant_ids"]:
                    error = "הדייל/ת כבר שובץ/ה"
                elif len(draft["attendant_ids"]) >= int(need["attendants"]):
                    error = f"כבר שובצו מספיק דיילים (נדרש {need['attendants']})"
                else:
                    draft["attendant_ids"].append(aid)
                    _draft_set(draft)
                    flash_msg = "דייל/ת שובץ/ה בהצלחה"

        elif action == "remove_attendant":
            attendant_id = request.form.get("attendant_id")
            if attendant_id:
                aid = int(attendant_id)
                if aid in draft["attendant_ids"]:
                    draft["attendant_ids"].remove(aid)
                    _draft_set(draft)
                    flash_msg = "דייל/ת הוסר/ה"
                else:
                    error = "הדייל/ת לא נמצא/ת ברשימת המשובצים"

        elif action == "continue":
            if len(draft["pilot_ids"]) != int(need["pilots"]):
                error = f"חובה לשבץ בדיוק {need['pilots']} טייסים"
            elif len(draft["attendant_ids"]) != int(need["attendants"]):
                error = f"חובה לשבץ בדיוק {need['attendants']} דיילים"
            else:
                _draft_set(draft)
                return redirect(url_for("manager_flight_confirm"))

    # ✅ זמינים עם שמות (כבר יש במודל שלך)
    available_pilots = Flight.list_available_pilots_for_new_flight(origin, dep_dt, require_large=(aircraft_size == "large"))
    available_attendants = Flight.list_available_attendants_for_new_flight(origin, dep_dt, require_large=(aircraft_size == "large"))

    # הסתר מי שכבר שובץ
    available_pilots = [p for p in (available_pilots or []) if int(p["id"]) not in draft["pilot_ids"]]
    available_attendants = [a for a in (available_attendants or []) if int(a["id"]) not in draft["attendant_ids"]]

    # ✅ משובצים עם שם + ת״ז (SQL ישיר)
    assigned_pilots = Flight.get_pilots_by_ids(draft["pilot_ids"])
    assigned_attendants = Flight.get_attendants_by_ids(draft["attendant_ids"])

    assigned_counts = {"pilots": len(draft["pilot_ids"]), "attendants": len(draft["attendant_ids"])}
    missing_counts = {
        "pilots": int(need["pilots"]) - assigned_counts["pilots"],
        "attendants": int(need["attendants"]) - assigned_counts["attendants"],
    }

    return render_template(
        "manager_flight_assign_crew.html",
        error=error,
        flash_msg=flash_msg,
        draft=draft,
        required=need,
        available_pilots=available_pilots,
        available_attendants=available_attendants,
        assigned_pilots=assigned_pilots,           # ✅ כולל id + שם
        assigned_attendants=assigned_attendants,   # ✅ כולל id + שם
        assigned_counts=assigned_counts,
        missing_counts=missing_counts,
    )

# =========================================================
# Step 5/5 - confirm & persist (Flight + Crew + Prices + Seats_on_Flights)
# =========================================================
@app.route("/manager_flight_confirm", methods=["GET", "POST"])
def manager_flight_confirm():
    if not _require_manager():
        return redirect(url_for("manager_login"))

    draft = _draft_get() or {}

    # מינימום חובה
    must = ["origin", "destination", "departure_dt", "aircraft_id"]
    if any(not draft.get(k) for k in must):
        return redirect(url_for("manager_flight_create"))

    # תמחור חובה
    pricing = draft.get("pricing") or {}
    if not pricing.get("economy_price"):
        return redirect(url_for("manager_set_pricing"))

    # צוות חובה (לפי הרשימות)
    pilot_ids = draft.get("pilot_ids") or []
    attendant_ids = draft.get("attendant_ids") or []
    if not pilot_ids or not attendant_ids:
        return redirect(url_for("manager_assign_crew"))

    origin = draft["origin"]
    destination = draft["destination"]
    dep_dt = datetime.strptime(draft["departure_dt"], "%Y-%m-%d %H:%M:%S")
    arr_preview = draft.get("arrival_dt_preview")

    aircraft_id = int(draft["aircraft_id"])
    aircraft = Flight.get_aircraft_by_id(aircraft_id)
    aircraft_size = (draft.get("aircraft_size") or (aircraft.get("aircraft_size") if aircraft else "") or "").strip().lower()

    info = Flight.get_route_info(origin, destination)
    if not info:
        return redirect(url_for("manager_flight_create"))

    # =========================================================
    # LOAD CREW DETAILS (ID + NAME) for template
    # =========================================================
    assigned_pilots = []
    assigned_attendants = []

    try:
        if hasattr(Flight, "get_pilots_by_ids"):
            assigned_pilots = Flight.get_pilots_by_ids(pilot_ids)
        if hasattr(Flight, "get_attendants_by_ids"):
            assigned_attendants = Flight.get_attendants_by_ids(attendant_ids)
    except Exception:
        # fallback to direct SQL below
        assigned_pilots = []
        assigned_attendants = []

    # fallback אם אין פונקציות במודל / נכשלו
    with DB.get_cursor() as cursor:
        if not assigned_pilots and pilot_ids:
            placeholders = ",".join(["%s"] * len(pilot_ids))
            cursor.execute(
                f"""
                SELECT id, first_name_he, last_name_he
                FROM Pilot
                WHERE id IN ({placeholders})
                ORDER BY id
                """,
                tuple(pilot_ids),
            )
            assigned_pilots = cursor.fetchall()

        if not assigned_attendants and attendant_ids:
            placeholders = ",".join(["%s"] * len(attendant_ids))
            cursor.execute(
                f"""
                SELECT id, first_name_he, last_name_he
                FROM FlightAttendant
                WHERE id IN ({placeholders})
                ORDER BY id
                """,
                tuple(attendant_ids),
            )
            assigned_attendants = cursor.fetchall()

    error = None
    if request.method == "POST":
        flight_number = Flight.generate_next_flight_number()

        duration_sec = int(info.get("duration_sec") or 0)
        if duration_sec > 6 * 3600 and aircraft_size != "large":
            error = "לא ניתן לאשר: טיסה מעל 6 שעות חייבת מטוס Large"
        else:
            eco_price = float(pricing.get("economy_price"))
            bus_price = pricing.get("business_price")
            bus_price = float(bus_price) if bus_price not in (None, "", 0) else None

            with DB.get_cursor() as cursor:
                # 1) Flight
                cursor.execute("""
                    INSERT INTO Flight (flight_number, aircraft_id, origin, destination, departure_time, flight_status)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """, (int(flight_number), int(aircraft_id), origin, destination, dep_dt, "Active"))

                # 2) Crew
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

                # 3) Prices -> Classes_on_Flights
                cursor.execute("""
                    INSERT INTO Classes_on_Flights (aircraft_id, class_type, flight_number, class_price)
                    VALUES (%s,%s,%s,%s)
                """, (int(aircraft_id), "Economy", int(flight_number), eco_price))

                # Business רק אם יש מחיר וגם קיימת מחלקת Business למטוס
                if bus_price is not None:
                    cursor.execute("""
                        SELECT 1
                        FROM Class
                        WHERE aircraft_id = %s AND class_type = 'Business'
                        LIMIT 1
                    """, (int(aircraft_id),))
                    if cursor.fetchone():
                        cursor.execute("""
                            INSERT INTO Classes_on_Flights (aircraft_id, class_type, flight_number, class_price)
                            VALUES (%s,%s,%s,%s)
                        """, (int(aircraft_id), "Business", int(flight_number), bus_price))

                # 4) Seats_on_Flights -> copy all seats of aircraft, available=1
                cursor.execute("""
                    INSERT INTO Seats_on_Flights (aircraft_id, class_type, row_num, column_number, flight_number, available)
                    SELECT s.aircraft_id, s.class_type, s.row_num, s.column_number, %s, 1
                    FROM Seat s
                    WHERE s.aircraft_id = %s
                """, (int(flight_number), int(aircraft_id)))

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
        pricing=pricing,

        # IDs (אם אתה עדיין משתמש)
        pilot_ids=pilot_ids,
        attendant_ids=attendant_ids,

        # NEW: objects for display: id + first_name_he + last_name_he
        assigned_pilots=assigned_pilots,
        assigned_attendants=assigned_attendants,
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
        origin = _normalize_airport(request.form.get("origin"))
        destination = _normalize_airport(request.form.get("destination"))
        length_minutes = (request.form.get("length_minutes") or "").strip()

        add_prefill = {"origin": origin, "destination": destination, "length_minutes": length_minutes}

        if not origin or not destination or not length_minutes:
            error = "נא למלא מקור, יעד ואורך טיסה"
        elif origin == destination:
            error = "מקור ויעד לא יכולים להיות זהים"
        elif not _is_time_ok(length_minutes):
            error = "לא ניתן להוסיף: אורך טיסה חייב להיות בפורמט HH:MM או HH:MM:SS"
        else:
            # אם HH:MM -> נוסיף :00
            if re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", length_minutes):
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
            except Exception:
                error = "לא ניתן להוסיף: הקו כבר קיים או שיש שגיאה בנתונים"

    # ---- dropdown data ----
    with DB.get_cursor() as cursor:
        cursor.execute("SELECT DISTINCT origin FROM FlightLength ORDER BY origin")
        origins_rows = cursor.fetchall() or []
        origins = [r["origin"] for r in origins_rows]

        if filter_origin:
            cursor.execute(
                "SELECT DISTINCT destination FROM FlightLength WHERE origin=%s ORDER BY destination",
                (_normalize_airport(filter_origin),),
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
            params.append(_normalize_airport(filter_origin))
        if filter_destination:
            where.append("destination=%s")
            params.append(_normalize_airport(filter_destination))

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

    # כרגע רק מסך ריק/שלד
    return render_template("add_flight_length.html")
@app.route("/manager_flight_cancel/<int:flight_number>", methods=["POST"])
def manager_flight_cancel(flight_number):
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    ok, msg = Flight.cancel_flight(flight_number)
    session["flash_msg"] = msg
    return redirect(url_for("manager_flights"))
# app.py

# app.py
from flask import render_template, redirect, url_for, session
from models.reports import ManagerReports

@app.route("/manager_reports", methods=["GET"])
def manager_reports():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    r1 = ManagerReports.report_1_avg_occupancy_past_flights()
    r2 = ManagerReports.report_2_revenue_by_aircraft_and_class()
    r3 = ManagerReports.report_3_crew_hours_short_long()
    r4 = ManagerReports.report_4_monthly_cancellation_rate()

    return render_template(
        "manager_reports.html",
        report1_avg=r1,
        report2_rows=r2,
        report3_rows=r3,
        report4_rows=r4
    )

def _require_logged_in_user():
    return session.get("role") == "registered" and session.get("user_email")

from models.customers import RegisteredUser

@app.route("/profile", methods=["GET", "POST"])
def profile():
    # רק ללקוחות מחוברים
    if session.get("role") != "customer" or not session.get("user_id"):
        return redirect(url_for("login_page"))

    email = (session.get("user_id") or "").strip().lower()

    user, phones = RegisteredUser.get_profile_with_phones(email)
    if not user:
        session.clear()
        return redirect(url_for("login_page"))

    def _prefill(u, phs, override=None):
        pf = {
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "birth_date": (u.birth_date.strftime("%Y-%m-%d") if u.birth_date else ""),
            "passport_number": u.passport or "",
            "phone_numbers": "\n".join(phs),
        }
        if override:
            pf.update(override)
        return pf

    if request.method == "GET":
        return render_template("profile.html", prefill=_prefill(user, phones), error=None, success=None)

    # POST
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    birth_date = (request.form.get("birth_date") or "").strip() or None
    passport_number = (request.form.get("passport_number") or "").strip()

    phone_numbers_raw = request.form.get("phone_numbers") or ""

    # אם אתה רוצה לחייב לפחות טלפון אחד בפרופיל:
    if not RegisteredUser.parse_phones(phone_numbers_raw):
        return render_template(
            "profile.html",
            prefill=_prefill(user, phones, override={
                "first_name": first_name,
                "last_name": last_name,
                "birth_date": birth_date or "",
                "passport_number": passport_number,
                "phone_numbers": phone_numbers_raw,
            }),
            error="אנא הזן לפחות מספר טלפון אחד",
            success=None,
        )

    ok, err = RegisteredUser.update_profile_and_phones(
        email=email,
        first_name_en=first_name,
        last_name_en=last_name,
        birth_date=birth_date,
        passport_number=passport_number,
        phones_text=phone_numbers_raw,
        password=None,  # לא משנים סיסמה כאן
    )

    user2, phones2 = RegisteredUser.get_profile_with_phones(email)
    return render_template(
        "profile.html",
        prefill=_prefill(user2, phones2),
        error=err if not ok else None,
        success=None if not ok else "הפרטים עודכנו בהצלחה",
    )

@app.route("/staff", methods=["GET", "POST"])
def staff_page():
    # רק מנהל
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    error = None
    success = None

    if request.method == "POST":
        staff_type = request.form.get("staff_type")  # pilot/attendant
        ok, err = StaffService.add_staff_member(staff_type, request.form)
        if ok:
            success = "איש צוות נוסף בהצלחה"
        else:
            error = err or "שגיאה בהוספה"

    pilots, attendants = StaffService.get_staff_tables()
    return render_template(
        "staff.html",
        pilots=pilots,
        attendants=attendants,
        error=error,
        success=success,
    )

if __name__ == '__main__':
    app.run(debug=True)




