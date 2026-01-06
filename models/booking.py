from __future__ import annotations

from datetime import date
from database import DB


class Booking:
    def __init__(self, booking_id, flight_number, price, status="Active"):
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

    # ----------------------------
    # Existing queries
    # ----------------------------
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
    def get_by_id(booking_id):
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Booking WHERE booking_id = %s", (booking_id,))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    @staticmethod
    def get_by_id_and_email(booking_id, email):
        query = """
            SELECT *
            FROM Booking
            WHERE booking_id = %s
              AND (registered_email = %s OR guest_email = %s)
        """
        with DB.get_cursor() as cursor:
            cursor.execute(query, (booking_id, email, email))
            row = cursor.fetchone()
            return Booking.from_db(row) if row else None

    @staticmethod
    def get_user_flights(user_identifier):
        """
        Optional helper (if you already had it before).
        Keeps behavior: returns all bookings for a registered user email or manager id.
        """
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM Booking
                WHERE registered_email = %s
                ORDER BY booking_date DESC
                """,
                (user_identifier,),
            )
            return cursor.fetchall() or []

    def get_details(self):
        with DB.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT B.*, F.origin, F.destination, F.departure_time, F.arrival_time, F.flight_status,
                       COALESCE(B.registered_email, B.guest_email) AS email
                FROM Booking B
                JOIN Flight F ON B.flight_number = F.flight_number
                WHERE B.booking_id = %s
                """,
                (self.booking_id,),
            )
            order = cursor.fetchone()

            cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            seats = cursor.fetchall() or []

            return order, seats

    def cancel(self):
        with DB.get_cursor() as cursor:
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
        detail item:
          {
            "seat_no": "14",
            "class_type": "Economy",
            "price": 310.0,
            "row_num": 1,
            "column_number": 4,
            "aircraft_id": 777
          }
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

            # Build price map per class (from Classes_on_Flights, filtered by aircraft_id like your seat_map)
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
        """
        If max booking is BK0014 -> returns BK0015
        """
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
    # Create booking + tickets (LOCK BY TICKET, because availability is derived from Ticket)
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
    ):
        Booking._dbg(
            "create_booking_with_tickets("
            f"flight={flight_number}, email={email}, logged_in_registered={logged_in_registered}, "
            f"payment={payment_method}, seats={selected_seats})"
        )

        details, total = Booking.get_pricing_for_selected_seats(int(flight_number), selected_seats)
        if not details:
            Booking._dbg("create_booking: details empty -> None")
            return None

        email = (email or "").strip().lower()
        if not email:
            Booking._dbg("create_booking: email empty -> None")
            return None

        with DB.get_cursor() as cursor:
            aircraft_id = details[0]["aircraft_id"]
            Booking._dbg(f"create_booking: aircraft_id={aircraft_id}, seats_count={len(details)}, total={total}")

            # 0) If guest flow: MUST exist before Booking insert (FK Booking.guest_email -> GuestUser.email)
            if not logged_in_registered:
                Booking._dbg("create_booking: step0 ensure GuestUser exists (FK requirement) ...")
                cursor.execute("SELECT 1 FROM GuestUser WHERE email = %s LIMIT 1", (email,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO GuestUser (email, first_name_en, last_name_en) VALUES (%s, %s, %s)",
                        (email, first_name, last_name),
                    )
                    Booking._dbg("create_booking: GuestUser inserted")

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

            # 3) Insert Booking (now FK will pass because GuestUser exists)
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

            # NEW: update flight status if full (import here to avoid circular import)
            from models.flight import Flight
            Flight.update_status_if_full(int(flight_number))

            return booking_id