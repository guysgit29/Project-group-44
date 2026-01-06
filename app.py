from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
from datetime import timedelta
from urllib.parse import urlencode

from database import DB
from models.customers import RegisteredUser
from models.booking import Booking
from models.employees import Manager
from models.flight import Flight

app = Flask(__name__)

# --- Flask Configuration ---
app.secret_key = "flytau_secret_key"
app.config.update(
    SESSION_TYPE="filesystem",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
)
Session(app)

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _safe_next(next_url):
    """
    Prevent open redirect:
    accept only internal paths that start with "/".
    """
    if not next_url:
        return None
    next_url = (next_url or "").strip()
    if next_url.startswith("/"):
        return next_url
    return None


def _url_with_selected_seats(endpoint, flight_id, selected_seats):
    """
    Build: /<endpoint>/<flight_id>?selected_seats=A&selected_seats=B...
    """
    base = url_for(endpoint, flight_id=flight_id)
    qs = urlencode([("selected_seats", s) for s in (selected_seats or [])])
    return f"{base}?{qs}" if qs else base


def _checkout_url_with_seats(flight_id, selected_seats):
    return _url_with_selected_seats("checkout", flight_id, selected_seats)


def _continue_booking_url(flight_id, selected_seats):
    return _url_with_selected_seats("continue_booking", flight_id, selected_seats)


# ------------------------------------------------------------
# Main Routes
# ------------------------------------------------------------

@app.route("/")
def home_page():
    """Landing page with search dropdowns."""
    origins, destinations = Flight.get_all_origins_and_destinations()
    return render_template("home_page.html", origins=origins, destinations=destinations)


@app.route("/search")
def search_flights():
    """Flight search."""
    origin = request.args.get("origin")
    destination = request.args.get("destination")

    if not origin or not destination:
        return redirect(url_for("home_page"))

    found_flights = Flight.search(origin, destination)
    return render_template("results.html", flights=found_flights, origin=origin, dest=destination)


@app.route("/my_flights")
def my_flights():
    """User bookings history."""
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    user_flights = Booking.get_user_flights(session["user_id"])
    return render_template("my_flights.html", flights=user_flights)


# ------------------------------------------------------------
# Booking Management Routes
# ------------------------------------------------------------

@app.route("/search_booking", methods=["GET", "POST"])
def search_booking():
    """Find booking by id + email."""
    if request.method == "POST":
        order_id = request.form.get("order_id")
        email = (request.form.get("email") or "").strip().lower()

        booking = Booking.get_by_id_and_email(order_id, email)
        if booking:
            return redirect(url_for("manage_booking", booking_id=booking.booking_id))

        return render_template("search_booking.html", error="Booking not found.")

    return render_template("search_booking.html")


@app.route("/manage_booking/<booking_id>")
def manage_booking(booking_id):
    """Booking details page."""
    booking = Booking(booking_id, None, None)
    order_data, seats = booking.get_details()
    if order_data:
        return render_template("manage_booking.html", order=order_data, seats=seats)
    return redirect(url_for("home_page"))


# ------------------------------------------------------------
# NEW: Order confirmation page after successful booking
# ------------------------------------------------------------

@app.route("/order_confirmation/<booking_id>")
def order_confirmation(booking_id):
    """
    Page after booking is completed (instead of manage_booking redirect).
    Requires templates/order_confirmation.html
    """
    booking = Booking.get_by_id(booking_id)
    if not booking:
        return redirect(url_for("home_page"))

    order_data, seats = booking.get_details()
    if not order_data:
        return redirect(url_for("home_page"))

    return render_template("order_confirmation.html", order=order_data, seats=seats)


# ------------------------------------------------------------
# Cancellation Flow
# ------------------------------------------------------------

@app.route("/cancel_confirm/<booking_id>")
def cancel_booking_confirm(booking_id):
    """Cancel confirmation page."""
    return render_template("cancel_confirm.html", booking_id=booking_id)


@app.route("/cancel_booking_execute/<booking_id>", methods=["POST"])
def cancel_booking_execute(booking_id):
    """Executes cancellation."""
    booking = Booking.get_by_id(booking_id)
    if booking and booking.status != "Canceled by Customer":
        booking.cancel()
    return redirect(url_for("manage_booking", booking_id=booking_id))


