from flask import Flask, render_template, request, redirect, session, url_for, flash
from flask_session import Session
from datetime import timedelta,datetime
from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager,Pilot,FlightAttendant
from models.flight import Flight
###
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

    for f in flights:
        # ✅ ביטול לא רלוונטי לטיסה שבוטלה/הושלמה
        if (f.get("flight_status") or "").strip() in ("Completed", "Canceled by Manager"):
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
    # ✅ לא מאפשרים צפייה בטיסה שבוטלה ע"י מנהל
    if (flight.get("flight_status") or "").strip() == "Canceled by Manager":
        session["flash_msg"] = "אין צפייה בפרטים לטיסה שבוטלה ע״י מנהל"
        return redirect(url_for("manager_flights"))


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
    # POST – שיבוץ / הסרה / ביטול טיסה
    # --------
    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        # ✅ ביטול טיסה מתוך דף הניהול
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

    # ✅ כדי שה־template לא יצטרך Flight
    can_cancel = Flight.can_manager_cancel(flight_number)
    # ✅ טיסה שבוטלה ע"י מנהל — לא נכנסים לניהול
    if (flight.get("flight_status") or "").strip() == "Canceled by Manager":
        session["flash_msg"] = "לא ניתן לנהל טיסה שבוטלה ע״י מנהל"
        return redirect(url_for("manager_flights"))
    can_cancel = Flight.can_manager_cancel(flight_number)  # מה שכבר יש לך
    is_departing_soon = (not can_cancel) and (
                (flight.get("flight_status") or "").strip() not in ["Completed", "Canceled by Manager"])

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
        is_departing_soon=is_departing_soon
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
@app.route("/manager_flight_create", methods=["GET", "POST"])
def manager_flight_create():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

    aircrafts = Flight.get_all_aircrafts()
    routes = Flight.get_all_routes()

    error = None
    preview = None
    available_pilots = []
    available_attendants = []

    # נקלוט שדות (גם ב-GET וגם ב-POST)
    flight_number = (request.values.get("flight_number") or "").strip()
    aircraft_id = (request.values.get("aircraft_id") or "").strip()
    origin = (request.values.get("origin") or "").strip()
    destination = (request.values.get("destination") or "").strip()
    departure_str = (request.values.get("departure_time") or "").strip()

    # מצב "טעינת צוות" (GET/POST עם action=preview)
    action = (request.values.get("action") or "").strip()

    # אם יש לנו 4 שדות בסיסיים -> נחשב arrival ונביא צוות זמין
    if aircraft_id and origin and destination and departure_str:
        try:
            dep_dt = datetime.strptime(departure_str, "%Y-%m-%dT%H:%M")
            length = Flight.get_route_length(origin, destination)
            if not length:
                error = "הנתיב לא קיים ב-FlightLength. קודם הוסף קו טיסה."
            else:
                # compute arrival עם SQL כדי לא להסתבך עם TIME בפייתון
                with DB.get_cursor() as cursor:
                    cursor.execute("""
                        SELECT ADDTIME(%s, length_minutes) AS arrival_dt,
                               TIME_TO_SEC(length_minutes) AS sec
                        FROM FlightLength
                        WHERE origin=%s AND destination=%s
                    """, (dep_dt, origin, destination))
                    row = cursor.fetchone() or {}

                arr_dt = row.get("arrival_dt")
                duration_sec = int(row.get("sec") or 0)

                size = Flight.get_aircraft_size(int(aircraft_id))
                if duration_sec > 6 * 3600 and size != "large":
                    error = "טיסה מעל 6 שעות חייבת להיות עם מטוס Large"

                if not error:
                    preview = {
                        "dep": dep_dt,
                        "arr": arr_dt,
                        "aircraft_size": size
                    }
                    available_pilots = Pilot.list_available_for_new_flight(origin, dep_dt, arr_dt, size)
                    available_attendants = FlightAttendant.list_available_for_new_flight(origin, dep_dt, arr_dt, size)
        except ValueError:
            error = "פורמט תאריך/שעה לא תקין"

    # יצירת טיסה בפועל
    if request.method == "POST" and action == "create":
        if not (flight_number and aircraft_id and origin and destination and departure_str):
            error = "חובה למלא מספר טיסה, מטוס, מקור, יעד ותאריך/שעה"
        else:
            try:
                dep_dt = datetime.strptime(departure_str, "%Y-%m-%dT%H:%M")
            except ValueError:
                dep_dt = None
                error = "פורמט תאריך/שעה לא תקין"

        if not error:
            ok, msg = Flight.create_flight(
                flight_number=int(flight_number),
                aircraft_id=int(aircraft_id),
                origin=origin,
                destination=destination,
                departure_time=dep_dt,
                flight_status="Active"
            )
            if not ok:
                error = msg
            else:
                # צוות נבחר (אופציונלי)
                chosen_pilots = request.form.getlist("pilot_ids")
                chosen_attendants = request.form.getlist("attendant_ids")

                # נשבץ רק מה שנבחר (אם לא בחרת כלום – בסדר)
                with DB.get_cursor() as cursor:
                    for pid in chosen_pilots:
                        cursor.execute("""
                            INSERT IGNORE INTO pilots_on_flights (id, flight_number)
                            VALUES (%s,%s)
                        """, (int(pid), int(flight_number)))

                    for aid in chosen_attendants:
                        cursor.execute("""
                            INSERT IGNORE INTO flightattendants_on_flights (id, flight_number)
                            VALUES (%s,%s)
                        """, (int(aid), int(flight_number)))

                return redirect(url_for("manager_flight_manage", flight_number=int(flight_number)))

    return render_template(
        "manager_flight_create.html",
        aircrafts=aircrafts,
        routes=routes,
        error=error,
        preview=preview,
        available_pilots=available_pilots,
        available_attendants=available_attendants,
        # כדי לשמור ערכים בטופס אחרי רענון:
        flight_number=flight_number,
        aircraft_id=aircraft_id,
        origin=origin,
        destination=destination,
        departure_time=departure_str
    )
@app.route("/add_flight_length", methods=["GET"])
def add_flight_length():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))

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


if __name__ == '__main__':
    app.run(debug=True)