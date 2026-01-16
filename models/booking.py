from datetime import date
from database import DB
from datetime import datetime,timedelta
import re
from models.flight import Flight

class Booking:
    def __init__(self, booking_id, flight_number, price, status='Active'):
        self.booking_id = booking_id
        self.flight_number = flight_number
        self.price = price
        self.status = status

        # ----------------------------
        # Debug helper
        # ----------------------------
        @staticmethod
        def _dbg(msg: str):
            print(f"[DBG][Booking] {msg}")

    @staticmethod
    def get_by_id(booking_id):
        """
        FIX FOR AttributeError: Fetches a booking object by its ID.

        """
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    @staticmethod
    def from_db(row):
        if not row:
            return None
        return Booking(
            row.get("booking_id"),
            row.get("flight_number"),
            row.get("price"),
            row.get("booking_status", "Active"),
        )
    @staticmethod
    def _dbg(msg: str):
        print(f"[DBG][Booking] {msg}")

    @staticmethod
    def get_by_id(booking_id):
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    @staticmethod
    def get_by_id_and_email(booking_id, email):
        """Used for public booking search"""
        query = "SELECT * FROM Booking WHERE booking_id = %s AND (registered_email = %s OR guest_email = %s)"
        with DB.get_cursor() as cursor:
            cursor.execute(query, (booking_id, email, email))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    def get_details(self):
        """Fixes AttributeError for manage_booking page"""
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT B.*, F.origin, F.destination, F.departure_time, F.arrival_time, F.flight_status,
                COALESCE(B.registered_email, B.guest_email) as email
                FROM Booking B JOIN Flight F ON B.flight_number = F.flight_number
                WHERE B.booking_id = %s""", (self.booking_id,))
            order = cursor.fetchone()

            cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            seats = cursor.fetchall()
            return order, seats

    def cancel(self):
        """
        Cancel booking:
        - delete tickets
        - mark booking canceled + apply fee
        - IMPORTANT: refresh flight status (Full/Active) after seats are freed
        """
        with DB.get_cursor() as cursor:
            # ensure we have flight_number even if this object was created manually
            if not self.flight_number:
                cursor.execute(
                    "SELECT flight_number FROM Booking WHERE booking_id = %s",
                    (self.booking_id,),
                )
                r = cursor.fetchone()
                self.flight_number = r.get("flight_number") if r else None

            cursor.execute("DELETE FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            cursor.execute(
                """
                UPDATE Booking
                SET booking_status = 'Canceled by Customer',
                    price = price * 0.05
                WHERE booking_id = %s
                """,
                (self.booking_id,),
            )

        # NEW: always recompute flight status after cancellation
        if self.flight_number:
            from models.flight import Flight
            Flight.update_status_by_capacity(int(self.flight_number))

    @staticmethod
    def get_user_flights(email):
        query = """
            SELECT B.booking_id, B.flight_number, B.price, B.booking_status,
                   F.origin, F.destination, F.departure_time
            FROM Booking B
            JOIN Flight F ON B.flight_number = F.flight_number
            WHERE B.registered_email = %s OR B.guest_email = %s
            ORDER BY F.departure_time DESC
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (email, email))
            return cursor.fetchall()

    @staticmethod
    def sync_past_bookings():
        """עדכון אוטומטי של הזמנות שזמן הטיסה שלהן עבר"""
        query = """
            UPDATE Booking B
            JOIN Flight F ON B.flight_number = F.flight_number
            SET B.booking_status = 'Completed'
            WHERE B.booking_status = 'Active' 
              AND F.departure_time < NOW()
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query)

    @staticmethod
    def from_db(row):
        """Helper to convert DB row to Python object"""
        if not row: return None
        return Booking(row['booking_id'], row['flight_number'], row['price'], row['booking_status'])

    # ----------------------------
    # Seat parsing
    # ----------------------------
    @staticmethod
    def _parse_seat_val(seat_val: str):
        # "Economy-1-4" -> ("Economy", 1, 4)
        parts = (seat_val or "").split("-")
        if len(parts) != 3:
            return None
        class_type = parts[0]
        try:
            row_num = int(parts[1])
            col_num = int(parts[2])
        except ValueError:
            return None
        return class_type, row_num, col_num

    @staticmethod
    def _get_aircraft_id_for_flight(cursor, flight_number: int):
        cursor.execute("SELECT aircraft_id FROM Flight WHERE flight_number = %s", (flight_number,))
        f = cursor.fetchone()
        if not f or f.get("aircraft_id") is None:
            return None
        return int(f["aircraft_id"])

    # ----------------------------
    # Pricing (matches your get_seat_map join logic)
    # ----------------------------
    @staticmethod
    def get_pricing_for_selected_seats(flight_number: int, selected_seats: list[str]):
        """
        Returns: (details_list, total)
        """
        Booking._dbg(f"get_pricing_for_selected_seats(flight={flight_number}, seats={selected_seats})")

        parsed = [Booking._parse_seat_val(s) for s in (selected_seats or [])]
        parsed = [p for p in parsed if p is not None]
        if not flight_number or not parsed:
            Booking._dbg("pricing: no flight_number or no parsed seats -> ([],0)")
            return [], 0.0

        with DB.get_cursor() as cursor:
            aircraft_id = Booking._get_aircraft_id_for_flight(cursor, int(flight_number))
            if aircraft_id is None:
                Booking._dbg("pricing: cannot find aircraft_id for flight -> ([],0)")
                return [], 0.0

            class_types = sorted({p[0] for p in parsed})
            placeholders = ",".join(["%s"] * len(class_types))

            cursor.execute(
                f"""
                SELECT class_type, class_price
                FROM Classes_on_Flights
                WHERE flight_number = %s
                  AND aircraft_id = %s
                  AND class_type IN ({placeholders})
                """,
                tuple([int(flight_number), aircraft_id] + class_types),
            )
            rows = cursor.fetchall() or []
            price_map = {r["class_type"]: float(r["class_price"] or 0.0) for r in rows}

            details = []
            total = 0.0
            for class_type, row_num, col_num in parsed:
                price = float(price_map.get(class_type, 0.0))
                details.append(
                    {
                        "seat_no": f"{row_num}{col_num}",
                        "class_type": class_type,
                        "price": price,
                        "row_num": row_num,
                        "column_number": col_num,
                        "aircraft_id": aircraft_id,
                    }
                )
                total += price

            Booking._dbg(f"pricing: aircraft_id={aircraft_id}, total={total}, details_count={len(details)}")
            return details, total

    # ----------------------------
    # Booking id generation BK0001...
    # ----------------------------
    @staticmethod
    def get_next_booking_id() -> str:
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT MAX(CAST(SUBSTRING(booking_id, 3) AS UNSIGNED)) AS max_num
                FROM Booking
                WHERE booking_id LIKE 'BK%'
                """
            )
            row = cursor.fetchone() or {}
            max_num = int(row.get("max_num") or 0)
            next_num = max_num + 1
            bid = f"BK{next_num:04d}"
            Booking._dbg(f"get_next_booking_id -> {bid} (max_num={max_num})")
            return bid

    # ----------------------------
    # Create booking + tickets
    # ----------------------------
    @staticmethod
    def create_booking_with_tickets(
            flight_number: int,
            first_name: str,
            last_name: str,
            email: str,
            selected_seats: list[str],
            payment_method: str,
            logged_in_registered: bool,
            phone_numbers_text: str = "",
            passport_number: str = "",
    ):
        email = (email or "").strip().lower()
        phones = Booking._parse_phone_numbers(phone_numbers_text)
        passport_number = (passport_number or "").strip()  # כרגע לא נשמר

        Booking._dbg(
            "create_booking_with_tickets("
            f"flight={flight_number}, email={email}, logged_in_registered={logged_in_registered}, "
            f"payment={payment_method}, seats={selected_seats}, phones={phones})"
        )

        if not email or not selected_seats:
            Booking._dbg("create_booking: missing email or seats -> None")
            return None

        # לא חובה, אבל מומלץ: enforce גם פה
        if not phones and not logged_in_registered:
            Booking._dbg("create_booking: guest must provide at least 1 phone -> None")
            return None

        details, total = Booking.get_pricing_for_selected_seats(int(flight_number), selected_seats)
        if not details:
            Booking._dbg("create_booking: details empty -> None")
            return None

        aircraft_id = int(details[0]["aircraft_id"])
        Booking._dbg(f"create_booking: aircraft_id={aircraft_id}, seats_count={len(details)}, total={total}")

        def _seat_key(d):
            return (d["class_type"], int(d["row_num"]), int(d["column_number"]))

        seats = [_seat_key(d) for d in details]

        with DB.get_cursor() as cursor:
            # 0) Ensure Guest exists + save many phones (only for guests)
            if not logged_in_registered:
                cursor.execute("SELECT 1 FROM GuestUser WHERE email=%s LIMIT 1", (email,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO GuestUser (email, first_name_en, last_name_en) VALUES (%s,%s,%s)",
                        (email, first_name, last_name),
                    )

                for ph in phones:
                    cursor.execute(
                        "INSERT IGNORE INTO GuestPhone (email, phone_number) VALUES (%s,%s)",
                        (email, ph),
                    )

            # 1) Validate Seat existence (set-based)
            cursor.execute(
                """
                SELECT class_type, row_num, column_number
                FROM Seat
                WHERE aircraft_id = %s
                """,
                (aircraft_id,),
            )
            existing_seats = {
                (r["class_type"], int(r["row_num"]), int(r["column_number"]))
                for r in (cursor.fetchall() or [])
            }

            missing = [s for s in seats if s not in existing_seats]
            if missing:
                Booking._dbg(f"SEAT NOT FOUND in Seat table: {missing} -> None")
                return None

            # 2) Ticket conflict check (set-based)
            cursor.execute(
                """
                SELECT class_type, row_num, column_number
                FROM Ticket
                WHERE flight_number = %s
                """,
                (int(flight_number),),
            )
            taken = {
                (r["class_type"], int(r["row_num"]), int(r["column_number"]))
                for r in (cursor.fetchall() or [])
            }

            conflict = [s for s in seats if s in taken]
            if conflict:
                Booking._dbg(f"CONFLICT: seats already taken: {conflict} -> None")
                return None

            # 3) Insert Booking
            booking_id = Booking.get_next_booking_id()
            registered_email = email if logged_in_registered else None
            guest_email = None if logged_in_registered else email

            cursor.execute(
                """
                INSERT INTO Booking
                  (booking_id, registered_email, guest_email, flight_number, price, booking_date, booking_status)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    booking_id,
                    registered_email,
                    guest_email,
                    int(flight_number),
                    float(total),
                    date.today(),
                    "Active",
                ),
            )

            # 4) Insert Tickets
            try:
                for class_type, row_num, col_num in seats:
                    cursor.execute(
                        """
                        INSERT INTO Ticket
                          (booking_id, flight_number, aircraft_id, class_type, row_num, column_number)
                        VALUES
                          (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            booking_id,
                            int(flight_number),
                            aircraft_id,
                            class_type,
                            row_num,
                            col_num,
                        ),
                    )
            except Exception as e:
                Booking._dbg(f"ERROR inserting Ticket: {repr(e)} -> cleanup")
                try:
                    cursor.execute("DELETE FROM Ticket WHERE booking_id=%s", (booking_id,))
                except Exception as e2:
                    Booking._dbg(f"cleanup Ticket failed: {repr(e2)}")
                try:
                    cursor.execute("DELETE FROM Booking WHERE booking_id=%s", (booking_id,))
                except Exception as e3:
                    Booking._dbg(f"cleanup Booking failed: {repr(e3)}")
                return None

        Flight.update_status_by_capacity(int(flight_number))
        Booking._dbg(f"create_booking: SUCCESS booking_id={booking_id}")
        return booking_id

    @staticmethod
    def get_user_flights_split(user_email: str, now=None):
        """
        Returns (active_bookings, history_bookings)
        Active = departure_time > now AND booking_status == 'Active'
        Everything else goes to history.
        """
        Booking.sync_past_bookings()
        all_bookings = Booking.get_user_flights(user_email)

        now = now or datetime.now()

        active, history = [], []
        for b in all_bookings:
            dep = b.get("departure_time")
            status = (b.get("booking_status") or "").strip()

            if dep and dep > now and status == "Active":
                active.append(b)
            else:
                history.append(b)

        return active, history

    @staticmethod
    def calc_cancel_flags(order_data: dict, now=None):
        """
        Rules:
        can_cancel iff:
          - booking_status != 'Canceled by Customer'
          - flight_status in ('Active','Full')
          - departure_time - now > 72h

        show_block_message iff:
          - booking active (not canceled)
          - flight not completed
          - cannot cancel
        """
        now = now or datetime.now()

        booking_status = (order_data.get("booking_status") or "").strip()
        flight_status = (order_data.get("flight_status") or "").strip()
        departure_time = order_data.get("departure_time")

        booking_active = booking_status != "Canceled by Customer"
        flight_cancelable_status = flight_status in ("Active", "Full")
        flight_not_completed = flight_status != "Completed"

        more_than_36h = False
        if departure_time:
            more_than_36h = (departure_time - now) > timedelta(hours=36)

        can_cancel = booking_active and flight_cancelable_status and more_than_36h
        show_block_message = booking_active and flight_not_completed and (not can_cancel)

        block_message = (
            "הזמנה זו לא ניתנת לביטול מאחר ונותרו פחות מ-36 שעות להמראה"
            if show_block_message else None
        )

        return can_cancel, show_block_message, block_message

    @staticmethod
    def get_details_by_id(booking_id: str):
        b = Booking(booking_id, None, None)
        return b.get_details()

    @staticmethod
    def _parse_phones_multiline(raw: str) -> list[str]:
        if not raw:
            return []
        # תומך בשורות / פסיקים
        parts = []
        for line in raw.replace(",", "\n").splitlines():
            p = line.strip()
            if p:
                parts.append(p)
        # unique, preserving order
        seen = set()
        out = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    @staticmethod
    def _normalize_phone(raw: str) -> str:
        """
        Normalize phone for storage:
        - strip spaces
        - keep digits and leading +
        Example: '050-123 4567' -> '0501234567'
        """
        s = (raw or "").strip()
        if not s:
            return ""
        s = s.replace(" ", "").replace("-", "")
        # allow leading +
        if s.startswith("+"):
            return "+" + re.sub(r"\D", "", s[1:])
        return re.sub(r"\D", "", s)

    @staticmethod
    def _parse_phone_numbers(phone_numbers_text: str) -> list[str]:
        """
        Accepts multiline or comma-separated input and returns a deduped list.
        """
        text = (phone_numbers_text or "").strip()
        if not text:
            return []

        parts = re.split(r"[,\n\r\t]+", text)
        out = []
        seen = set()
        for p in parts:
            norm = Booking._normalize_phone(p)
            if not norm:
                continue
            if norm not in seen:
                seen.add(norm)
                out.append(norm)
        return out

    @staticmethod
    def get_user_flights_for_page(user_email, selected_status=""):
        q = """
            SELECT
                b.booking_id,
                b.price,
                b.booking_date,
                b.booking_status,

                f.flight_number,
                f.aircraft_id,
                f.origin,
                f.destination,
                f.departure_time,
                f.arrival_time,
                f.flight_status,

                ru.first_name_en AS first_name,
                ru.last_name_en  AS last_name
            FROM Booking b
            JOIN Flight f ON f.flight_number = b.flight_number
            LEFT JOIN RegisteredUser ru ON ru.email = b.registered_email
            WHERE (b.registered_email = %s OR b.guest_email = %s)
            ORDER BY f.departure_time DESC
        """

        with DB.get_cursor() as cursor:
            cursor.execute(q, (user_email, user_email))
            flights = cursor.fetchall() or []

        # source of truth: booking_status
        for f in flights:
            f["display_status"] = (f.get("booking_status") or "").strip()

        if selected_status:
            flights = [f for f in flights if f.get("display_status") == selected_status]

        return flights