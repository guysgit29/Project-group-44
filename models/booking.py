from datetime import date
from database import DB


class Booking:
    def __init__(self, booking_id, flight_number, price, status="Active"):
        self.booking_id = booking_id
        self.flight_number = flight_number
        self.price = price
        self.status = status

    @staticmethod
    def from_db(row):
        if not row:
            return None
        return Booking(
            row["booking_id"],
            row["flight_number"],
            row["price"],
            row.get("booking_status", "Active")
        )

    @staticmethod
    def get_by_id(booking_id):
        with DB.get_cursor() as cursor:
            cursor.execute("SELECT * FROM Booking WHERE booking_id=%s", (booking_id,))
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

    def get_details(self):
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT B.*, F.origin, F.destination, F.departure_time, F.arrival_time, F.flight_status,
                       COALESCE(B.registered_email, B.guest_email) AS email
                FROM Booking B
                JOIN Flight F ON B.flight_number = F.flight_number
                WHERE B.booking_id = %s
            """, (self.booking_id,))
            order = cursor.fetchone()

            cursor.execute("SELECT * FROM Ticket WHERE booking_id = %s", (self.booking_id,))
            seats = cursor.fetchall()
            return order, seats

    def cancel(self):
        with DB.get_cursor() as cursor:
            cursor.execute("DELETE FROM Ticket WHERE booking_id=%s", (self.booking_id,))
            cursor.execute("""
                UPDATE Booking
                SET booking_status='Canceled by Customer',
                    price = price * 0.05
                WHERE booking_id=%s
            """, (self.booking_id,))

    # ---------- pricing ----------
    @staticmethod
    def get_pricing_for_selected_seats(flight_number: int, selected_seats: list[str]):
        details = []
        total = 0.0

        if not flight_number or not selected_seats:
            return [], 0.0

        with DB.get_cursor() as cursor:
            for seat_str in selected_seats:
                parts = (seat_str or "").split("-")
                if len(parts) != 3:
                    continue

                class_type = parts[0]
                try:
                    row_num = int(parts[1])
                    col_num = int(parts[2])
                except ValueError:
                    continue

                cursor.execute(
                    """
                    SELECT class_price
                    FROM Classes_on_Flights
                    WHERE flight_number=%s AND class_type=%s
                    """,
                    (int(flight_number), class_type)
                )
                res = cursor.fetchone()
                price = float(res["class_price"]) if res and res["class_price"] is not None else 0.0

                total += price
                details.append({
                    "seat_no": f"{row_num}{col_num}",
                    "class_type": class_type,
                    "price": price,
                    "row_num": row_num,
                    "column_number": col_num
                })

        return details, total

    # ---------- booking id BK0001 ----------
    @staticmethod
    def get_next_booking_id() -> str:
        with DB.get_cursor() as cursor:
            cursor.execute("""
                SELECT MAX(CAST(SUBSTRING(booking_id, 3) AS UNSIGNED)) AS max_num
                FROM Booking
                WHERE booking_id LIKE 'BK%'
            """)
            row = cursor.fetchone() or {}
            max_num = int(row.get("max_num") or 0)
            return f"BK{max_num + 1:04d}"

    # ---------- create booking ----------
    @staticmethod
    def create_booking_with_tickets(
        flight_number: int,
        first_name: str,
        last_name: str,
        email: str,
        selected_seats: list[str],
        payment_method: str,
        logged_in_registered: bool
    ):
        # 1) pricing
        details, total = Booking.get_pricing_for_selected_seats(flight_number, selected_seats)
        if not details:
            return None

        with DB.get_cursor() as cursor:
            # 2) lock seats FIRST
            for d in details:
                cursor.execute(
                    """
                    UPDATE Seats_on_Flights
                    SET available = 0
                    WHERE flight_number=%s
                      AND class_type=%s
                      AND row_num=%s
                      AND column_number=%s
                      AND available=1
                    """,
                    (flight_number, d["class_type"], d["row_num"], d["column_number"])
                )
                if cursor.rowcount != 1:
                    return None  # seat already taken / mismatch

            # 3) booking id
            booking_id = Booking.get_next_booking_id()

            registered_email = email if logged_in_registered else None
            guest_email = None if logged_in_registered else email

            # 4) create booking
            cursor.execute(
                """
                INSERT INTO Booking
                  (booking_id, registered_email, guest_email, flight_number, price, booking_date, booking_status)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s)
                """,
                (booking_id, registered_email, guest_email, flight_number, total, date.today(), "Active")
            )

            # 5) tickets
            for d in details:
                cursor.execute(
                    """
                    INSERT INTO Ticket
                      (booking_id, flight_number, class_type, row_num, column_number)
                    VALUES
                      (%s, %s, %s, %s, %s)
                    """,
                    (booking_id, flight_number, d["class_type"], d["row_num"], d["column_number"])
                )

            # 6) GuestUser ONLY AFTER everything succeeded
            if not logged_in_registered:
                cursor.execute("SELECT 1 FROM GuestUser WHERE email=%s LIMIT 1", (email,))
                if not cursor.fetchone():
                    cursor.execute(
                        "INSERT INTO GuestUser (email, first_name_en, last_name_en) VALUES (%s, %s, %s)",
                        (email, first_name, last_name)
                    )

            return booking_id