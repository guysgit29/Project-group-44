from database import DB


class Booking:
    def __init__(self, booking_id, flight_number, price, status='Active'):
        self.booking_id = booking_id
        self.flight_number = flight_number
        self.price = price
        self.status = status

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

    @staticmethod
    def create_booking(flight_number: int,
                       email: str,
                       first_name: str,
                       last_name: str,
                       selected_seats: list[str],
                       total: float,
                       is_registered: bool) -> int:
        """
        Create a booking + tickets.
        selected_seats format: ["Business-1-4", "Economy-5-3", ...]
        Returns: booking_id (int)
        """

        if not selected_seats:
            raise ValueError("selected_seats is empty")

        # Decide which email column to fill
        reg_email = email if is_registered else None
        guest_email = None if is_registered else email

        with DB.get_cursor() as cursor:
            # 1) Create booking
            cursor.execute(
                """
                INSERT INTO Booking (flight_number, registered_email, guest_email, price, booking_status)
                VALUES (%s, %s, %s, %s, 'Active')
                """,
                (int(flight_number), reg_email, guest_email, float(total))
            )

            booking_id = cursor.lastrowid
            if not booking_id:
                # fallback (rare): fetch last inserted id
                cursor.execute("SELECT LAST_INSERT_ID() AS booking_id")
                booking_id = cursor.fetchone()["booking_id"]

            # 2) Create tickets for selected seats
            for seat_str in selected_seats:
                class_type, row_num, col_num = seat_str.split("-")

                cursor.execute(
                    """
                    INSERT INTO Ticket (booking_id, flight_number, class_type, row_num, column_number)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (int(booking_id), int(flight_number), class_type, int(row_num), int(col_num))
                )

                # 3) OPTIONAL: mark seat as taken if you have Seat table with 'available'
                # If your schema has Seat( flight_number, row_num, column_number, available )
                # uncomment this:
                #
                # cursor.execute(
                #     """
                #     UPDATE Seat
                #     SET available = 0
                #     WHERE flight_number = %s AND row_num = %s AND column_number = %s
                #     """,
                #     (int(flight_number), int(row_num), int(col_num))
                # )

        # 4) Update flight status by capacity (you already use this in cancel)
        from models.flight import Flight
        Flight.update_status_by_capacity(int(flight_number))

        return int(booking_id)