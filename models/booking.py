from datetime import date
from database import DB
from datetime import datetime,timedelta


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
            phone_number: str = "",
            passport_number: str = "",  # לא נשמר, רק אם תרצה ולידציה/לוגיקה בעתיד
    ):
        Booking._dbg(
            "create_booking_with_tickets("
            f"flight={flight_number}, email={email}, logged_in_registered={logged_in_registered}, "
            f"payment={payment_method}, seats={selected_seats}, phone={phone_number})"
        )

        details, total = Booking.get_pricing_for_selected_seats(int(flight_number), selected_seats)
        if not details:
            Booking._dbg("create_booking: details empty -> None")
            return None

        email = (email or "").strip().lower()
        if not email:
            Booking._dbg("create_booking: email empty -> None")
            return None

        phone_number = (phone_number or "").strip()
        passport_number = (passport_number or "").strip()

        with DB.get_cursor() as cursor:
            aircraft_id = details[0]["aircraft_id"]
            Booking._dbg(f"create_booking: aircraft_id={aircraft_id}, seats_count={len(details)}, total={total}")

            # 0) Guest must exist before Booking insert (FK)
            if not logged_in_registered:
                Booking._dbg("create_booking: step0 ensure GuestUser exists (FK requirement) ...")
                cursor.execute("SELECT 1 FROM GuestUser WHERE email = %s LIMIT 1", (email,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO GuestUser (email, first_name_en, last_name_en) VALUES (%s, %s, %s)",
                        (email, first_name, last_name),
                    )
                    Booking._dbg("create_booking: GuestUser inserted")

                # NEW: Save guest phone in separate table (passport NOT saved)
                if phone_number:
                    cursor.execute(
                        "INSERT IGNORE INTO GuestPhone (email, phone_number) VALUES (%s, %s)",
                        (email, phone_number),
                    )
                    Booking._dbg("create_booking: GuestPhone inserted/ignored")

            # 1) Validate Seat existence
            Booking._dbg("create_booking: step1 validate seats exist in Seat...")
            for d in details:
                cursor.execute(
                    """
                    SELECT 1
                    FROM Seat
                    WHERE aircraft_id = %s
                      AND class_type = %s
                      AND row_num = %s
                      AND column_number = %s
                    LIMIT 1
                    """,
                    (aircraft_id, d["class_type"], d["row_num"], d["column_number"]),
                )
                if not cursor.fetchone():
                    Booking._dbg(
                        "SEAT NOT FOUND in Seat table "
                        f"(aircraft_id={aircraft_id}, class={d['class_type']}, row={d['row_num']}, col={d['column_number']}) -> None"
                    )
                    return None

            # 2) Check conflicts in Ticket
            Booking._dbg("create_booking: step2 check conflicts in Ticket...")
            for d in details:
                cursor.execute(
                    """
                    SELECT booking_id
                    FROM Ticket
                    WHERE flight_number = %s
                      AND class_type = %s
                      AND row_num = %s
                      AND column_number = %s
                    LIMIT 1
                    """,
                    (int(flight_number), d["class_type"], d["row_num"], d["column_number"]),
                )
                hit = cursor.fetchone()
                if hit:
                    Booking._dbg(
                        "CONFLICT: Ticket already exists for "
                        f"{d['class_type']}-{d['row_num']}-{d['column_number']} "
                        f"(existing_booking_id={hit.get('booking_id')}) -> None"
                    )
                    return None

            # 3) Insert Booking
            booking_id = Booking.get_next_booking_id()
            registered_email = email if logged_in_registered else None
            guest_email = None if logged_in_registered else email

            Booking._dbg(f"create_booking: step3 insert Booking booking_id={booking_id} ...")
            cursor.execute(
                """
                INSERT INTO Booking
                  (booking_id, registered_email, guest_email, flight_number, price, booking_date, booking_status)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s)
                """,
                (booking_id, registered_email, guest_email, int(flight_number), float(total), date.today(), "Active"),
            )

            # 4) Insert Tickets
            Booking._dbg("create_booking: step4 insert Ticket rows ...")
            try:
                for d in details:
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
                            int(aircraft_id),
                            d["class_type"],
                            int(d["row_num"]),
                            int(d["column_number"]),
                        ),
                    )
            except Exception as e:
                Booking._dbg(f"ERROR inserting Ticket: {repr(e)} -> cleanup Booking + Tickets best-effort")
                try:
                    cursor.execute("DELETE FROM Ticket WHERE booking_id = %s", (booking_id,))
                except Exception as e2:
                    Booking._dbg(f"cleanup Ticket failed: {repr(e2)}")
                try:
                    cursor.execute("DELETE FROM Booking WHERE booking_id = %s", (booking_id,))
                except Exception as e3:
                    Booking._dbg(f"cleanup Booking failed: {repr(e3)}")
                return None

            Booking._dbg(f"create_booking: SUCCESS booking_id={booking_id}")

        from models.flight import Flight
        Flight.update_status_by_capacity(int(flight_number))

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