# ------------------------------------------------------------
# Authentication Routes (UPDATED: supports next)
# ------------------------------------------------------------

@app.route("/registration", methods=["GET", "POST"])
def registration():
    """
    User registration.
    Supports ?next=/some/internal/path to return to checkout after register.
    """
    if request.method == "GET":
        next_url = _safe_next(request.args.get("next"))
        return render_template("registration.html", error=None, next=next_url)

    # POST
    next_url = _safe_next(request.form.get("next"))

    user, error = RegisteredUser.register(request.form)
    if error:
        return render_template("registration.html", error=error, next=next_url)

    # Auto-login after successful registration (so user returns to checkout)
    if user:
        session["user_id"] = user.email
        session["role"] = "customer"

    return redirect(next_url or url_for("home_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    """
    Login route.
    Supports ?next=/some/internal/path to return to checkout after login.
    """
    if request.method == "GET":
        next_url = _safe_next(request.args.get("next"))
        return render_template("login.html", error=None, next=next_url)

    # POST
    next_url = _safe_next(request.form.get("next"))

    uid = request.form.get("username")
    pwd = request.form.get("password")

    user = Manager.login(uid, pwd) or RegisteredUser.login(uid, pwd)
    if user:
        session["user_id"] = getattr(user, "id", getattr(user, "email", None))
        session["role"] = "manager" if isinstance(user, Manager) else "customer"
        return redirect(next_url or url_for("home_page"))

    return render_template("login.html", error="Invalid Credentials", next=next_url)


@app.route("/logout")
def logout():
    """Logout."""
    session.clear()
    return redirect(url_for("home_page"))


# ------------------------------------------------------------
# Manager Routes
# ------------------------------------------------------------

@app.route("/manager_login", methods=["GET", "POST"])
def manager_login():
    if request.method == "POST":
        emp_id_raw = (request.form.get("id", "") or "").strip()
        password = (request.form.get("password", "") or "").strip()

        if not emp_id_raw.isdigit():
            return render_template("manager_login.html", error="תעודת עובד חייבת להיות מספר")

        emp_id = int(emp_id_raw)
        manager = Manager.login(emp_id, password)

        if manager:
            session["user_id"] = manager.id
            session["role"] = "manager"
            session["first_name"] = manager.first_name_he
            session["last_name"] = manager.last_name_he
            return redirect(url_for("manager_dashboard"))

        return render_template("manager_login.html", error="תעודת עובד או סיסמה שגויים")

    return render_template("manager_login.html")


@app.route("/manager_dashboard")
def manager_dashboard():
    if session.get("role") != "manager":
        return redirect(url_for("manager_login"))
    return render_template("manager_dashboard.html")


# ------------------------------------------------------------
# Seat Selection + Payment Summary
# ------------------------------------------------------------

@app.route("/seat_selection/<flight_id>")
def seat_selection(flight_id):
    flight_id_int = int(flight_id)
    seats = Flight.get_seat_map(flight_id_int)

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
        max_row=max_row,
    )


@app.route("/process_booking", methods=["POST"])
def process_booking():
    """
    Builds payment summary for selected seats and moves to payment_summary page.
    selected_seats values are like: Economy-2-3
    """
    flight_num = request.form.get("flight_number")
    selected_seats = request.form.getlist("selected_seats")

    if not flight_num:
        return redirect(url_for("home_page"))

    if not selected_seats:
        return redirect(url_for("seat_selection", flight_id=flight_num))

    total_price = 0.0
    details = []

    with DB.get_cursor() as cursor:
        for seat_str in selected_seats:
            class_type, row_num, col_num = seat_str.split("-")

            cursor.execute(
                """
                SELECT class_price
                FROM Classes_on_Flights
                WHERE flight_number = %s AND class_type = %s
                """,
                (int(flight_num), class_type),
            )
            res = cursor.fetchone()
            price = float(res["class_price"]) if res and res["class_price"] is not None else 0.0
            total_price += price

            seat_no = f"{row_num}{col_num}"

            details.append({
                "seat_no": seat_no,
                "class_type": class_type,
                "price": price,
                # backward compatibility for older templates:
                "seat": seat_no,
                "class": class_type,
            })

    return render_template(
        "payment_summary.html",
        details=details,
        total=total_price,
        flight_number=int(flight_num),
        selected_seats=selected_seats,
    )


# ------------------------------------------------------------
# NEW: guest-only bridge page (3 options)
# ------------------------------------------------------------

@app.route("/continue_booking/<int:flight_id>", methods=["GET"])
def continue_booking(flight_id):
    """
    Guest-only bridge page:
    - Existing customer -> Login (returns to checkout)
    - New customer -> Register (returns to checkout)
    - Continue as guest -> Checkout
    Requires templates/continue_booking.html
    """
    selected_seats = request.args.getlist("selected_seats")
    if not selected_seats:
        return redirect(url_for("seat_selection", flight_id=flight_id))

    # If already logged in as customer -> go directly to checkout
    if session.get("role") == "customer" and session.get("user_id"):
        return redirect(_checkout_url_with_seats(flight_id, selected_seats))

    checkout_url = _checkout_url_with_seats(flight_id, selected_seats)

    login_url = url_for("login_page") + "?" + urlencode({"next": checkout_url})
    registration_url = url_for("registration") + "?" + urlencode({"next": checkout_url})

    return render_template(
        "continue_booking.html",
        flight_number=flight_id,
        selected_seats=selected_seats,
        checkout_url=checkout_url,
        login_url=login_url,
        registration_url=registration_url,
    )


# ------------------------------------------------------------
# Checkout
# ------------------------------------------------------------

@app.route("/checkout/<int:flight_id>", methods=["GET", "POST"])
def checkout(flight_id):
    selected_seats = (
        request.form.getlist("selected_seats")
        if request.method == "POST"
        else request.args.getlist("selected_seats")
    )
    if not selected_seats:
        return redirect(url_for("seat_selection", flight_id=flight_id))

    details, total = Booking.get_pricing_for_selected_seats(flight_id, selected_seats)

    prefill = {"first_name": "", "last_name": "", "email": "", "lock_email": False}
    if session.get("role") == "customer" and session.get("user_id"):
        user = RegisteredUser.get_by_email(session["user_id"])
        if user:
            prefill["first_name"] = getattr(user, "first_name_en", "") or ""
            prefill["last_name"] = getattr(user, "last_name_en", "") or ""
            prefill["email"] = getattr(user, "email", "") or session["user_id"]
            prefill["lock_email"] = True

    # GET -> show page
    if request.method == "GET":
        # If not logged in as customer -> force bridge page
        if session.get("role") != "customer":
            return redirect(_continue_booking_url(flight_id, selected_seats))

        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill=prefill,
            error=None
        )

    # POST -> validate + create booking
    first_name = (request.form.get("first_name") or "").strip()
    last_name = (request.form.get("last_name") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    payment_method = request.form.get("payment_method") or "card"

    # block: email belongs to registered user but NOT logged in
    if session.get("role") != "customer":
        if RegisteredUser.email_exists(email):
            return render_template(
                "checkout.html",
                flight_number=flight_id,
                selected_seats=selected_seats,
                details=details,
                total=total,
                prefill={"first_name": first_name, "last_name": last_name, "email": email, "lock_email": False},
                error="עליך להתחבר לחשבונך כדי לבצע הזמנה עם כתובת מייל זו"
            )

    created_id = Booking.create_booking_with_tickets(
        flight_number=flight_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        selected_seats=selected_seats,
        payment_method=payment_method,
        logged_in_registered=(session.get("role") == "customer")
    )

    if not created_id:
        return render_template(
            "checkout.html",
            flight_number=flight_id,
            selected_seats=selected_seats,
            details=details,
            total=total,
            prefill={"first_name": first_name, "last_name": last_name, "email": email, "lock_email": False},
            error="לא ניתן להשלים הזמנה. ייתכן שמושב נתפס או שיש חוסר התאמה בנתוני מושבים לטיסה."
        )

    return redirect(url_for("order_confirmation", booking_id=created_id))


# ------------------------------------------------------------
# Run (MUST be last)
# ------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)